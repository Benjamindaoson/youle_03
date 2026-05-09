"""Critique → Reflexion 飞轮桥接(ADR-G,接 ADR-020 + ADR-011)。

# 目的
ADR-020 的 Critic Loop 把"完成但低质量"这种宝贵中间态落到了
`step_result["critique"]`,但**没有人在消费它**。
Reflexion(`reflexion_graph.py`)只看任务级 `failed`,产出
`prompt_improvement_candidates`。

本文件把两者**桥接**:
    1. 扫 TaskState.step_results,提取低分 critique signals
    2. 转换为与 Reflexion 兼容的 payload(prompt_name + failure_reason + trace_excerpt)
    3. 通过 `flywheel_emitter.emit(signal_type="reflexion", payload=...)` 入队
       — 与现有失败路径走同一个 stream,下游消费者零改动

# 飞轮闭环
    Critic 评低分 → step_result["critique"] 落库
        ↓
    本文件:critique_signal scan + emit
        ↓
    flywheel:signals (Redis Stream)
        ↓
    flywheel_consumer 路由到 flywheel:reflexion stream
        ↓
    backend 的 reflexion runner 调 process_reflexion_event(payload)
        ↓
    LangGraph reflexion_graph(LLM 根因 → 改进建议)
        ↓
    prompt_improvement_candidates 表(待人工审核)
        ↓
    晋升器(S2)发现"同类改进多次成功"→ 自动上线

# 设计选择
- **不直接改 reflexion_graph.py**:它对 failure_reason / trace_excerpt 的契约
  就能接住 critique payload —— 加一个 `source` 标记区分来源就够了。
- **不直接调 process_reflexion_event**:那会引入 backend deps
  (app.db / app.models),违反 agents-only 边界。走 Redis stream 解耦。
- **graceful**:Redis 不可用 → 静默放弃这条信号,不抛
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger(__name__)

#: 进入 Reflexion 的最低评分门槛 — 比 critic 自己的 threshold 更严
#: 防止 critic_threshold=0.7 时大量 0.65 的小波动被当作可改进信号
REFLEXION_FROM_CRITIQUE_MAX_SCORE = float(
    os.getenv("REFLEXION_FROM_CRITIQUE_MAX_SCORE", "0.6")
)

#: 单任务一次性 emit 多少个 critique 信号(防雪崩)
REFLEXION_FROM_CRITIQUE_MAX_PER_TASK = int(
    os.getenv("REFLEXION_FROM_CRITIQUE_MAX_PER_TASK", "5")
)

#: 信号 source 标记 — backend 的 reflexion runner 据此区分 failed vs critic_low_score
SIGNAL_SOURCE_CRITIC_LOW_SCORE = "critic_low_score"


# ─────────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────────
@dataclass
class CritiqueSignal:
    """从单个 step 提取的 critic-driven 飞轮信号。"""

    task_id: str
    step_id: str
    task_type: str
    skill_id: str | None
    score: float
    threshold: float
    issues: list[str] = field(default_factory=list)
    suggestion: str = ""
    artifact_ref: str | None = None
    rendered_prompt_excerpt: str | None = None  # step prompt(若可拿)

    @property
    def prompt_name(self) -> str:
        """与 reflexion_graph.ReflexionState.prompt_name 对齐。

        命名约定:
            {skill_id 或 'dynamic'}::step_{step_id}::{task_type}
        """
        skill_part = self.skill_id or "dynamic"
        return f"{skill_part}::step_{self.step_id}::{self.task_type}"

    def failure_reason(self) -> str:
        """合成"失败原因"给 reflexion 的 LLM。"""
        issues_str = "; ".join(self.issues[:5]) if self.issues else "(critic 未列出具体问题)"
        return (
            f"[critic_low_score] score={self.score:.2f} < threshold={self.threshold:.2f}\n"
            f"issues: {issues_str}\n"
            f"suggestion: {self.suggestion[:300] or '(critic 无明确改进方向)'}"
        )

    def trace_excerpt(self) -> str:
        """给 reflexion 的 LLM 看的上下文片段。"""
        parts: list[str] = []
        parts.append(f"step_id: {self.step_id}")
        parts.append(f"task_type: {self.task_type}")
        if self.artifact_ref:
            parts.append(f"artifact_ref: {self.artifact_ref}")
        if self.rendered_prompt_excerpt:
            excerpt = self.rendered_prompt_excerpt[:1500]
            parts.append(f"--- rendered prompt (excerpt) ---\n{excerpt}")
        if self.issues:
            parts.append("--- critic issues ---\n" + "\n".join(f"- {x}" for x in self.issues))
        if self.suggestion:
            parts.append(f"--- critic suggestion ---\n{self.suggestion}")
        return "\n".join(parts)

    def to_reflexion_payload(self) -> dict[str, Any]:
        """转换为与 process_reflexion_event() 兼容的 payload。

        多了一个 `source` 字段,backend reflexion runner 应该转写到
        `prompt_improvement_candidates.source`(或 metadata)用于
        后续切片成本 / 晋升策略(critic 来源 vs failed 来源可以不同处理)。
        """
        return {
            "task_id": self.task_id,
            "prompt_name": self.prompt_name,
            "failure_reason": self.failure_reason(),
            "trace_excerpt": self.trace_excerpt(),
            "source": SIGNAL_SOURCE_CRITIC_LOW_SCORE,
            "metadata": {
                "step_id": self.step_id,
                "task_type": self.task_type,
                "skill_id": self.skill_id,
                "score": self.score,
                "threshold": self.threshold,
                "n_issues": len(self.issues),
            },
        }


# ─────────────────────────────────────────────────────────────────
# 提取
# ─────────────────────────────────────────────────────────────────
def extract_critique_signals(
    *,
    task_id: str,
    skill_id: str | None,
    step_results: dict[str, Any],
    collected_fields: dict[str, Any] | None = None,
    max_score: float = REFLEXION_FROM_CRITIQUE_MAX_SCORE,
    max_signals: int = REFLEXION_FROM_CRITIQUE_MAX_PER_TASK,
) -> list[CritiqueSignal]:
    """从 TaskState 的 step_results 中提取低分 critique 信号。

    Args:
        task_id: TaskState["task_id"]
        skill_id: TaskState["skill_id"](可空 — 动态 plan 路径)
        step_results: TaskState["step_results"]
        collected_fields: TaskState["collected_fields"](用于丰富 trace)
        max_score: 严于 critic threshold,默认 0.6
        max_signals: 单任务上限

    Returns:
        list[CritiqueSignal] — 按 score 升序(最差的优先 reflexion)
    """
    if not isinstance(step_results, dict):
        return []

    candidates: list[CritiqueSignal] = []
    for sid, sr in step_results.items():
        if not isinstance(sr, dict):
            continue
        # 必须是 completed 状态(failed 走原有 reflexion 路径,不重复)
        if sr.get("status") != "completed":
            continue
        critique = sr.get("critique")
        if not isinstance(critique, dict):
            continue
        # critic 自己跳过的(skipped_reason)不视为信号
        if critique.get("skipped_reason"):
            continue
        try:
            score = float(critique.get("score") or 0.0)
            threshold = float(critique.get("threshold_used") or 0.7)
        except (TypeError, ValueError):
            continue
        if score >= max_score:
            continue

        signal = CritiqueSignal(
            task_id=str(task_id),
            step_id=str(sid),
            task_type=str(sr.get("task_type") or "unknown"),
            skill_id=str(skill_id) if skill_id else None,
            score=score,
            threshold=threshold,
            issues=_normalize_str_list(critique.get("issues")),
            suggestion=str(critique.get("suggestion") or "")[:600],
            artifact_ref=sr.get("artifact_ref"),
            rendered_prompt_excerpt=_render_prompt_excerpt(sr, collected_fields or {}),
        )
        candidates.append(signal)

    # 按 score 升序(分越低,越值得 reflexion)
    candidates.sort(key=lambda c: c.score)
    return candidates[:max_signals]


# ─────────────────────────────────────────────────────────────────
# 发射
# ─────────────────────────────────────────────────────────────────
async def emit_critique_signals(signals: list[CritiqueSignal]) -> int:
    """把信号 push 到 flywheel:signals stream。返回实际入队数。

    Graceful:Redis 不可用 / emit 抛异常 → 跳过该信号 + log,**不抛**。
    """
    if not signals:
        return 0

    # 延迟导入 flywheel_emitter 以避免单测时强制 redis 依赖
    try:
        from agents._common.flywheel_emitter import emit as _flywheel_emit
    except Exception as e:
        log.warning("critique_signal.emitter_unavailable", err=str(e)[:200])
        return 0

    success = 0
    for sig in signals:
        payload = sig.to_reflexion_payload()
        try:
            await _flywheel_emit(signal_type="reflexion", payload=payload)
            success += 1
            log.info(
                "critique_signal.emitted",
                task_id=sig.task_id,
                step_id=sig.step_id,
                score=sig.score,
                source=SIGNAL_SOURCE_CRITIC_LOW_SCORE,
            )
        except Exception as e:
            log.warning(
                "critique_signal.emit_fail",
                task_id=sig.task_id,
                step_id=sig.step_id,
                err=str(e)[:200],
            )
    return success


async def scan_and_emit_from_state(
    state: dict[str, Any],
    *,
    max_score: float = REFLEXION_FROM_CRITIQUE_MAX_SCORE,
    max_signals: int = REFLEXION_FROM_CRITIQUE_MAX_PER_TASK,
) -> int:
    """便利函数:一次完成 extract + emit。

    在任务完成后调用一次即可。返回实际 emit 的信号数。
    """
    task_id = state.get("task_id")
    if not task_id:
        return 0
    signals = extract_critique_signals(
        task_id=str(task_id),
        skill_id=state.get("skill_id"),
        step_results=state.get("step_results") or {},
        collected_fields=state.get("collected_fields"),
        max_score=max_score,
        max_signals=max_signals,
    )
    if not signals:
        return 0
    return await emit_critique_signals(signals)


# ─────────────────────────────────────────────────────────────────
# 内部
# ─────────────────────────────────────────────────────────────────
def _normalize_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v[:300]] if v.strip() else []
    if isinstance(v, list):
        return [str(x)[:300] for x in v if str(x).strip()]
    return []


def _render_prompt_excerpt(
    step_result: dict[str, Any],
    collected_fields: dict[str, Any],
) -> str | None:
    """尽量给 reflexion 一份"产物当时是怎么生成的"片段。

    我们没存渲染后的 prompt(那在 worker 端,完成后已扔),所以只能拼:
        1. inputs 里的 _prompt(若 worker 完成时回传 — 通常没有)
        2. error_detail 里的 prompt 信息
        3. critique 里的 issues / suggestion(由调用方另外拼)
    退化:返回包含 task_type + collected_fields 的简短描述。
    """
    parts: list[str] = []
    if collected_fields:
        try:
            cf_json = json.dumps(collected_fields, ensure_ascii=False, default=str)[:800]
            parts.append(f"collected_fields: {cf_json}")
        except (TypeError, ValueError):
            pass
    if step_result.get("error_detail"):
        try:
            ed = json.dumps(step_result["error_detail"], ensure_ascii=False)[:400]
            parts.append(f"error_detail: {ed}")
        except (TypeError, ValueError):
            pass
    return "\n".join(parts) if parts else None
