"""Critique → Reflexion 桥接测试(ADR-G,接 ADR-020 + ADR-011)。

覆盖:
- 提取:status=completed + critique.score < max_score → 命中
- 提取:status=failed → 跳过(走原有 reflexion 路径)
- 提取:critique.skipped_reason 非空 → 跳过(critic 自身故障 ≠ 改进信号)
- 提取:critique.score >= max_score → 跳过(不够差)
- 排序:按 score 升序,最差的优先
- 上限:max_signals 限制
- payload shape 与 reflexion_graph.ReflexionState 兼容
- emit:flywheel_emitter 不可用时不抛
- emit:每条信号失败不影响其他
- scan_and_emit_from_state:端到端
"""

from __future__ import annotations


from agents.orchestrator_agent.langgraph_runner.critique_signal import (
    SIGNAL_SOURCE_CRITIC_LOW_SCORE,
    CritiqueSignal,
    emit_critique_signals,
    extract_critique_signals,
    scan_and_emit_from_state,
)


def _step_result(
    *,
    status: str = "completed",
    score: float | None = 0.4,
    threshold: float = 0.7,
    issues: list[str] | None = None,
    suggestion: str = "",
    skipped_reason: str | None = None,
    task_type: str = "long_writing",
    artifact_ref: str | None = "oss://x.txt",
):
    critique: dict | None
    if score is None and skipped_reason is None and not issues and not suggestion:
        critique = None
    else:
        critique = {
            "score": score,
            "threshold_used": threshold,
            "issues": issues or [],
            "suggestion": suggestion,
            "should_retry": score is not None and score < threshold,
        }
        if skipped_reason is not None:
            critique["skipped_reason"] = skipped_reason
    return {
        "step_id": "s1",
        "agent_id": "agent_1",
        "task_type": task_type,
        "status": status,
        "artifact_ref": artifact_ref,
        "critique": critique,
    }


# ─── 提取规则 ───
def test_extract_low_score_step_returns_signal() -> None:
    step_results = {
        "draft": _step_result(
            score=0.3,
            issues=["开头钩子缺失"],
            suggestion="加一个真实数字开头",
        )
    }
    sigs = extract_critique_signals(
        task_id="t-1",
        skill_id="short_video",
        step_results=step_results,
    )
    assert len(sigs) == 1
    s = sigs[0]
    assert s.step_id == "draft"
    assert s.score == 0.3
    assert s.threshold == 0.7
    assert s.skill_id == "short_video"
    assert "开头钩子缺失" in s.issues
    assert "真实数字" in s.suggestion


def test_extract_failed_step_skipped() -> None:
    """status=failed 走原有 reflexion 路径,不重复发信号。"""
    step_results = {
        "draft": _step_result(status="failed", score=0.2),
    }
    sigs = extract_critique_signals(
        task_id="t-1", skill_id=None, step_results=step_results
    )
    assert sigs == []


def test_extract_critic_skipped_filtered() -> None:
    """critique.skipped_reason 非空 → 不视为改进信号。"""
    step_results = {
        "draft": _step_result(
            score=0.0, skipped_reason="non-text artifact"
        ),
    }
    sigs = extract_critique_signals(
        task_id="t-1", skill_id=None, step_results=step_results
    )
    assert sigs == []


def test_extract_score_above_max_filtered() -> None:
    step_results = {
        "draft": _step_result(score=0.65),  # 高于默认 max_score=0.6
    }
    sigs = extract_critique_signals(
        task_id="t-1", skill_id=None, step_results=step_results
    )
    assert sigs == []


def test_extract_uses_explicit_max_score() -> None:
    step_results = {
        "draft": _step_result(score=0.65),
    }
    sigs = extract_critique_signals(
        task_id="t-1", skill_id=None, step_results=step_results, max_score=0.7
    )
    assert len(sigs) == 1


def test_extract_no_critique_skipped() -> None:
    """step_result 无 critique 字段(critic 未启用)→ 跳过。"""
    step_results = {
        "draft": {
            "step_id": "draft",
            "agent_id": "agent_1",
            "task_type": "long_writing",
            "status": "completed",
            # 没有 critique
        }
    }
    sigs = extract_critique_signals(
        task_id="t-1", skill_id=None, step_results=step_results
    )
    assert sigs == []


def test_extract_sorts_by_score_ascending() -> None:
    """最差的(分最低的)优先 — emit 数量受限时它们先入队。"""
    step_results = {
        "a": _step_result(score=0.5),
        "b": _step_result(score=0.2),
        "c": _step_result(score=0.4),
    }
    # 改 step_id 让对比清晰
    step_results["a"]["step_id"] = "a"
    step_results["b"]["step_id"] = "b"
    step_results["c"]["step_id"] = "c"

    sigs = extract_critique_signals(
        task_id="t", skill_id=None, step_results=step_results
    )
    scores = [s.score for s in sigs]
    assert scores == sorted(scores)
    assert sigs[0].step_id == "b"


def test_extract_respects_max_signals() -> None:
    step_results = {
        f"s{i}": {
            **_step_result(score=0.1 + i * 0.05),
            "step_id": f"s{i}",
        }
        for i in range(10)
    }
    sigs = extract_critique_signals(
        task_id="t",
        skill_id=None,
        step_results=step_results,
        max_signals=3,
    )
    assert len(sigs) == 3
    # 仍按 score 升序
    assert sigs[0].score < sigs[1].score < sigs[2].score


# ─── Payload shape ───
def test_to_reflexion_payload_compatible_shape() -> None:
    sig = CritiqueSignal(
        task_id="t-1",
        step_id="draft",
        task_type="long_writing",
        skill_id="short_video",
        score=0.3,
        threshold=0.7,
        issues=["i1", "i2"],
        suggestion="改 X",
        artifact_ref="oss://a.txt",
    )
    p = sig.to_reflexion_payload()
    # 必填字段(reflexion_graph.process_reflexion_event 读这些)
    assert p["task_id"] == "t-1"
    assert "short_video::step_draft::long_writing" == p["prompt_name"]
    assert "score=0.30" in p["failure_reason"]
    assert "改 X" in p["failure_reason"]
    assert "draft" in p["trace_excerpt"]
    # source 标记
    assert p["source"] == SIGNAL_SOURCE_CRITIC_LOW_SCORE
    # metadata
    assert p["metadata"]["score"] == 0.3
    assert p["metadata"]["step_id"] == "draft"
    assert p["metadata"]["skill_id"] == "short_video"


def test_prompt_name_for_dynamic_plan() -> None:
    """skill_id=None 的动态 plan → prompt_name 用 'dynamic'."""
    sig = CritiqueSignal(
        task_id="t",
        step_id="s1",
        task_type="web_search",
        skill_id=None,
        score=0.3,
        threshold=0.7,
    )
    assert sig.prompt_name == "dynamic::step_s1::web_search"


def test_failure_reason_handles_missing_fields() -> None:
    sig = CritiqueSignal(
        task_id="t",
        step_id="s",
        task_type="x",
        skill_id=None,
        score=0.3,
        threshold=0.7,
        issues=[],
        suggestion="",
    )
    fr = sig.failure_reason()
    assert "score=0.30" in fr
    assert "critic 未列出具体问题" in fr
    assert "critic 无明确改进方向" in fr


# ─── emit graceful ───
async def test_emit_handles_emitter_unavailable(monkeypatch) -> None:
    """flywheel_emitter 导入失败(无 redis)→ 不抛,返回 0。"""
    # 强制 import 失败:用 stub 替换 sys.modules
    import sys

    saved = sys.modules.pop("agents._common.flywheel_emitter", None)
    sys.modules["agents._common.flywheel_emitter"] = None  # type: ignore[assignment]
    try:
        n = await emit_critique_signals(
            [
                CritiqueSignal(
                    task_id="t",
                    step_id="s",
                    task_type="x",
                    skill_id=None,
                    score=0.3,
                    threshold=0.7,
                )
            ]
        )
        assert n == 0
    finally:
        if saved is not None:
            sys.modules["agents._common.flywheel_emitter"] = saved
        else:
            sys.modules.pop("agents._common.flywheel_emitter", None)


async def test_emit_continues_on_per_signal_failure(monkeypatch) -> None:
    """单个 emit 抛异常不影响其他信号。"""
    import agents._common.flywheel_emitter as fe

    call_n = {"i": 0}

    async def flaky(*, signal_type, payload):
        call_n["i"] += 1
        if call_n["i"] == 1:
            raise ConnectionError("redis down for first call")
        return None

    monkeypatch.setattr(fe, "emit", flaky)

    sigs = [
        CritiqueSignal(
            task_id="t",
            step_id=f"s{i}",
            task_type="x",
            skill_id=None,
            score=0.2 + i * 0.1,
            threshold=0.7,
        )
        for i in range(3)
    ]
    n = await emit_critique_signals(sigs)
    # 第 1 条挂,后 2 条成功
    assert n == 2
    assert call_n["i"] == 3


async def test_emit_empty_returns_zero() -> None:
    assert (await emit_critique_signals([])) == 0


# ─── scan_and_emit_from_state ───
async def test_scan_and_emit_from_state_end_to_end(monkeypatch) -> None:
    captured: list[dict] = []

    async def _fake_emit(*, signal_type, payload):
        captured.append({"type": signal_type, "payload": payload})

    import agents._common.flywheel_emitter as fe

    monkeypatch.setattr(fe, "emit", _fake_emit)

    state = {
        "task_id": "t-final",
        "skill_id": "short_video",
        "step_results": {
            "research": {
                "step_id": "research",
                "task_type": "web_search",
                "status": "completed",
                "critique": {
                    "score": 0.95,  # 高分,不发
                    "threshold_used": 0.7,
                    "issues": [],
                    "suggestion": "",
                },
            },
            "script": {
                "step_id": "script",
                "task_type": "long_writing",
                "status": "completed",
                "artifact_ref": "oss://script.txt",
                "critique": {
                    "score": 0.35,  # 低分,要发
                    "threshold_used": 0.7,
                    "issues": ["开头钩子无冲突感"],
                    "suggestion": "加真实数字开场",
                    "should_retry": True,
                },
            },
        },
        "collected_fields": {"年份": 2026, "受众": "城市老人"},
    }

    n = await scan_and_emit_from_state(state)
    assert n == 1
    assert len(captured) == 1
    pl = captured[0]["payload"]
    assert pl["source"] == SIGNAL_SOURCE_CRITIC_LOW_SCORE
    assert pl["metadata"]["step_id"] == "script"
    assert "开头钩子" in pl["failure_reason"]
    assert "城市老人" in pl["trace_excerpt"]  # collected_fields 进了 excerpt


async def test_scan_and_emit_no_signals_returns_zero(monkeypatch) -> None:
    """没有低分 critique → 不调 emitter。"""
    called = {"n": 0}

    async def _fake_emit(*, signal_type, payload):
        called["n"] += 1

    import agents._common.flywheel_emitter as fe

    monkeypatch.setattr(fe, "emit", _fake_emit)

    state = {
        "task_id": "t",
        "skill_id": None,
        "step_results": {
            "draft": {
                "step_id": "draft",
                "task_type": "long_writing",
                "status": "completed",
                "critique": {"score": 0.95, "threshold_used": 0.7},
            }
        },
    }
    n = await scan_and_emit_from_state(state)
    assert n == 0
    assert called["n"] == 0


async def test_scan_and_emit_no_task_id_returns_zero() -> None:
    """state 缺 task_id → 不抛,返回 0。"""
    n = await scan_and_emit_from_state({"step_results": {}})
    assert n == 0
