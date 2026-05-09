"""Eval runner — 把 case 跑出来 + 打分(ADR-027)。

# 设计哲学
不重新实现 task 执行逻辑 — 复用既有 LangGraph compiler / dynamic_compiler。
runner 接受一个 `case_executor`(callable)做实际跑,本身只:
  1. 给每个 case 起一个 fresh task_state
  2. 调 case_executor → 拿到 final_state
  3. 用 metrics.score_case 打分
  4. 聚合成 SuiteReport

# 三种 mode
  - `mock`:LITELLM_MOCK=true,所有 LLM 走 fixture,**完全不连外部** —
           用于 CI 烟雾测试 + 拓扑校验
  - `live`:LITELLM_MOCK=false,真调认知层 + worker — 用于 release 前 E2E
  - `shadow`:5% 真流量旁挂 — S2 + backend 配合,本 runner 不直接支持

# 使用
    from agents.eval import EvalSuite, run_suite
    suite = EvalSuite.from_directory("agents/eval/golden")
    report = await run_suite(suite, mode="mock")
    print(report.summary_text())
    if report.pass_rate < 0.8:
        sys.exit(1)  # CI 卡门槛
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Awaitable, Callable

import structlog

from agents.eval.golden import EvalCase, EvalSuite
from agents.eval.metrics import CaseResult, SuiteReport, aggregate_report, score_case

log = structlog.get_logger(__name__)

#: 单 case 默认硬上限 — 防 CI 跑挂
EVAL_DEFAULT_TIMEOUT_S = int(os.getenv("EVAL_DEFAULT_TIMEOUT_S", "600"))


CaseExecutor = Callable[[EvalCase], Awaitable[dict[str, Any]]]
"""签名:(case) -> final_state(dict);final_state 至少含 step_results / final_status。"""


async def run_case(
    case: EvalCase,
    *,
    executor: CaseExecutor,
    timeout_s: int = EVAL_DEFAULT_TIMEOUT_S,
    keep_raw_state: bool = False,
) -> CaseResult:
    """跑单个 case 并打分。"""
    started = time.monotonic()
    final_state: dict[str, Any]
    try:
        final_state = await asyncio.wait_for(executor(case), timeout=timeout_s)
    except asyncio.TimeoutError:
        elapsed = int((time.monotonic() - started) * 1000)
        log.warning("eval.case.timeout", case_id=case.case_id, timeout_s=timeout_s)
        return CaseResult(
            case_id=case.case_id,
            passed=False,
            score=0.0,
            reasons=[f"timeout after {timeout_s}s"],
            final_status="failed",
            duration_ms=elapsed,
        )
    except Exception as e:
        elapsed = int((time.monotonic() - started) * 1000)
        log.warning("eval.case.exception", case_id=case.case_id, err=str(e)[:200])
        return CaseResult(
            case_id=case.case_id,
            passed=False,
            score=0.0,
            reasons=[f"exception: {str(e)[:200]}"],
            final_status="failed",
            duration_ms=elapsed,
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    result = score_case(case, final_state, duration_ms=duration_ms)
    if keep_raw_state:
        result.raw_state = final_state
    return result


async def run_suite(
    suite: EvalSuite,
    *,
    executor: CaseExecutor | None = None,
    mode: str = "mock",
    timeout_s: int = EVAL_DEFAULT_TIMEOUT_S,
    parallel: int = 1,
    keep_raw_state: bool = False,
) -> SuiteReport:
    """跑整套 suite。

    Args:
        executor: 调用方注入的 case 执行器。若为 None,使用 `mock_executor`
            (默认实现 — 仅用于自检,不接 LangGraph)
        mode: 仅做记录用 — `mock` / `live` / `shadow`
        timeout_s: 单 case 硬上限
        parallel: 并发度(1 = 顺序,>1 用 asyncio.Semaphore)
        keep_raw_state: 是否在 CaseResult 里保留完整 final_state(报告体积↑)
    """
    if not suite.cases:
        log.warning("eval.suite.empty", suite=suite.name)
        return aggregate_report(suite_name=suite.name, results=[])

    exec_fn = executor or _make_mock_executor(mode=mode)

    log.info(
        "eval.suite.run",
        suite=suite.name,
        n_cases=len(suite.cases),
        mode=mode,
        parallel=parallel,
    )

    if parallel <= 1:
        results: list[CaseResult] = []
        for c in suite.cases:
            r = await run_case(
                c, executor=exec_fn, timeout_s=timeout_s, keep_raw_state=keep_raw_state
            )
            results.append(r)
            log.info(
                "eval.case.done",
                case_id=c.case_id,
                passed=r.passed,
                score=r.score,
                duration_ms=r.duration_ms,
            )
    else:
        sem = asyncio.Semaphore(parallel)

        async def _bounded(c: EvalCase) -> CaseResult:
            async with sem:
                return await run_case(
                    c,
                    executor=exec_fn,
                    timeout_s=timeout_s,
                    keep_raw_state=keep_raw_state,
                )

        results = await asyncio.gather(*[_bounded(c) for c in suite.cases])

    return aggregate_report(suite_name=suite.name, results=results)


# ─────────────────────────────────────────────────────────────────
# Mock executor — 自检 / 文档示例用
# ─────────────────────────────────────────────────────────────────
def _make_mock_executor(*, mode: str) -> CaseExecutor:
    """生成一个最小 executor,模拟 case "完美执行"。

    用于 metrics 单测,真实评测应当注入 LangGraph 驱动的 executor。
    """
    async def _exec(case: EvalCase) -> dict[str, Any]:
        expected = case.expected or {}
        must_steps = list(expected.get("must_have_steps") or ["step_a"])
        must_types = list(expected.get("must_have_artifact_types") or ["text"])

        step_results: dict[str, Any] = {}
        for i, sid in enumerate(must_steps):
            atype = must_types[i] if i < len(must_types) else "text"
            step_results[sid] = {
                "step_id": sid,
                "agent_id": "agent_1",
                "task_type": "long_writing",
                "status": "completed",
                "artifact_ref": f"oss://mock/{sid}",
                "artifact_type": atype,
                "duration_ms": 100,
                "cost_usd": 0.001,
                "critique": None,
            }
        return {
            "task_id": f"mock-{case.case_id}",
            "skill_id": None,
            "step_results": step_results,
            "final_status": "completed",
            "primary_artifact_ref": f"oss://mock/{must_steps[-1]}",
        }

    return _exec
