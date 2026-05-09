"""LangGraphTaskRunner — 与现有 TaskRunner 等价的 LangGraph 实现。

对外 API 兼容:
  - start(task_id) → invoke graph,返回 派发的 step 列表(对齐 TaskRunner.start)
  - resume(task_id, step_id, decision) → Command(resume=...) 唤醒 interrupt
  - resolve_hitl(...) → 同 resume
  - rollback_to_step(task_id, target_step) → time-travel(V2 中断 C/D 真实现)
  - get_state(task_id) → graph.aget_state
  - get_history(task_id) → graph.aget_state_history(用于 UI 时间线 + V2 回滚选 N)

对外仍走 ws_manager.publish(铁律不变)。LangGraph 的 astream_events 用作内部事件源
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
import yaml
from langgraph.errors import GraphRecursionError  # noqa: F401 — 供 except 命中
from langgraph.types import Command
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hitl_gate import HITLGate
from app.models.conversation import Conversation
from app.models.skill import Skill
from app.models.task import Task, TaskStep
from agents.orchestrator_agent.interaction import (
    emit_and_persist_handoff,
    should_emit_handoff,
)
from agents.orchestrator_agent.langgraph_runner.compiler import build_state_graph
from agents.orchestrator_agent.langgraph_runner.result_waiter import (
    reset_cursor,
    wait_for_step_result,
)
from agents.orchestrator_agent.langgraph_runner.runner_checkpointer import (
    get_checkpointer,
    init_checkpointer,
)
from agents.orchestrator_agent.langgraph_runner.runner_compiled_cache import (
    COMPILED_GRAPH_CACHE,
    clear_compiled_cache,
    skill_yaml_cache_key,
)
from agents.orchestrator_agent.langgraph_runner.runner_db_mirror import (
    mirror_state_steps_to_db,
    mirror_step_to_db,
)
from agents.orchestrator_agent.langgraph_runner.state import make_initial_state
from app.schemas.ws import WSEventType
from app.services.agent_result_stream import cleanup_task_redis
from app.services.agent_status import set_status as set_agent_status
from app.services.dispatcher import dispatch_task as default_dispatch
from app.services.flywheel import flywheel
from app.services.memory.hooks import apply_task_memory_snapshot
from app.services.skill_loader import load_skill_by_id
from app.ws.manager import ws_manager

log = structlog.get_logger(__name__)

# ── 自定义 WS 事件 type(尚未进 backend WSEventType enum)──
# backend 在 `app/schemas/ws.py:WSEventType` 加 `TASK_ROLLED_BACK = "task_rolled_back"`
# + 把它纳入 `WSEvent` union 后,这里可改为 `WSEventType.TASK_ROLLED_BACK`。
EVENT_TASK_ROLLED_BACK = "task_rolled_back"

# ── Tier-1 韧性常量 ──
GRAPH_RECURSION_LIMIT = 50  # 防 V1.5 嵌套撞默认 25

# 兼容 backend 单测: `runner._cache_key` / `runner._COMPILED_CACHE`
_cache_key = skill_yaml_cache_key
_COMPILED_CACHE = COMPILED_GRAPH_CACHE


# ─────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────
class LangGraphTaskRunner:
    """与 TaskRunner 接口兼容的 LangGraph 版编排器。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        dispatcher=None,
        publisher=None,
    ) -> None:
        self.session = session
        self.dispatch = dispatcher or default_dispatch
        self.publish = publisher or ws_manager.publish

    # ── 加载 Skill YAML(同 TaskRunner)──
    async def _load_skill_yaml(self, task: Task) -> dict[str, Any]:
        if task.skill_id is None:
            raise ValueError(f"task {task.id} has no skill_id")
        skill = await self.session.get(Skill, task.skill_id)
        if skill is None:
            raise ValueError(f"skill {task.skill_id} not found in DB")
        if skill.yaml_content:
            return yaml.safe_load(skill.yaml_content)  # type: ignore[no-any-return]
        return load_skill_by_id(skill.skill_id)

    # ── thread_id 约定:LangGraph checkpoint 的 key ──
    @staticmethod
    def _thread_id(task_id: UUID) -> str:
        return f"task:{task_id}"

    async def _build_compiled(self, skill_yaml: dict[str, Any]):
        """编译 + 注入 checkpointer。按 (skill_id, version) 缓存编译产物。

        CompiledStateGraph 是无状态的(状态在 checkpointer),可跨 task / 跨请求共享。
        key 含 dispatcher 不必要(实例方法绑定 self,但 dispatch_task 是模块级单例)。
        """
        key = _cache_key(skill_yaml)
        cached = _COMPILED_CACHE.get(key)
        if cached is not None:
            return cached

        async def _wait(tid: str, sid: str, timeout: int):
            return await wait_for_step_result(tid, sid, timeout)

        builder = build_state_graph(
            skill_yaml,
            dispatcher=self.dispatch,
            result_waiter=_wait,
        )
        graph = builder.compile(
            checkpointer=get_checkpointer(),
            recursion_limit=GRAPH_RECURSION_LIMIT,
        )
        # 仅当 key 完整(skill_id+version 都有)时才缓存,避免测试场景污染
        if key[0] is not None and key[1] is not None:
            _COMPILED_CACHE[key] = graph
            log.info("lg.compiled_cached", skill_id=key[0], version=key[1])
        return graph

    # ── start:首次跑 ──
    async def start(self, task_id: UUID) -> dict[str, Any]:
        """启动 LangGraph 图。返回 final state(可能含 interrupt 标记)。"""
        task = await self.session.get(Task, task_id)
        if task is None:
            raise ValueError(f"task {task_id} not found")
        skill_yaml = await self._load_skill_yaml(task)

        graph = await self._build_compiled(skill_yaml)
        config = {"configurable": {"thread_id": self._thread_id(task_id)}}

        initial = make_initial_state(
            task_id=task_id,
            user_id=task.user_id,
            conversation_id=task.conversation_id,
            skill_id=task.skill_id,
            skill_version=task.skill_version,
            skill_yaml=skill_yaml,
            collected_fields=task.collected_fields or {},
        )

        # 标记 task 进入执行
        task.status = "executing"
        task.started_at = task.started_at or datetime.now(UTC)
        await self.session.commit()

        # 跑 graph 直到结束 / interrupt(用 stream + handlers)
        final_state = await self._run_until_pause(graph, initial, config, task_id, task.user_id)
        return {"state": final_state, "config": config}

    # ── resume:HITL 决议后 / 中断后续 ──
    async def resume(
        self,
        task_id: UUID,
        *,
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        """HITL gate 用户决议后调:graph 用 Command(resume=decision) 继续跑。"""
        task = await self.session.get(Task, task_id)
        if task is None:
            raise ValueError(f"task {task_id} not found")
        skill_yaml = await self._load_skill_yaml(task)
        graph = await self._build_compiled(skill_yaml)
        config = {"configurable": {"thread_id": self._thread_id(task_id)}}

        # 校验图当前确实处于中断状态,防止对已完成/不存在的任务 resume
        snap = await graph.aget_state(config)
        if not snap.next:
            raise ValueError(
                f"task {task_id} is not in an interrupted state "
                f"(next={list(snap.next)!r}); cannot resume"
            )

        final_state = await self._run_until_pause(
            graph,
            Command(resume=decision),
            config,
            task_id,
            task.user_id,
        )
        return {"state": final_state, "config": config}

    # ── 兼容老 API:resolve_hitl(gate_id, resolution, user_choice) → 内部转 resume ──
    async def resolve_hitl(
        self,
        gate_id: UUID,
        *,
        resolution: str,
        user_choice: dict[str, Any] | None = None,
    ) -> list[str]:
        """V1 hitl.py 调用入口。把 gate_id → task_id,组装 decision payload 转给 resume。

        decision 语义:
        - resolution="approved"   → graph 继续跑下游
        - resolution="modified"   → graph 走 modify(V1.5 用 rollback_to_step 实现)
        - resolution="cancelled"  → 标 final_status=failed
        - resolution="rejected"   → 同 cancelled
        """
        gate = await self.session.get(HITLGate, gate_id)
        if gate is None:
            raise ValueError(f"hitl gate {gate_id} not found")
        # 关 gate(UI 兼容)
        gate.resolution = resolution
        gate.user_choice = user_choice or {}
        gate.closed_at = datetime.now(UTC)
        await self.session.commit()
        task_row = await self.session.get(Task, gate.task_id)
        if task_row is not None:
            await self.publish(
                str(task_row.user_id),
                {
                    "type": WSEventType.HITL_GATE_CLOSED,
                    "task_id": str(gate.task_id),
                    "gate_id": str(gate_id),
                    "resolution": resolution,
                },
            )
        # LangGraph resume:resolution=approved 继续;cancelled/rejected 终止;modified 暂作 approved + 标记
        if resolution in ("cancelled", "rejected"):
            decision = {"resolution": "rejected", "feedback": (user_choice or {}).get("reason", "user_cancelled")}
        elif resolution == "modified":
            # V1.5 真实现:这里应当调 rollback_to_step;V1 暂作 approved 处理
            decision = {"resolution": "approved", "modify_request": user_choice or {}}
        else:
            decision = {"resolution": "approved", "user_choice": user_choice or {}}
        interrupt_id = (gate.extra_metadata or {}).get("interrupt_id")
        resume_decision = {interrupt_id: decision} if interrupt_id else decision
        out = await self.resume(gate.task_id, decision=resume_decision)
        # 返回新派发的 step_id 列表(API 契约兼容)— 简化:从最终 state 提 next
        return list((out.get("state") or {}).get("step_results", {}).keys())

    # ── 时间旅行:V2 中断 C/D — 回滚到 step N 重做 ──
    async def rollback_to_step(
        self,
        task_id: UUID,
        *,
        target_step_id: str,
        instruction: str | None = None,
    ) -> dict[str, Any]:
        """回滚到指定 step 的 checkpoint,并清掉它和下游的状态后再跑。

        这是 V2 中断 C/D 的核心实现。LangGraph 原生支持:
          1. aget_state_history 找到 target_step 完成前的 checkpoint
          2. update_state 改写 collected_fields(承载 user instruction)+ 清下游 step
          3. 用 None invoke 让 graph 从该 checkpoint 继续
        """
        task = await self.session.get(Task, task_id)
        if task is None:
            raise ValueError(f"task {task_id} not found")
        skill_yaml = await self._load_skill_yaml(task)
        graph = await self._build_compiled(skill_yaml)
        config = {"configurable": {"thread_id": self._thread_id(task_id)}}

        # 找回滚点 — history 是 reverse-chronological,跳过 target_step 已完成的 snapshot,
        # 找到第一个 target_step 尚未完成的(= target_step 刚好待跑或下游中)
        target_checkpoint_id = None
        async for snapshot in graph.aget_state_history(config):
            results = (snapshot.values or {}).get("step_results") or {}
            target_done = (
                target_step_id in results
                and results[target_step_id].get("status") == "completed"
            )
            if not target_done:
                target_checkpoint_id = snapshot.config["configurable"].get("checkpoint_id")
                break
        if target_checkpoint_id is None:
            raise ValueError(f"无法找到 step {target_step_id!r} 的回滚点")

        anchor_config = {
            "configurable": {
                "thread_id": self._thread_id(task_id),
                "checkpoint_ns": "",
                "checkpoint_id": target_checkpoint_id,
            }
        }

        # 改写 state — 清掉 target_step 及下游的 step_results
        snap = await graph.aget_state(anchor_config)
        results = dict((snap.values or {}).get("step_results") or {})
        # 找 target_step 的下游(BFS)
        workflow = skill_yaml.get("workflow") or []
        children_map: dict[str, list[str]] = {}
        for s in workflow:
            for d in s.get("depends_on") or []:
                children_map.setdefault(d, []).append(s["step_id"])
        to_clear = {target_step_id}
        frontier = [target_step_id]
        while frontier:
            n = frontier.pop()
            for c in children_map.get(n, []):
                if c not in to_clear:
                    to_clear.add(c)
                    frontier.append(c)
        for sid in to_clear:
            results.pop(sid, None)
            await reset_cursor(str(task_id), sid)
        new_collected = dict((snap.values or {}).get("collected_fields") or {})
        if instruction:
            new_collected["_user_instruction"] = instruction

        await graph.aupdate_state(
            anchor_config,
            {
                "step_results": results,  # 注意:这是完全替换(因为我们没让 reducer 处理"删除")
                "collected_fields": new_collected,
                "rollback_count": (snap.values or {}).get("rollback_count", 0) + 1,
                "final_status": None,
                "failure_reason": None,
            },
        )

        log.info(
            "lg.rollback",
            task_id=str(task_id),
            target=target_step_id,
            cleared=list(to_clear),
        )

        # 镜回 DB:把清掉的 step 标 rolled_back
        for sid in to_clear:
            await self.session.execute(
                update(TaskStep)
                .where(TaskStep.task_id == task_id, TaskStep.step_id == sid)
                .values(status="rolled_back", error_detail={"reason": "user_rollback"})
            )
        await self.session.commit()

        # 从 anchor 继续跑(invoke None 触发 graph 从该 checkpoint resume)
        final_state = await self._run_until_pause(
            graph,
            None,
            {"configurable": {"thread_id": self._thread_id(task_id)}},
            task_id,
            task.user_id,
        )
        await self.publish(
            str(task.user_id),
            {
                "type": EVENT_TASK_ROLLED_BACK,
                "task_id": str(task_id),
                "target_step_id": target_step_id,
                "cleared_steps": sorted(to_clear),
                "rollback_count": (final_state or {}).get("rollback_count"),
            },
        )
        return {"state": final_state, "cleared_steps": sorted(to_clear)}

    # ── 取 state / 历史(给 UI / 调试)──
    async def get_state(self, task_id: UUID) -> dict[str, Any]:
        task = await self.session.get(Task, task_id)
        if task is None:
            raise ValueError(f"task {task_id} not found")
        skill_yaml = await self._load_skill_yaml(task)
        graph = await self._build_compiled(skill_yaml)
        config = {"configurable": {"thread_id": self._thread_id(task_id)}}
        snap = await graph.aget_state(config)
        return {"values": snap.values, "next": list(snap.next), "tasks": [t._asdict() if hasattr(t, "_asdict") else str(t) for t in (snap.tasks or [])]}

    async def get_history(self, task_id: UUID) -> AsyncIterator[dict[str, Any]]:
        task = await self.session.get(Task, task_id)
        if task is None:
            raise ValueError(f"task {task_id} not found")
        skill_yaml = await self._load_skill_yaml(task)
        graph = await self._build_compiled(skill_yaml)
        config = {"configurable": {"thread_id": self._thread_id(task_id)}}
        async for snap in graph.aget_state_history(config):
            yield {
                "checkpoint_id": snap.config["configurable"].get("checkpoint_id"),
                "next": list(snap.next),
                "values_summary": {
                    "step_count": len((snap.values or {}).get("step_results") or {}),
                    "rollback_count": (snap.values or {}).get("rollback_count", 0),
                    "final_status": (snap.values or {}).get("final_status"),
                },
            }

    # ── 内部:跑到下一次 interrupt 或 END,边跑边把状态镜回 DB + WS 推送 ──
    async def _run_until_pause(
        self,
        graph,
        input_or_command,
        config: dict[str, Any],
        task_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """用 astream_events 边跑边推 WS,完成后镜射 state 到 DB。"""
        last_state: dict[str, Any] = {}
        # 互动编排器(铁律 19/22):跨 Agent 交接时在群里说一句
        # **修正并行 fan-out 下的 prev_agent 错位**:
        # 不再用单变量"上一个完成的 agent"(并行时是不确定 race 赢家),
        # 而是按 step.depends_on 查"真正的前置 step",取它的 agent。
        handoffs_so_far = 0
        # 取 task 一次,缓存 conversation_id / scenario / step 元数据
        task_cache = await self.session.get(Task, task_id)
        scenario: str | None = None
        # step_id → (agent_id, depends_on list)
        step_meta: dict[str, dict[str, Any]] = {}
        if task_cache is not None and task_cache.skill_id is not None:
            try:
                yml = await self._load_skill_yaml(task_cache)
                scenario = yml.get("scenario")
                for s in (yml.get("workflow") or []):
                    step_meta[s["step_id"]] = {
                        "agent": s.get("agent"),
                        "task_type": s.get("task_type"),
                        "depends_on": list(s.get("depends_on") or []),
                    }
            except Exception as e:
                log.warning("lg.load_skill_yaml_for_scenario_failed", err=str(e))

        def _pick_predecessor_agent(
            current_step_id: str,
            current_agent: str,
            results: dict[str, dict[str, Any]],
        ) -> str | None:
            """从 step.depends_on 找直接前置中**不同 agent**的 step。

            - depends_on 为空(图入口) → None
            - 所有前置都同 agent → None(同 Agent 内部步骤,不演)
            - 多个不同 agent 前置 → 取 任一(简化,V1 hero 不会出现复杂多 agent fan-in)
            """
            meta = step_meta.get(current_step_id, {})
            for dep in meta.get("depends_on", []):
                dep_meta = step_meta.get(dep, {})
                dep_agent = dep_meta.get("agent")
                if dep_agent and dep_agent != current_agent:
                    return dep_agent
            return None

        # 用 astream_events v2 拿节点开始/结束 + state 更新
        async for event in graph.astream_events(input_or_command, config, version="v2"):
            ev = event.get("event")
            name = event.get("name", "")
            data = event.get("data", {})
            if ev == "on_chain_start" and name.startswith("step_"):
                step_id = name[len("step_") :]
                # backend `app/schemas/ws.py:StepStarted` 要求 agent_id;
                # 从 step_meta(已在 _run_graph 入口构建)查,动态 plan 路径同样有 workflow.agent 字段。
                step_started_agent = (step_meta.get(step_id) or {}).get("agent")
                step_started_payload: dict[str, Any] = {
                    "type": WSEventType.STEP_STARTED,
                    "task_id": str(task_id),
                    "step_id": step_id,
                }
                if step_started_agent:
                    step_started_payload["agent_id"] = step_started_agent
                await self.publish(str(user_id), step_started_payload)
            elif ev == "on_chain_end" and name.startswith("step_"):
                step_id = name[len("step_") :]
                output = data.get("output") or {}
                step_results_delta = output.get("step_results") or {}
                if step_id in step_results_delta:
                    step_result = step_results_delta[step_id]
                    artifact_id = await mirror_step_to_db(
                        self.session, task_id=task_id, step_id=step_id, step_result=step_result
                    )
                    await self.publish(
                        str(user_id),
                        {
                            "type": (
                                WSEventType.STEP_COMPLETED
                                if step_result.get("status") == "completed"
                                else WSEventType.TASK_FAILED
                            ),
                            "task_id": str(task_id),
                            "step_id": step_id,
                            "artifact": (
                                {
                                    "artifact_id": str(artifact_id) if artifact_id else None,
                                    "type": step_result.get("artifact_type"),
                                    "reference": step_result.get("artifact_ref"),
                                    "metadata": step_result.get("artifact_metadata"),
                                }
                                if step_result.get("artifact_ref")
                                else None
                            ),
                        },
                    )
                        # Agent → idle(带 conversation_id 让前端定位群成员栏)
                    current_agent = step_result.get("agent_id")
                    if current_agent:
                        try:
                            await set_agent_status(
                                self.session,
                                user_id=user_id,
                                agent_id=current_agent,
                                status="idle",
                                conversation_id=task_cache.conversation_id if task_cache else None,
                            )
                        except Exception as e:
                            log.warning("lg.set_status_failed", err=str(e))

                        # 互动编排器:跨 Agent 交接时在群里说一句
                        # 用 depends_on 查真前置,**避免并行 fan-out 下的"赢家偏差"**
                    if (
                        current_agent
                        and step_result.get("status") == "completed"
                        and task_cache is not None
                    ):
                        # _pick_predecessor_agent 只依赖 step_meta 闭包,不使用 results 参数
                        # 无需额外读 checkpoint,直接传空 dict
                        pred_agent = _pick_predecessor_agent(
                            step_id, current_agent, {}
                        )
                        if pred_agent and should_emit_handoff(
                            prev_agent=pred_agent,
                            current_agent=current_agent,
                            handoffs_so_far=handoffs_so_far,
                            scenario=scenario,
                        ):
                            summary = f"{step_result.get('task_type','')} 完成"
                            if step_result.get("artifact_ref"):
                                summary += f",产物 {step_result['artifact_ref']}"
                            try:
                                msg = await emit_and_persist_handoff(
                                    self.session,
                                    conversation_id=task_cache.conversation_id,
                                    user_id=user_id,
                                    from_agent=pred_agent,
                                    to_agent=current_agent,
                                    summary=summary,
                                    scenario=scenario,
                                    task_id=task_id,
                                )
                                if msg is not None:
                                    handoffs_so_far += 1
                            except Exception as e:
                                log.warning("lg.emit_handoff_failed", err=str(e))

        # 取最终 state
        snap = await graph.aget_state(config)
        last_state = snap.values or {}
        await mirror_state_steps_to_db(self.session, task_id=task_id, state=last_state)

        # 是否被 interrupt 暂停?— recursion 兜底视为非暂停(直接关单)
        paused = bool(snap.next)
        if paused:
            # 找最近一个 interrupt → open HITLGate row(给现有 UI 兼容)
            await self._open_hitl_for_interrupt(
                snap,
                task_id=task_id,
                user_id=user_id,
                step_meta=step_meta,
            )
        else:
            # 没暂停 → 任务完成(成功/失败)
            await self._finalize_task_db(task_id, last_state)
        return last_state

    async def _open_hitl_for_interrupt(
        self,
        snap,
        *,
        task_id: UUID,
        user_id: UUID,
        step_meta: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """把 LangGraph 的 __interrupt__ 反射成 hitl_gates 行(WS UI 现成)。"""
        ints = []
        for t in snap.tasks or []:
            ints.extend(getattr(t, "interrupts", []) or [])
        if not ints:
            return
        for intr in ints:
            payload = getattr(intr, "value", None) or {}
            step_id = payload.get("step_id") if isinstance(payload, dict) else None
            if not step_id:
                continue
            interrupt_id = getattr(intr, "id", None)
            payload = {**payload, "interrupt_id": interrupt_id} if interrupt_id else payload
            now = datetime.now(UTC).isoformat()
            meta = (step_meta or {}).get(step_id, {})
            await mirror_step_to_db(
                self.session,
                task_id=task_id,
                step_id=step_id,
                step_result={
                    "step_id": step_id,
                    "agent_id": payload.get("agent_id") or meta.get("agent"),
                    "task_type": meta.get("task_type"),
                    "status": "completed",
                    "artifact_ref": payload.get("preview_artifact_ref"),
                    "artifact_type": payload.get("preview_artifact_type") or "text",
                    "artifact_metadata": payload.get("preview_artifact_metadata") or {},
                    "started_at": now,
                    "completed_at": now,
                },
            )
            existing_rows = (
                await self.session.execute(
                    select(HITLGate).where(
                        HITLGate.task_id == task_id,
                        HITLGate.step_id == step_id,
                    )
                )
            ).scalars().all()
            existing = next(
                (
                    gate
                    for gate in existing_rows
                    if (gate.extra_metadata or {}).get("interrupt_id") == interrupt_id
                ),
                None,
            )
            if existing is None:
                existing = next(
                    (gate for gate in existing_rows if gate.closed_at is None),
                    None,
                )
            gate_obj: HITLGate
            if existing is None:
                gate_obj = HITLGate(
                    id=uuid4(),
                    task_id=task_id,
                    step_id=step_id,
                    gate_type=payload.get("gate_type", "quality_review"),
                    preview_artifact_id=None,
                    timeout_seconds=int(payload.get("timeout_seconds") or 600),
                    extra_metadata=payload,
                )
                self.session.add(gate_obj)
                await self.session.commit()
            elif existing.closed_at is not None:
                continue
            else:
                gate_obj = existing
            # 统一为 Shape A(对齐 backend `app/schemas/ws.py:HITLGateOpened`):
            # {type, task_id, gate{id,step_id,gate_type,timeout_seconds},
            #  preview_artifact{artifact_id,type,reference,metadata}}
            await self.publish(
                str(user_id),
                {
                    "type": WSEventType.HITL_GATE_OPENED,
                    "task_id": str(task_id),
                    "gate": {
                        "id": str(gate_obj.id),
                        "step_id": step_id,
                        "gate_type": payload.get("gate_type", "quality_review"),
                        "timeout_seconds": int(payload.get("timeout_seconds") or 600),
                    },
                    "preview_artifact": {
                        "artifact_id": (
                            str(gate_obj.preview_artifact_id)
                            if gate_obj.preview_artifact_id
                            else None
                        ),
                        "type": payload.get("preview_artifact_type"),
                        "reference": payload.get("preview_artifact_ref"),
                        "metadata": payload.get("preview_artifact_metadata") or {},
                    },
                },
            )

    async def _finalize_task_db(self, task_id: UUID, state: dict[str, Any]) -> None:
        task = await self.session.get(Task, task_id)
        if task is None:
            return
        final_status = state.get("final_status") or "completed"
        task.status = final_status
        task.completed_at = datetime.now(UTC)
        if state.get("failure_reason"):
            task.error_detail = {"failure_reason": state["failure_reason"]}
        rid = state.get("orchestration_run_id")
        if rid:
            task.orchestration_run_id = str(rid).strip()[:36]
        tid = state.get("trace_id")
        if tid:
            task.trace_id = str(tid).strip()[:64]
        conv = await self.session.get(Conversation, task.conversation_id)
        apply_task_memory_snapshot(task=task, conv=conv, state=state)
        await self.session.commit()

        # 飞轮:emit_trace
        try:
            duration_ms = (
                int((task.completed_at - task.started_at).total_seconds() * 1000)
                if task.started_at
                else None
            )
            await flywheel.emit_trace(
                self.session,
                task_id=task.id,
                user_id=task.user_id,
                skill_id=task.skill_id,
                skill_version=task.skill_version,
                duration_ms=duration_ms,
                cost_usd=None,
                failure_reason=state.get("failure_reason"),
                full_trace={"step_results": state.get("step_results") or {}},
            )
        except Exception as e:
            log.warning("lg.flywheel_emit_failed", err=str(e))

        # ADR-023:Critic 低分 step → 飞轮(Reflexion)信号
        # graceful — Redis / emitter 不可用时静默,不阻塞主流程
        if os.getenv("ENABLE_CRITIQUE_SIGNAL_EMIT", "true").lower() in {"1", "true", "yes"}:
            try:
                from agents.orchestrator_agent.langgraph_runner.critique_signal import (
                    scan_and_emit_from_state,
                )

                n_emitted = await scan_and_emit_from_state(state)
                if n_emitted:
                    log.info(
                        "lg.critique_signal.emitted",
                        task_id=str(task_id),
                        n_signals=n_emitted,
                    )
            except Exception as e:
                log.warning("lg.critique_signal_emit_failed", err=str(e))

        await self.publish(
            str(task.user_id),
            {
                "type": (
                    WSEventType.TASK_COMPLETED
                    if final_status == "completed"
                    else WSEventType.TASK_FAILED
                ),
                "task_id": str(task_id),
                "primary_artifact": (
                    {"reference": state.get("primary_artifact_ref")}
                    if state.get("primary_artifact_ref")
                    else None
                ),
            },
        )

        # H-7: 跨存储一致性 — 任务完成后清理 Redis 临时 key,防止状态分叉
        try:
            await cleanup_task_redis(task_id)
        except Exception as e:
            log.warning("lg.redis_cleanup_failed", task_id=str(task_id), err=str(e))
