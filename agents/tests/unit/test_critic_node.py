"""critic_node 单元测试(ADR-020)。

LITELLM_MOCK=true 下走 _mock_critique 路径,无网络依赖。
"""

from __future__ import annotations


from agents.orchestrator_agent.langgraph_runner.critic_node import (
    CRITIC_DEFAULT_ON_TASK_TYPES,
    CritiqueResult,
    build_retry_prompt,
    evaluate,
    get_max_retries,
    get_threshold,
)


# ─── is_critic_enabled_for ───
def test_critic_disabled_by_default(monkeypatch) -> None:
    """ENABLE_CRITIC_LOOP=false(默认)→ 一律返回 false。"""
    monkeypatch.setenv("ENABLE_CRITIC_LOOP", "false")
    # 必须重新 import 以重新读 env(critic_node 模块级常量)
    import importlib

    import agents.orchestrator_agent.langgraph_runner.critic_node as cn

    importlib.reload(cn)
    assert cn.is_critic_enabled_for("long_writing", {}) is False
    assert cn.is_critic_enabled_for("xhs_carousel_copy", {}) is False


def test_critic_enabled_for_default_task_types(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_CRITIC_LOOP", "true")
    import importlib

    import agents.orchestrator_agent.langgraph_runner.critic_node as cn

    importlib.reload(cn)
    assert cn.is_critic_enabled_for("long_writing", {}) is True
    assert cn.is_critic_enabled_for("short_writing", {}) is True
    assert cn.is_critic_enabled_for("xhs_carousel_copy", {}) is True
    # 非创作类
    assert cn.is_critic_enabled_for("video_compose", {}) is False
    assert cn.is_critic_enabled_for("image_generate", {}) is False


def test_critic_step_override_enable(monkeypatch) -> None:
    """flag off + step.critic.enabled=true → true。"""
    monkeypatch.setenv("ENABLE_CRITIC_LOOP", "false")
    import importlib

    import agents.orchestrator_agent.langgraph_runner.critic_node as cn

    importlib.reload(cn)
    assert cn.is_critic_enabled_for(
        "video_compose", {"critic": {"enabled": True}}
    ) is True


def test_critic_step_override_disable(monkeypatch) -> None:
    """flag on + step.critic.enabled=false → false。"""
    monkeypatch.setenv("ENABLE_CRITIC_LOOP", "true")
    import importlib

    import agents.orchestrator_agent.langgraph_runner.critic_node as cn

    importlib.reload(cn)
    assert cn.is_critic_enabled_for(
        "long_writing", {"critic": {"enabled": False}}
    ) is False


# ─── threshold / max_retries ───
def test_get_threshold_default() -> None:
    assert get_threshold({}) == 0.7  # CRITIC_THRESHOLD default


def test_get_threshold_step_override() -> None:
    assert get_threshold({"critic": {"threshold": 0.85}}) == 0.85


def test_get_threshold_invalid_falls_back() -> None:
    # bad value → fall back to default
    assert get_threshold({"critic": {"threshold": "bad"}}) == 0.7


def test_get_max_retries_default() -> None:
    assert get_max_retries({}) == 1


def test_get_max_retries_step_override() -> None:
    assert get_max_retries({"critic": {"max_retries": 3}}) == 3


def test_get_max_retries_clamps_negative() -> None:
    assert get_max_retries({"critic": {"max_retries": -5}}) == 0


# ─── CritiqueResult ───
def test_passed_above_threshold() -> None:
    c = CritiqueResult(score=0.9, threshold_used=0.7)
    assert c.passed() is True


def test_passed_below_threshold() -> None:
    c = CritiqueResult(score=0.5, threshold_used=0.7)
    assert c.passed() is False


def test_skipped_means_passed() -> None:
    """critic 自身故障 / 不适用 → passed=True,主流程不阻塞。"""
    c = CritiqueResult(score=0.0, threshold_used=0.7, skipped_reason="non-text artifact")
    assert c.passed() is True


def test_feedback_summary_includes_issues_and_suggestion() -> None:
    c = CritiqueResult(
        score=0.4,
        threshold_used=0.7,
        issues=["开头钩子缺失", "案例不具体"],
        suggestion="加一个真实数字开头",
    )
    s = c.feedback_summary()
    assert "开头钩子缺失" in s
    assert "加一个真实数字开头" in s


# ─── evaluate ───
async def test_evaluate_skips_non_text_artifact() -> None:
    """图像 / 视频类产物 → 跳过,critic 不评。"""
    c = await evaluate(
        step_def={},
        task_type="image_generate",
        rendered_prompt="生成图像",
        produced_artifact_text="<binary>",
        produced_artifact_type="image",
    )
    assert c.skipped_reason is not None
    assert c.passed() is True


async def test_evaluate_skips_empty_text() -> None:
    c = await evaluate(
        step_def={},
        task_type="long_writing",
        rendered_prompt="...",
        produced_artifact_text="",
        produced_artifact_type="text",
    )
    assert c.skipped_reason is not None
    assert c.passed() is True


async def test_evaluate_mock_returns_pass() -> None:
    """LITELLM_MOCK=true → 默认通过(score=0.85)。"""
    c = await evaluate(
        step_def={},
        task_type="long_writing",
        rendered_prompt="写一段短视频脚本",
        produced_artifact_text="这是一段短视频脚本,开头钩子...",
        produced_artifact_type="text",
    )
    assert c.passed() is True
    assert c.score == 0.85
    assert c.skipped_reason is None
    assert c.model_used == "mock"


async def test_evaluate_respects_step_threshold() -> None:
    """step.critic.threshold=0.9,mock 给 0.85 → 不通过。"""
    c = await evaluate(
        step_def={"critic": {"threshold": 0.9}},
        task_type="long_writing",
        rendered_prompt="...",
        produced_artifact_text="some text",
        produced_artifact_type="text",
    )
    assert c.score == 0.85
    assert c.threshold_used == 0.9
    assert c.passed() is False


# ─── build_retry_prompt ───
def test_build_retry_prompt_appends_block() -> None:
    original = "写一段短视频脚本"
    critique = CritiqueResult(
        score=0.5,
        threshold_used=0.7,
        issues=["开头无冲突"],
        suggestion="加一个真实数字开头",
    )
    out = build_retry_prompt(original_prompt=original, critique=critique)
    assert "写一段短视频脚本" in out
    assert "[Critic 反馈" in out
    assert "开头无冲突" in out
    assert "加一个真实数字开头" in out
    assert "0.50 / 阈值 0.70" in out


def test_build_retry_prompt_strips_prior_block() -> None:
    """连续两轮 critic 不应让反馈累加,旧反馈段被替换。"""
    original = "写一段短视频脚本"
    c1 = CritiqueResult(score=0.5, threshold_used=0.7, issues=["问题1"], suggestion="改 A")
    c2 = CritiqueResult(score=0.6, threshold_used=0.7, issues=["问题2"], suggestion="改 B")

    once = build_retry_prompt(original_prompt=original, critique=c1)
    twice = build_retry_prompt(original_prompt=once, critique=c2)

    # 旧反馈块不应在第二轮 prompt 里
    assert "问题1" not in twice
    assert "改 A" not in twice
    # 新反馈块应在
    assert "问题2" in twice
    assert "改 B" in twice
    # 用户原 prompt 仍在
    assert "写一段短视频脚本" in twice


# ─── default-on task_types 完整性 ───
def test_default_on_task_types_covers_creative() -> None:
    """白名单应包含核心创作类 task_type。"""
    expected = {
        "short_writing",
        "long_writing",
        "structured_writing",
        "short_video_script",
        "xhs_carousel_copy",
    }
    assert expected <= CRITIC_DEFAULT_ON_TASK_TYPES
