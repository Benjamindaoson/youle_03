"""Critic Loop 运行期集成测试(ADR-020)。

验证 compiler.py 注入的 critic 块在真实 LangGraph 运行时:
  1. flag 关 → 行为完全等同于原 YAML 路径(零额外派发,无 critique 落地)
  2. flag 开 + 评审通过 → 单次派发,critique 落地为通过状态
  3. flag 开 + 评审不通过 → 触发重派,prompt 中含 critic 反馈,最终采用重派结果
  4. 评审始终不通过 → max_retries 命中后保留最后产物,step 不被标记 failed

用 monkeypatch 替换 evaluate 与 fetch_artifact_text_excerpt,**不连任何外部服务**。
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from agents.orchestrator_agent.langgraph_runner.state import make_initial_state
from app.schemas.agent import AgentResult, ArtifactRef


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────
def _mk_skill(workflow, *, primary=None):
    yml: dict[str, Any] = {"skill_id": "test", "version": "1.0", "workflow": workflow}
    if primary:
        yml["delivery"] = {"primary_artifact": primary}
    return yml


class _Queue:
    """Fake dispatcher + result_waiter — FIFO 按 step_id 弹结果。"""

    def __init__(self) -> None:
        self.dispatched: list[Any] = []
        self.next_results: list[AgentResult] = []

    async def dispatch(self, agent_task) -> None:
        self.dispatched.append(agent_task)

    def queue(
        self,
        *,
        task_id,
        step_id: str,
        ref: str = "oss://x.txt",
        status: str = "completed",
    ) -> None:
        self.next_results.append(
            AgentResult(
                task_id=task_id,
                step_id=step_id,
                status=status,  # type: ignore[arg-type]
                output=(
                    ArtifactRef(
                        artifact_id=uuid4(),
                        type="text",
                        reference=ref,
                        extra_metadata={},
                    )
                    if status == "completed"
                    else None
                ),
                duration_ms=10,
            )
        )

    async def wait(self, task_id, step_id: str, timeout: int):
        # 容忍异步调度延迟
        for _ in range(20):
            for i, r in enumerate(self.next_results):
                if r.step_id == step_id:
                    return self.next_results.pop(i)
            await asyncio.sleep(0.005)
        return None


def _initial_state(skill_yaml, **fields):
    return make_initial_state(
        task_id=uuid4(),
        user_id=uuid4(),
        conversation_id=uuid4(),
        skill_id=None,
        skill_version="1.0",
        skill_yaml=skill_yaml,
        collected_fields=fields,
    )


async def _fake_fetch_text(*, reference: str, artifact_type, max_bytes=None):
    """假装从 OSS 取到产物文本,避免连 MinIO。"""
    return {
        "kind": "text",
        "text": f"<produced content of {reference}>",
        "object": None,
        "truncated": False,
    }


# ─────────────────────────────────────────────────────────────────
# 1. flag off → 行为等同原路径
# ─────────────────────────────────────────────────────────────────
async def test_critic_off_no_extra_dispatch(monkeypatch) -> None:
    import agents.orchestrator_agent.langgraph_runner.compiler as cmp
    import agents.orchestrator_agent.langgraph_runner.critic_node as cn

    monkeypatch.setattr(cn, "ENABLE_CRITIC_LOOP", False)

    skill = _mk_skill(
        [{"step_id": "draft", "agent": "agent_1", "task_type": "long_writing"}],
        primary="draft",
    )
    q = _Queue()
    builder = cmp.build_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    graph = builder.compile(checkpointer=InMemorySaver())

    state = _initial_state(skill, topic="x")
    q.queue(task_id=state["task_id"], step_id="draft", ref="oss://d.txt")

    config = {"configurable": {"thread_id": f"task:{state['task_id']}"}}
    final = await graph.ainvoke(state, config)

    assert final["step_results"]["draft"]["status"] == "completed"
    assert final["step_results"]["draft"].get("critique") is None
    assert len(q.dispatched) == 1


# ─────────────────────────────────────────────────────────────────
# 2. flag on + critic pass → 1 次派发,critique 落地
# ─────────────────────────────────────────────────────────────────
async def test_critic_pass_records_critique(monkeypatch) -> None:
    import agents.orchestrator_agent.langgraph_runner.artifact_body as ab
    import agents.orchestrator_agent.langgraph_runner.compiler as cmp
    import agents.orchestrator_agent.langgraph_runner.critic_node as cn

    monkeypatch.setattr(cn, "ENABLE_CRITIC_LOOP", True)
    monkeypatch.setattr(ab, "fetch_artifact_text_excerpt", _fake_fetch_text)

    async def always_pass(**kw):
        return cn.CritiqueResult(
            score=0.92,
            threshold_used=0.7,
            issues=[],
            suggestion="",
            should_retry=False,
            model_used="mock-pass",
        )

    monkeypatch.setattr(cmp, "_critic_evaluate", always_pass)

    skill = _mk_skill(
        [
            {
                "step_id": "draft",
                "agent": "agent_1",
                "task_type": "long_writing",
                "prompt_template": "写一段反诈脚本",
            }
        ],
        primary="draft",
    )
    q = _Queue()
    builder = cmp.build_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    graph = builder.compile(checkpointer=InMemorySaver())

    state = _initial_state(skill)
    q.queue(task_id=state["task_id"], step_id="draft", ref="oss://draft.txt")

    config = {"configurable": {"thread_id": f"task:{state['task_id']}"}}
    final = await graph.ainvoke(state, config)

    assert len(q.dispatched) == 1  # critic 通过,不重派
    crit = final["step_results"]["draft"]["critique"]
    assert crit is not None
    assert crit["score"] == 0.92
    assert crit["model_used"] == "mock-pass"


# ─────────────────────────────────────────────────────────────────
# 3. flag on + critic 第一轮不过 → 第二轮重派 + 反馈注入 + 通过
# ─────────────────────────────────────────────────────────────────
async def test_critic_retries_with_feedback(monkeypatch) -> None:
    import agents.orchestrator_agent.langgraph_runner.artifact_body as ab
    import agents.orchestrator_agent.langgraph_runner.compiler as cmp
    import agents.orchestrator_agent.langgraph_runner.critic_node as cn

    monkeypatch.setattr(cn, "ENABLE_CRITIC_LOOP", True)
    monkeypatch.setattr(ab, "fetch_artifact_text_excerpt", _fake_fetch_text)

    call_n = {"i": 0}

    async def fail_then_pass(**kw):
        call_n["i"] += 1
        if call_n["i"] == 1:
            return cn.CritiqueResult(
                score=0.4,
                threshold_used=0.7,
                issues=["开头钩子无冲突感"],
                suggestion="改写为以一个真实数字开场",
                should_retry=True,
                model_used="mock-fail",
            )
        return cn.CritiqueResult(
            score=0.88,
            threshold_used=0.7,
            issues=[],
            suggestion="",
            should_retry=False,
            model_used="mock-pass",
        )

    monkeypatch.setattr(cmp, "_critic_evaluate", fail_then_pass)

    skill = _mk_skill(
        [
            {
                "step_id": "draft",
                "agent": "agent_1",
                "task_type": "long_writing",
                "prompt_template": "写一段反诈脚本,目标受众老人。",
            }
        ],
        primary="draft",
    )
    q = _Queue()
    builder = cmp.build_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    graph = builder.compile(checkpointer=InMemorySaver())

    state = _initial_state(skill)
    # 两次产物 — 第一次 critic 不过,第二次 critic 过
    q.queue(task_id=state["task_id"], step_id="draft", ref="oss://draft1.txt")
    q.queue(task_id=state["task_id"], step_id="draft", ref="oss://draft2.txt")

    config = {"configurable": {"thread_id": f"task:{state['task_id']}"}}
    final = await graph.ainvoke(state, config)

    # 两次派发(原始 + critic 驱动重派)
    assert len(q.dispatched) == 2
    # 第二次派发的 prompt 含 critic 反馈
    second_prompt = q.dispatched[1].inputs.get("_prompt", "")
    assert "开头钩子无冲突感" in second_prompt
    assert "改写为以一个真实数字开场" in second_prompt
    assert "[Critic 反馈" in second_prompt
    # _critic_feedback 也注入了 inputs
    assert q.dispatched[1].inputs.get("_critic_feedback")
    # idempotency_key 含 critic 标记
    assert "c1" in (q.dispatched[1].idempotency_key or "")
    # 最终采用重派结果
    assert final["step_results"]["draft"]["artifact_ref"] == "oss://draft2.txt"
    # 落地的 critique 是最后一轮(通过的那次)
    assert final["step_results"]["draft"]["critique"]["score"] == 0.88


# ─────────────────────────────────────────────────────────────────
# 4. critic 始终不过 → 重试上限后保留最后产物,step 不被标记 failed
# ─────────────────────────────────────────────────────────────────
async def test_critic_max_retries_pass_through(monkeypatch) -> None:
    import agents.orchestrator_agent.langgraph_runner.artifact_body as ab
    import agents.orchestrator_agent.langgraph_runner.compiler as cmp
    import agents.orchestrator_agent.langgraph_runner.critic_node as cn

    monkeypatch.setattr(cn, "ENABLE_CRITIC_LOOP", True)
    monkeypatch.setattr(ab, "fetch_artifact_text_excerpt", _fake_fetch_text)

    async def always_fail(**kw):
        return cn.CritiqueResult(
            score=0.3,
            threshold_used=0.7,
            issues=["仍然不达标"],
            suggestion="再改",
            should_retry=True,
            model_used="mock-always-fail",
        )

    monkeypatch.setattr(cmp, "_critic_evaluate", always_fail)

    skill = _mk_skill(
        [
            {
                "step_id": "draft",
                "agent": "agent_1",
                "task_type": "long_writing",
                "prompt_template": "P",
                # 显式 max_retries=1(默认也是 1,这里 explicit 一下)
                "critic": {"max_retries": 1},
            }
        ],
        primary="draft",
    )
    q = _Queue()
    builder = cmp.build_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    graph = builder.compile(checkpointer=InMemorySaver())

    state = _initial_state(skill)
    # 两次产物都准备好(原始 + critic 驱动重派)
    q.queue(task_id=state["task_id"], step_id="draft", ref="oss://d1.txt")
    q.queue(task_id=state["task_id"], step_id="draft", ref="oss://d2.txt")

    config = {"configurable": {"thread_id": f"task:{state['task_id']}"}}
    final = await graph.ainvoke(state, config)

    # max_retries=1 → 2 次派发(原始 + 1 次 critic-driven)
    assert len(q.dispatched) == 2
    # step 不被 critic 拖成 failed — 主流程 graceful pass-through
    assert final["step_results"]["draft"]["status"] == "completed"
    assert final["final_status"] == "completed"
    # critique 落地为最后一轮(失败的)分数 — 给下游 / replanner 看
    crit = final["step_results"]["draft"]["critique"]
    assert crit is not None
    assert crit["score"] == 0.3
    assert crit["should_retry"] is True


# ─────────────────────────────────────────────────────────────────
# 5. step.critic.enabled=true 可在 flag off 时单独开启
# ─────────────────────────────────────────────────────────────────
async def test_step_level_critic_enable_overrides_global_off(monkeypatch) -> None:
    import agents.orchestrator_agent.langgraph_runner.artifact_body as ab
    import agents.orchestrator_agent.langgraph_runner.compiler as cmp
    import agents.orchestrator_agent.langgraph_runner.critic_node as cn

    monkeypatch.setattr(cn, "ENABLE_CRITIC_LOOP", False)  # 全局关
    monkeypatch.setattr(ab, "fetch_artifact_text_excerpt", _fake_fetch_text)

    seen = {"called": False}

    async def fake_eval(**kw):
        seen["called"] = True
        return cn.CritiqueResult(score=0.95, threshold_used=0.7, model_used="m")

    monkeypatch.setattr(cmp, "_critic_evaluate", fake_eval)

    skill = _mk_skill(
        [
            {
                "step_id": "draft",
                "agent": "agent_1",
                # 非默认创作类 task_type → 全局开关也不会启用
                "task_type": "version_compare",
                "prompt_template": "比较",
                "critic": {"enabled": True},  # 显式开启
            }
        ],
        primary="draft",
    )
    q = _Queue()
    builder = cmp.build_state_graph(skill, dispatcher=q.dispatch, result_waiter=q.wait)
    graph = builder.compile(checkpointer=InMemorySaver())

    state = _initial_state(skill)
    q.queue(task_id=state["task_id"], step_id="draft", ref="oss://d.txt")

    config = {"configurable": {"thread_id": f"task:{state['task_id']}"}}
    final = await graph.ainvoke(state, config)

    assert seen["called"] is True
    assert final["step_results"]["draft"]["critique"] is not None
