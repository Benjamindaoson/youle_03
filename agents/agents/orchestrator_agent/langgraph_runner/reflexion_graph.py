"""Reflexion 飞轮的 LangGraph 化 — 替代 flywheel/reflexion/runner.py 的单步循环。

把 "失败 trace → 根因 → 改进建议 → 落库" 拆成 3 节点 graph,关键收益:
  1. **可中间停**:LLM 调用失败 → checkpoint 保留,人工排查后 ainvoke(None) 续跑
  2. **可单步重试**:只重跑 propose_fix 节点,不重做 root_cause analysis
  3. **状态可观测**:每个 reflexion 实例的 thread_id = task_id,UI 可拉历史

调用方:flywheel runner 拿到一条 reflexion 事件 → process_reflexion_event(payload)
内部:invoke graph(thread_id=task_id),checkpointer 自动持久化中间产物。
"""

from __future__ import annotations

import json
from typing import Annotated, Any, TypedDict
from uuid import UUID, uuid4

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.config.prompts import REFLEXION_SYSTEM_PROMPT
from app.db import SessionLocal
from app.models.prompt_improvement import PromptImprovementCandidate
from app.router import complete

log = structlog.get_logger(__name__)


class ReflexionState(TypedDict, total=False):
    task_id: str
    prompt_name: str
    trace_excerpt: str
    failure_reason: str
    # 节点输出
    root_cause: str | None
    proposed_changes: str | None
    section_to_improve: str | None
    current_text: str | None
    expected_improvement: str | None
    candidate_id: str | None
    # 错误标记(失败时由节点写入,父调用判断)
    error: str | None
    messages: Annotated[list, add_messages]


# ─── 节点 1:LLM 根因 + 修复建议 ───
async def _llm_analyze(state: ReflexionState) -> dict[str, Any]:
    """跑 LLM 输出 JSON。失败时只标 error,checkpoint 保留供续跑。"""
    if state.get("root_cause"):
        return {}  # 已分析过,checkpoint resume 时不重做
    user_msg = (
        f"任务 ID:{state.get('task_id')}\n"
        f"使用的 prompt:{state.get('prompt_name')}\n"
        f"失败原因:{state.get('failure_reason')}\n"
        f"轨迹片段:\n{state.get('trace_excerpt')}"
    )
    try:
        resp = await complete(
            task_type="brief_update",
            messages=[
                {"role": "system", "content": REFLEXION_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=600,
        )
        data = json.loads(resp.content)
    except Exception as e:
        log.warning("reflexion.llm_failed", err=str(e))
        return {"error": f"llm_failed:{e}"}
    return {
        "root_cause": data.get("root_cause"),
        "section_to_improve": data.get("section_to_improve"),
        "current_text": data.get("current_text"),
        "proposed_changes": data.get("proposed_changes"),
        "expected_improvement": data.get("expected_improvement"),
    }


# ─── 节点 2:校验(必填字段)───
async def _validate(state: ReflexionState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    if not state.get("root_cause") or not state.get("proposed_changes"):
        return {"error": "validation_failed:missing root_cause or proposed_changes"}
    return {}


# ─── 节点 3:落库 ───
async def _persist(state: ReflexionState) -> dict[str, Any]:
    if state.get("error") or state.get("candidate_id"):
        return {}
    async with SessionLocal() as session:
        cand = PromptImprovementCandidate(
            id=uuid4(),
            prompt_name=state.get("prompt_name") or "unknown",
            failure_task_id=UUID(state["task_id"]) if state.get("task_id") else None,
            root_cause=state.get("root_cause"),
            section_to_improve=state.get("section_to_improve"),
            current_text=state.get("current_text"),
            proposed_changes=state.get("proposed_changes"),
            expected_improvement=state.get("expected_improvement"),
            status="pending",
        )
        session.add(cand)
        await session.commit()
        log.info(
            "reflexion.candidate_written",
            candidate_id=str(cand.id),
            prompt_name=state.get("prompt_name"),
        )
        return {"candidate_id": str(cand.id)}


def _branch(state: ReflexionState) -> str:
    """error 直接终止,否则 持续推进。"""
    if state.get("error"):
        return END
    if not state.get("root_cause"):
        return END  # 安全 fallback
    if state.get("candidate_id"):
        return END
    return "persist"


# ─── 构图 ───
def build_reflexion_graph(checkpointer=None):
    builder = StateGraph(ReflexionState)
    builder.add_node("analyze", _llm_analyze)
    builder.add_node("validate", _validate)
    builder.add_node("persist", _persist)
    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "validate")
    builder.add_conditional_edges("validate", _branch, ["persist", END])
    builder.add_edge("persist", END)
    return builder.compile(checkpointer=checkpointer)


# 进程级单例(由 flywheel runner 复用)
_GRAPH = None


def get_reflexion_graph():
    """复用全局 LangGraph checkpointer(与主任务图共用 PostgresSaver)。"""
    global _GRAPH
    if _GRAPH is None:
        from agents.orchestrator_agent.langgraph_runner.runner import get_checkpointer

        _GRAPH = build_reflexion_graph(checkpointer=get_checkpointer())
    return _GRAPH


async def process_reflexion_event(payload: dict[str, Any]) -> dict[str, Any]:
    """flywheel runner 调用入口。每条 reflexion 事件用 task_id 作 thread_id。"""
    graph = get_reflexion_graph()
    task_id = str(payload.get("task_id") or uuid4())
    config = {"configurable": {"thread_id": f"reflexion:{task_id}"}}
    initial: ReflexionState = {
        "task_id": task_id,
        "prompt_name": payload.get("prompt_name") or "unknown",
        "trace_excerpt": payload.get("trace_excerpt") or "",
        "failure_reason": payload.get("failure_reason") or "",
        "messages": [],
    }
    final = await graph.ainvoke(initial, config)
    return {
        "candidate_id": final.get("candidate_id"),
        "error": final.get("error"),
        "thread_id": config["configurable"]["thread_id"],
    }
