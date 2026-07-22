"""LangGraph runner 修补单测:

1. 编译产物缓存：canonical 为 `runner_compiled_cache.COMPILED_GRAPH_CACHE`；
   `runner._COMPILED_CACHE` / `_cache_key` 为兼容 facade(与 canonical 同一对象 / 函数)
2. _pick_predecessor_agent 在并行 fan-out 下用 depends_on 正确选前置 agent
   (不依赖 race 赢家 / 单变量 prev_agent)

prev_agent 的逻辑现在是 inline closure 在 _run_until_pause 里,这里直接重建一份
等价 stub 来测算法本身。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from agents.orchestrator_agent.langgraph_runner import runner as lg_runner
from agents.orchestrator_agent.langgraph_runner.runner_compiled_cache import (
    COMPILED_GRAPH_CACHE,
    skill_yaml_cache_key,
)

from app.schemas.ws import WSEventType


def test_runner_compiled_cache_facade_aliases_canonical() -> None:
    assert lg_runner._cache_key is skill_yaml_cache_key
    assert lg_runner._COMPILED_CACHE is COMPILED_GRAPH_CACHE


# ─────────────────────────────────────────────────────────────────
# 编译产物缓存
# ─────────────────────────────────────────────────────────────────
def test_cache_key_extracts_skill_id_and_version() -> None:
    yml = {"skill_id": "short_video", "version": "1.0", "workflow": []}
    assert lg_runner._cache_key(yml) == ("short_video", "1.0")


def test_cache_key_handles_missing_fields() -> None:
    assert lg_runner._cache_key({}) == (None, None)
    assert lg_runner._cache_key({"skill_id": "x"}) == ("x", None)


def test_clear_compiled_cache_empties_dict() -> None:
    lg_runner._COMPILED_CACHE[("dummy", "v1")] = "fake_graph"
    assert lg_runner._COMPILED_CACHE
    lg_runner.clear_compiled_cache()
    assert not lg_runner._COMPILED_CACHE


def test_task_events_are_scoped_to_their_conversation() -> None:
    task_id = UUID("00000000-0000-0000-0000-000000000010")
    conversation_id = UUID("00000000-0000-0000-0000-000000000020")

    event = lg_runner._task_event(
        event_type=WSEventType.TASK_COMPLETED,
        task_id=task_id,
        conversation_id=conversation_id,
        primary_artifact={"reference": "mock://result"},
    )

    assert event["task_id"] == str(task_id)
    assert event["conversation_id"] == str(conversation_id)


def test_progress_is_derived_from_completed_step_results() -> None:
    progress = lg_runner._progress_from_state(
        {
            "step_results": {
                "research": {"status": "completed"},
                "script": {"status": "completed"},
                "video": {"status": "failed"},
            }
        },
        previous={"current": 0, "total": 5},
    )

    assert progress == {"current": 2, "total": 5}


def test_primary_artifact_keeps_type_and_metadata() -> None:
    artifact = lg_runner._primary_artifact_from_state(
        {
            "primary_artifact_ref": "mock://video",
            "step_results": {
                "compose": {
                    "artifact_ref": "mock://video",
                    "artifact_type": "video",
                    "artifact_metadata": {"duration": 30},
                }
            },
        }
    )

    assert artifact == {
        "reference": "mock://video",
        "type": "video",
        "metadata": {"duration": 30},
    }


def test_cache_isolates_by_version() -> None:
    """同 skill_id 不同 version 应当是不同 key(version bump → 自动失效)。"""
    lg_runner.clear_compiled_cache()
    lg_runner._COMPILED_CACHE[("x", "1.0")] = "graph_v1"
    lg_runner._COMPILED_CACHE[("x", "1.1")] = "graph_v11"
    assert lg_runner._COMPILED_CACHE[("x", "1.0")] != lg_runner._COMPILED_CACHE[("x", "1.1")]
    lg_runner.clear_compiled_cache()


# ─────────────────────────────────────────────────────────────────
# 并行前置选择(_pick_predecessor_agent 等价算法)
# ─────────────────────────────────────────────────────────────────
def _pick_pred(
    step_meta: dict[str, dict[str, Any]],
    current_step_id: str,
    current_agent: str,
) -> str | None:
    """与 runner._run_until_pause 内闭包等价的算法 — 用于隔离单测。"""
    meta = step_meta.get(current_step_id, {})
    for dep in meta.get("depends_on", []):
        dep_meta = step_meta.get(dep, {})
        dep_agent = dep_meta.get("agent")
        if dep_agent and dep_agent != current_agent:
            return dep_agent
    return None


def test_pred_returns_none_for_entry_step() -> None:
    """图入口 step 没有 depends_on → None(没人交接)。"""
    meta = {"a": {"agent": "agent_1", "depends_on": []}}
    assert _pick_pred(meta, "a", "agent_1") is None


def test_pred_returns_none_when_dep_same_agent() -> None:
    """前置都是同 agent → None(同 Agent 内部步骤,不演)。"""
    meta = {
        "a": {"agent": "agent_1", "depends_on": []},
        "b": {"agent": "agent_1", "depends_on": ["a"]},
    }
    assert _pick_pred(meta, "b", "agent_1") is None


def test_pred_finds_cross_agent_predecessor() -> None:
    """前置是不同 agent → 返回它(交接发生)。"""
    meta = {
        "a": {"agent": "agent_1", "depends_on": []},
        "b": {"agent": "agent_3", "depends_on": ["a"]},
    }
    assert _pick_pred(meta, "b", "agent_3") == "agent_1"


def test_pred_parallel_fanout_correctness() -> None:
    """并行 fan-out:research → image / tts / bgm → compose

    无论 image/tts/bgm 谁先完成,compose 的 predecessor 不再依赖 race 赢家,
    而是由 depends_on 指定。compose depends_on=[image,tts,bgm],其中
    image/tts 是 agent_3,bgm/compose 是 agent_4,任一不同的就行。
    """
    meta = {
        "research": {"agent": "agent_1", "depends_on": []},
        "image": {"agent": "agent_3", "depends_on": ["research"]},
        "tts": {"agent": "agent_4", "depends_on": ["research"]},
        "bgm": {"agent": "agent_4", "depends_on": ["research"]},
        "compose": {"agent": "agent_4", "depends_on": ["image", "tts", "bgm"]},
    }
    # image / tts / bgm 各自 predecessor 都是 research(agent_1)— 跨 Agent
    assert _pick_pred(meta, "image", "agent_3") == "agent_1"
    assert _pick_pred(meta, "tts", "agent_4") == "agent_1"
    assert _pick_pred(meta, "bgm", "agent_4") == "agent_1"
    # compose 的 deps 是 [image=agent_3, tts=agent_4, bgm=agent_4]
    # current=agent_4,找到第一个不同 agent 的前置 = image(agent_3)
    # 关键:**不依赖完成顺序**,depends_on 顺序决定
    assert _pick_pred(meta, "compose", "agent_4") == "agent_3"


def test_pred_skips_unknown_step() -> None:
    """未知 step_id → None(graceful)。"""
    meta = {"a": {"agent": "agent_1", "depends_on": []}}
    assert _pick_pred(meta, "ghost", "agent_3") is None


def test_pred_skips_dep_with_unknown_agent() -> None:
    """前置 step 元数据缺失 → 跳过(graceful,不 crash)。"""
    meta = {
        "b": {"agent": "agent_3", "depends_on": ["missing_dep"]},
    }
    assert _pick_pred(meta, "b", "agent_3") is None
