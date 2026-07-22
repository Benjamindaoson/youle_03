"""Eval 体系测试(ADR-027)。

覆盖:
- EvalSuite.from_directory 加载 + 缺字段 / 坏 YAML 跳过
- score_case 各规则
- run_case 异常 / 超时
- run_suite 聚合 + parallel
- 真仓库 agents/eval/golden/ 至少有 1 个 case 且都能解析
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agents.eval import (
    CaseResult,
    EvalCase,
    EvalSuite,
    SuiteReport,
    run_case,
    run_suite,
    score_case,
)
from agents.eval.metrics import aggregate_report

REPO_GOLDEN = Path(__file__).resolve().parents[3] / "agents" / "eval" / "golden"


# ─── 加载 ───
def test_load_suite_from_directory(tmp_path) -> None:
    (tmp_path / "case_a.yaml").write_text(
        "case_id: a\n"
        "input:\n"
        "  user_request: hello\n",
        encoding="utf-8",
    )
    suite = EvalSuite.from_directory(tmp_path)
    assert suite.name == tmp_path.name
    assert len(suite.cases) == 1
    assert suite.cases[0].case_id == "a"


def test_load_skips_invalid(tmp_path) -> None:
    (tmp_path / "ok.yaml").write_text(
        "case_id: ok\ninput:\n  user_request: x\n", encoding="utf-8"
    )
    (tmp_path / "no_id.yaml").write_text(
        "input:\n  user_request: x\n", encoding="utf-8"
    )
    (tmp_path / "no_request.yaml").write_text(
        "case_id: noreq\ninput: {}\n", encoding="utf-8"
    )
    (tmp_path / "broken.yaml").write_text("case_id: x\n  bad: : yaml", encoding="utf-8")

    suite = EvalSuite.from_directory(tmp_path)
    ids = {c.case_id for c in suite.cases}
    assert ids == {"ok"}


def test_missing_dir_returns_empty(tmp_path) -> None:
    suite = EvalSuite.from_directory(tmp_path / "nope")
    assert suite.cases == []


def test_filter_by_tag(tmp_path) -> None:
    (tmp_path / "a.yaml").write_text(
        "case_id: a\ntags: [hero]\ninput:\n  user_request: x\n", encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        "case_id: b\ntags: [smoke]\ninput:\n  user_request: x\n", encoding="utf-8"
    )
    suite = EvalSuite.from_directory(tmp_path)
    sub = suite.filter_by_tag("hero")
    assert {c.case_id for c in sub.cases} == {"a"}


# ─── score_case 规则 ───
def _case(**kw):
    base = {
        "case_id": "t",
        "user_request": "x",
        "expected": {},
        "budget": {},
    }
    base.update(kw)
    return EvalCase(**base)


def test_score_perfect_run() -> None:
    case = _case(
        expected={
            "must_have_steps": ["a", "b"],
            "primary_artifact_step": "b",
            "min_score": 0.7,
        }
    )
    final = {
        "final_status": "completed",
        "step_results": {
            "a": {"status": "completed", "artifact_type": "text", "cost_usd": 0.001},
            "b": {"status": "completed", "artifact_type": "text", "cost_usd": 0.002},
        },
    }
    r = score_case(case, final, duration_ms=1000)
    assert r.passed is True
    assert r.score >= 0.9


def test_score_missing_step_fails() -> None:
    case = _case(expected={"must_have_steps": ["a", "b", "c"]})
    final = {
        "final_status": "completed",
        "step_results": {
            "a": {"status": "completed"},
            "b": {"status": "completed"},
            # c 缺
        },
    }
    r = score_case(case, final, duration_ms=100)
    assert r.score < 1.0
    assert any("missing_steps" in reason for reason in r.reasons)


def test_score_failed_status_fails() -> None:
    case = _case(expected={"must_have_steps": ["a"]})
    final = {"final_status": "failed", "step_results": {"a": {"status": "completed"}}}
    r = score_case(case, final, duration_ms=100)
    assert r.passed is False
    assert any("final_status" in x for x in r.reasons)


def test_score_cost_over_budget() -> None:
    case = _case(budget={"total_cost_usd": 1.0})
    final = {
        "final_status": "completed",
        "step_results": {
            "a": {"status": "completed", "cost_usd": 5.0},
        },
    }
    r = score_case(case, final, duration_ms=100)
    assert any("cost_over" in x for x in r.reasons)


def test_score_critic_failures_count() -> None:
    case = _case(expected={"must_pass_critic": True})
    final = {
        "final_status": "completed",
        "step_results": {
            "a": {
                "status": "completed",
                "critique": {
                    "score": 0.4,
                    "threshold_used": 0.7,
                },
            },
            "b": {
                "status": "completed",
                "critique": {
                    "score": 0.9,
                    "threshold_used": 0.7,
                },
            },
        },
    }
    r = score_case(case, final, duration_ms=100)
    assert r.n_critic_evaluated == 2
    assert r.n_critic_passed == 1
    assert any("critic_pass_rate" in x for x in r.reasons)


def test_score_skipped_critic_not_counted() -> None:
    """skipped critic(故障/不适用)不计入评估。"""
    case = _case(expected={"must_pass_critic": True})
    final = {
        "final_status": "completed",
        "step_results": {
            "a": {
                "status": "completed",
                "critique": {
                    "score": 0.0,
                    "threshold_used": 0.7,
                    "skipped_reason": "non-text artifact",
                },
            }
        },
    }
    r = score_case(case, final, duration_ms=100)
    assert r.n_critic_evaluated == 0
    assert r.n_critic_passed == 0


# ─── run_case ───
async def test_run_case_executor_exception_caught() -> None:
    case = _case(case_id="boom", expected={"must_have_steps": ["a"]})

    async def _bad_exec(c: EvalCase) -> dict[str, Any]:
        raise RuntimeError("explode")

    r = await run_case(case, executor=_bad_exec)
    assert r.passed is False
    assert r.score == 0.0
    assert any("exception" in x for x in r.reasons)


async def test_run_case_timeout_handled() -> None:
    case = _case(case_id="slow")

    async def _slow(c: EvalCase) -> dict[str, Any]:
        await asyncio.sleep(10)
        return {"final_status": "completed", "step_results": {}}

    r = await run_case(case, executor=_slow, timeout_s=1)
    assert r.passed is False
    assert any("timeout" in x for x in r.reasons)


# ─── run_suite ───
async def test_run_suite_with_mock_executor(tmp_path) -> None:
    """默认 mock executor 应当让所有 case 通过。"""
    (tmp_path / "a.yaml").write_text(
        "case_id: a\n"
        "input:\n  user_request: x\n"
        "expected:\n  must_have_steps: [step_a]\n"
        "  must_have_artifact_types: [text]\n",
        encoding="utf-8",
    )
    suite = EvalSuite.from_directory(tmp_path)
    report = await run_suite(suite, mode="mock")
    assert isinstance(report, SuiteReport)
    assert report.n_cases == 1
    assert report.pass_rate == 1.0


async def test_run_suite_parallel(tmp_path) -> None:
    for i in range(5):
        (tmp_path / f"c{i}.yaml").write_text(
            f"case_id: c{i}\n"
            "input:\n  user_request: x\n"
            "expected:\n  must_have_steps: [step_a]\n",
            encoding="utf-8",
        )
    suite = EvalSuite.from_directory(tmp_path)
    report = await run_suite(suite, mode="mock", parallel=3)
    assert report.n_cases == 5
    assert report.pass_rate == 1.0


def test_aggregate_report_handles_empty() -> None:
    r = aggregate_report(suite_name="empty", results=[])
    assert r.n_cases == 0
    assert r.pass_rate == 0.0


def test_summary_text_renders() -> None:
    r = aggregate_report(
        suite_name="x",
        results=[
            CaseResult(case_id="ok", passed=True, score=0.9, duration_ms=100, total_cost_usd=0.01),
            CaseResult(
                case_id="bad",
                passed=False,
                score=0.4,
                duration_ms=200,
                total_cost_usd=0.02,
                reasons=["missing_steps=['x']"],
            ),
        ],
    )
    text = r.summary_text()
    assert "passed:       1" in text
    assert "bad" in text
    assert "missing_steps" in text


# ─── 真仓库 fixtures ───
def test_repo_golden_loads_at_least_one_case() -> None:
    if not REPO_GOLDEN.exists():
        pytest.skip(f"golden dir not present at {REPO_GOLDEN}")
    suite = EvalSuite.from_directory(REPO_GOLDEN)
    assert suite.cases, "expected at least one fixture in agents/eval/golden/"
    ids = {c.case_id for c in suite.cases}
    # 关键 fixture 都在
    assert "short_video_basic" in ids
    assert "xhs_note_basic" in ids


async def test_repo_golden_runs_with_mock_executor() -> None:
    """真 fixture + 默认 mock executor → 应该都能跑通(verify schema 没 typo)。"""
    if not REPO_GOLDEN.exists():
        pytest.skip(f"golden dir not present at {REPO_GOLDEN}")
    suite = EvalSuite.from_directory(REPO_GOLDEN)
    report = await run_suite(suite, mode="mock", timeout_s=30)
    # mock executor 默认让所有 case 通过 — 失败说明 fixture 有结构问题
    assert report.n_cases == len(suite.cases)
    # 不强制 pass_rate==1.0 — 真 fixture 可能要求 must_pass_critic=true,而 mock 没产 critique
    # 但至少 score > 0
    for c in report.cases:
        assert c.score > 0, f"{c.case_id} got 0 score: {c.reasons}"
