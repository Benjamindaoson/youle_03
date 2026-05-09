"""编译后 StateGraph 进程级缓存 — 从 runner 拆分。"""

from __future__ import annotations

from typing import Any

# Skill YAML 极少变,但 start / resume / rollback / get_state 都要拿 graph。
# key = (skill_id, version):version bump 自动失效。
COMPILED_GRAPH_CACHE: dict[tuple[str | None, str | None], Any] = {}


def skill_yaml_cache_key(skill_yaml: dict[str, Any]) -> tuple[str | None, str | None]:
    return (skill_yaml.get("skill_id"), skill_yaml.get("version"))


def clear_compiled_cache() -> None:
    """测试用 / 热重载 Skill YAML 时调。"""
    COMPILED_GRAPH_CACHE.clear()
