"""Eval 评测体系(ADR-027)。

# 角色
持续在已知"黄金任务集"上跑系统,产出质量 / 成本 / 延迟报告。
飞轮的"测量"端 — 没有 eval 就没有进步。

# 用法
    from agents.eval import EvalSuite, run_suite

    suite = EvalSuite.from_directory("agents/eval/golden")
    report = await run_suite(suite, mode="mock")  # 或 "live"
    print(report.summary_text())
"""

from agents.eval.golden import (
    EvalCase,
    EvalSuite,
    SuiteLoadError,
)
from agents.eval.metrics import (
    CaseResult,
    SuiteReport,
    score_case,
)
from agents.eval.runner import run_case, run_suite

__all__ = [
    "CaseResult",
    "EvalCase",
    "EvalSuite",
    "SuiteLoadError",
    "SuiteReport",
    "run_case",
    "run_suite",
    "score_case",
]
