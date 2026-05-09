"""LangGraph 状态 schema。

设计:
- 大产物用引用(铁律 4):state 里只存 OSS ref,不存 bytes
- step 状态用 Annotated reducer 合并(允许多个节点并发更新同一个 step_results 字典)
- 整个 state 可被 PostgresSaver 序列化
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict
from uuid import UUID

from langgraph.graph.message import add_messages

StepStatus = Literal["pending", "running", "completed", "failed", "pending_external", "rolled_back"]


def _merge_dicts(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """同步多个并发 step 更新 step_results 时的 reducer。"""
    out = dict(a)
    out.update(b)
    return out


def _max_step_dispatch_counts(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    out = dict(a or {})
    for k, v in (b or {}).items():
        vv = int(v) if v is not None else 0
        out[k] = max(out.get(k, 0), vv)
    return out


def _max_int(a: int | None, b: int | None) -> int:
    """rollback_count 取最大值(防止并发更新冲突)。"""
    return max(a or 0, b or 0)


class StepResult(TypedDict, total=False):
    """单个 step 的产物快照(引用,不是 bytes)。"""

    step_id: str
    agent_id: str
    task_type: str
    status: StepStatus
    artifact_ref: str | None  # oss://...
    artifact_type: str | None
    artifact_metadata: dict[str, Any]
    duration_ms: int | None
    cost_usd: float | None
    model_used: str | None
    error_detail: dict[str, Any] | None
    started_at: str | None  # iso
    completed_at: str | None
    #: ADR-020 Critic Loop 评审结果(critic_node.CritiqueResult.to_dict())
    #: None 表示该 step 未启用 critic;dict 表示已评审,passed/score/issues/...
    critique: dict[str, Any] | None


class TaskState(TypedDict, total=False):
    """LangGraph 任务状态 — 整个会被 PostgresSaver checkpoint。

    设计原则:
    - **小**:大产物落 OSS,这里只存 ref
    - **可合并**:并发节点写 step_results 不冲突(reducer 处理)
    - **time-travel 友好**:state 可由 graph.update_state(checkpoint_id, ...) 重写
    """

    # 不变量(进入 graph 时设好,不变)
    task_id: str  # UUID str(JSON 友好)
    user_id: str
    conversation_id: str
    skill_id: str | None
    skill_version: str | None
    skill_yaml: dict[str, Any]  # 反序列化的 Skill 定义,checkpoint 含 = 复现可信
    collected_fields: dict[str, Any]

    # 运行期累积(多节点写)
    step_results: Annotated[dict[str, StepResult], _merge_dicts]

    # HITL gates 已开/已关(interrupt 唤醒后写入)
    hitl_decisions: Annotated[dict[str, dict[str, Any]], _merge_dicts]

    # 计数器
    rollback_count: Annotated[int, _max_int]
    #: 每 step 累计 dispatch 次数(含失败重试);用于可观测与幂等调试
    step_dispatch_counts: Annotated[dict[str, int], _max_step_dispatch_counts]

    # ── 编排可观测性 ──
    #: 单次「工作流执行」稳定 ID(跨多 step 任务相同)
    orchestration_run_id: str
    #: 32-hex W3C-compatible trace id(与 OpenTelemetry 对齐时可外接)
    trace_id: str

    # 终止标记
    final_status: StepStatus | None
    failure_reason: str | None
    primary_artifact_ref: str | None
    primary_artifact_id: str | None  # DB Artifact.id(完成后写回)

    # 节点日志(用于 Reflexion + UI 时间线)
    messages: Annotated[list, add_messages]


def make_initial_state(
    *,
    task_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    skill_id: UUID | None,
    skill_version: str | None,
    skill_yaml: dict[str, Any],
    collected_fields: dict[str, Any],
    orchestration_run_id: UUID | None = None,
    trace_id: str | None = None,
) -> TaskState:
    from uuid import uuid4

    rid = str(orchestration_run_id or uuid4())
    tid = (trace_id or uuid4().hex)[:32]
    return TaskState(
        task_id=str(task_id),
        user_id=str(user_id),
        conversation_id=str(conversation_id),
        skill_id=str(skill_id) if skill_id else None,
        skill_version=skill_version,
        skill_yaml=skill_yaml,
        collected_fields=collected_fields,
        step_results={},
        hitl_decisions={},
        rollback_count=0,
        step_dispatch_counts={},
        orchestration_run_id=rid,
        trace_id=tid,
        final_status=None,
        failure_reason=None,
        primary_artifact_ref=None,
        primary_artifact_id=None,
        messages=[],
    )
