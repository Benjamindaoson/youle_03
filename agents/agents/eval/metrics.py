"""Eval 指标(ADR-027)。

# 单 case 评分
对一次执行结果(`final_state`)打分:
  - must_have_steps:expected 列出的 step 是否都 completed
  - must_have_artifact_types:产物类型覆盖率
  - primary_artifact_step:主产物 step 是否对
  - max_total_cost_usd / max_p95_duration_s:硬上限
  - must_pass_critic:是否所有创作 step 的 critique 都 pass

# Suite 报告
聚合 N 个 case 的:
  - pass_rate(0..1)
  - 平均 / P95 cost / duration
  - critic 触发率 / 通过率
  - 失败原因分布
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseResult:
    """单 case 的执行 + 评分结果。"""

    case_id: str
    passed: bool
    score: float  # 0..1
    reasons: list[str] = field(default_factory=list)  # 失败原因 / 警告

    # 执行测量
    final_status: str | None = None
    duration_ms: int | None = None
    total_cost_usd: float | None = None
    n_steps_completed: int = 0
    n_steps_failed: int = 0
    n_critic_evaluated: int = 0
    n_critic_passed: int = 0

    raw_state: dict[str, Any] | None = None  # 调试用,生产产报告时去掉


@dataclass
class SuiteReport:
    """一组 case 的聚合报告。"""

    suite_name: str
    n_cases: int
    n_passed: int
    pass_rate: float
    avg_score: float
    cost_p50: float | None = None
    cost_p95: float | None = None
    duration_p50_ms: int | None = None
    duration_p95_ms: int | None = None
    critic_eval_count: int = 0
    critic_pass_count: int = 0
    cases: list[CaseResult] = field(default_factory=list)

    def summary_text(self) -> str:
        cp50 = f"${self.cost_p50:.4f}" if self.cost_p50 is not None else "-"
        cp95 = f"${self.cost_p95:.4f}" if self.cost_p95 is not None else "-"
        dp50 = f"{self.duration_p50_ms}ms" if self.duration_p50_ms is not None else "-"
        dp95 = f"{self.duration_p95_ms}ms" if self.duration_p95_ms is not None else "-"
        crit = (
            f"{self.critic_pass_count}/{self.critic_eval_count}"
            if self.critic_eval_count
            else "n/a"
        )
        lines = [
            f"# Eval Report: {self.suite_name}",
            f"  cases:        {self.n_cases}",
            f"  passed:       {self.n_passed} ({self.pass_rate:.1%})",
            f"  avg_score:    {self.avg_score:.3f}",
            f"  cost p50/p95: {cp50} / {cp95}",
            f"  dur  p50/p95: {dp50} / {dp95}",
            f"  critic pass:  {crit}",
            "",
            "## Failed cases:",
        ]
        for r in self.cases:
            if r.passed:
                continue
            lines.append(f"  - {r.case_id} (score={r.score:.2f}) — {'; '.join(r.reasons[:3])}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# 评分
# ─────────────────────────────────────────────────────────────────
def score_case(
    case,  # EvalCase — 不强 import 防止循环
    final_state: dict[str, Any],
    *,
    duration_ms: int | None = None,
) -> CaseResult:
    """对一次执行打分。"""
    reasons: list[str] = []
    weights: list[tuple[str, float, float]] = []  # (rule_name, weight, score)

    expected = case.expected or {}
    budget = case.budget or {}
    step_results: dict[str, Any] = final_state.get("step_results") or {}

    n_completed = sum(
        1 for r in step_results.values()
        if isinstance(r, dict) and r.get("status") == "completed"
    )
    n_failed = sum(
        1 for r in step_results.values()
        if isinstance(r, dict) and r.get("status") == "failed"
    )
    final_status = final_state.get("final_status")

    # ── 规则 1:final_status == "completed" ──
    rule1 = 1.0 if final_status == "completed" else 0.0
    weights.append(("final_completed", 0.35, rule1))
    if rule1 < 1.0:
        reasons.append(f"final_status={final_status!r}")

    # ── 规则 2:must_have_steps 全 completed ──
    must_steps = list(expected.get("must_have_steps") or [])
    if must_steps:
        missing = [
            s for s in must_steps
            if (step_results.get(s) or {}).get("status") != "completed"
        ]
        rule2 = 1.0 if not missing else 1.0 - len(missing) / len(must_steps)
        weights.append(("must_have_steps", 0.25, rule2))
        if missing:
            reasons.append(f"missing_steps={missing}")

    # ── 规则 3:must_have_artifact_types 覆盖 ──
    must_types = list(expected.get("must_have_artifact_types") or [])
    if must_types:
        present = {
            r.get("artifact_type")
            for r in step_results.values()
            if isinstance(r, dict)
        }
        missing_t = [t for t in must_types if t not in present]
        rule3 = 1.0 if not missing_t else 1.0 - len(missing_t) / len(must_types)
        weights.append(("must_have_artifact_types", 0.10, rule3))
        if missing_t:
            reasons.append(f"missing_artifact_types={missing_t}")

    # ── 规则 4:primary_artifact_step ──
    primary = expected.get("primary_artifact_step")
    if primary:
        rule4 = (
            1.0
            if (step_results.get(primary) or {}).get("status") == "completed"
            else 0.0
        )
        weights.append(("primary_artifact", 0.10, rule4))
        if rule4 < 1.0:
            reasons.append(f"primary_artifact_not_completed: {primary}")

    # ── 规则 5:cost 上限 ──
    total_cost = _sum_cost(step_results)
    cost_cap = budget.get("total_cost_usd") or expected.get("max_total_cost_usd")
    if cost_cap is not None and total_cost is not None:
        cap = float(cost_cap)
        rule5 = 1.0 if total_cost <= cap else max(0.0, 1.0 - (total_cost - cap) / cap)
        weights.append(("cost_cap", 0.10, rule5))
        if rule5 < 1.0:
            reasons.append(f"cost_over: ${total_cost:.4f} > ${cap:.4f}")

    # ── 规则 6:duration 上限 ──
    dur_cap_s = budget.get("total_duration_s") or expected.get("max_p95_duration_s")
    if dur_cap_s is not None and duration_ms is not None:
        cap_ms = float(dur_cap_s) * 1000
        rule6 = 1.0 if duration_ms <= cap_ms else max(0.0, 1.0 - (duration_ms - cap_ms) / cap_ms)
        weights.append(("duration_cap", 0.05, rule6))
        if rule6 < 1.0:
            reasons.append(f"duration_over: {duration_ms}ms > {cap_ms:.0f}ms")

    # ── 规则 7:must_pass_critic ──
    n_crit_eval, n_crit_pass = _count_critic_passes(step_results)
    if expected.get("must_pass_critic"):
        rule7 = (
            1.0 if n_crit_eval == 0 else (n_crit_pass / n_crit_eval)
        )
        weights.append(("critic_pass", 0.05, rule7))
        if rule7 < 1.0:
            reasons.append(f"critic_pass_rate={n_crit_pass}/{n_crit_eval}")

    # ── 加权 ──
    if not weights:
        score = 0.0
        passed = False
    else:
        total_w = sum(w for _, w, _ in weights)
        score = sum(w * s for _, w, s in weights) / total_w if total_w else 0.0
        passed = score >= float(expected.get("min_score", 0.7)) and final_status == "completed"

    return CaseResult(
        case_id=case.case_id,
        passed=passed,
        score=round(score, 4),
        reasons=reasons,
        final_status=final_status,
        duration_ms=duration_ms,
        total_cost_usd=total_cost,
        n_steps_completed=n_completed,
        n_steps_failed=n_failed,
        n_critic_evaluated=n_crit_eval,
        n_critic_passed=n_crit_pass,
        raw_state=None,  # 默认不暴露 — 报告处理外面置回
    )


def aggregate_report(*, suite_name: str, results: list[CaseResult]) -> SuiteReport:
    n = len(results)
    n_pass = sum(1 for r in results if r.passed)
    avg_score = sum(r.score for r in results) / n if n else 0.0
    costs = [r.total_cost_usd for r in results if r.total_cost_usd is not None]
    durs = [r.duration_ms for r in results if r.duration_ms is not None]
    return SuiteReport(
        suite_name=suite_name,
        n_cases=n,
        n_passed=n_pass,
        pass_rate=(n_pass / n) if n else 0.0,
        avg_score=round(avg_score, 4),
        cost_p50=_percentile(costs, 50),
        cost_p95=_percentile(costs, 95),
        duration_p50_ms=int(_percentile(durs, 50) or 0) if durs else None,
        duration_p95_ms=int(_percentile(durs, 95) or 0) if durs else None,
        critic_eval_count=sum(r.n_critic_evaluated for r in results),
        critic_pass_count=sum(r.n_critic_passed for r in results),
        cases=results,
    )


# ─────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────
def _sum_cost(step_results: dict[str, Any]) -> float | None:
    total: float = 0.0
    seen = False
    for r in step_results.values():
        if not isinstance(r, dict):
            continue
        c = r.get("cost_usd")
        if c is None:
            continue
        try:
            total += float(c)
            seen = True
        except (TypeError, ValueError):
            continue
    return total if seen else None


def _count_critic_passes(step_results: dict[str, Any]) -> tuple[int, int]:
    n_eval = 0
    n_pass = 0
    for r in step_results.values():
        if not isinstance(r, dict):
            continue
        critique = r.get("critique")
        if not isinstance(critique, dict):
            continue
        if critique.get("skipped_reason"):
            continue  # critic 跳过不计
        n_eval += 1
        try:
            score = float(critique.get("score") or 0.0)
            th = float(critique.get("threshold_used") or 0.7)
            if score >= th:
                n_pass += 1
        except (TypeError, ValueError):
            continue
    return n_eval, n_pass


def _percentile(values: list[float], p: int) -> float | None:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(s[int(k)])
    return float(s[f] + (s[c] - s[f]) * (k - f))
