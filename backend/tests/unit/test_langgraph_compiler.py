"""LangGraph compiler:Skill YAML → StateGraph 的拓扑/校验/编译可用性。"""

from __future__ import annotations

import pytest
from agents.orchestrator_agent.langgraph_runner.compiler import build_state_graph


async def _noop_dispatch(task):
    return None


async def _noop_wait(task_id, step_id, timeout):
    return None


def _skill(workflow):
    return {"skill_id": "test", "version": "1.0", "workflow": workflow}


def test_build_simple_graph_compiles() -> None:
    builder = build_state_graph(
        _skill(
            [
                {"step_id": "a", "agent": "agent_1", "task_type": "web_search"},
                {
                    "step_id": "b",
                    "agent": "agent_1",
                    "task_type": "long_writing",
                    "depends_on": ["a"],
                },
            ]
        ),
        dispatcher=_noop_dispatch,
        result_waiter=_noop_wait,
    )
    # builder 拥有节点 planner / step_a / step_b / finalize
    nodes = set(builder.nodes.keys())
    assert {"planner", "step_a", "step_b", "finalize"} <= nodes


def test_build_diamond_parallelism() -> None:
    builder = build_state_graph(
        _skill(
            [
                {"step_id": "a", "agent": "agent_1", "task_type": "web_search"},
                {
                    "step_id": "b",
                    "agent": "agent_1",
                    "task_type": "long_writing",
                    "depends_on": ["a"],
                },
                {
                    "step_id": "c",
                    "agent": "agent_3",
                    "task_type": "image_download",
                    "depends_on": ["a"],
                },
                {
                    "step_id": "d",
                    "agent": "agent_4",
                    "task_type": "video_compose",
                    "depends_on": ["b", "c"],
                },
            ]
        ),
        dispatcher=_noop_dispatch,
        result_waiter=_noop_wait,
    )
    # 编译后所有 step 节点都存在,Send 路由是动态的(运行时验证)
    assert {"step_a", "step_b", "step_c", "step_d"} <= set(builder.nodes.keys())


def test_build_invalid_yaml_raises() -> None:
    """compiler 复用 compile_to_dag 的环检测,坏 YAML 应早 fail。"""
    from agents.orchestrator_agent.task_compiler import DAGCompileError

    with pytest.raises(DAGCompileError):
        build_state_graph(
            _skill(
                [
                    {
                        "step_id": "a",
                        "agent": "agent_1",
                        "task_type": "web_search",
                        "depends_on": ["b"],
                    },
                    {
                        "step_id": "b",
                        "agent": "agent_1",
                        "task_type": "web_search",
                        "depends_on": ["a"],
                    },
                ]
            ),
            dispatcher=_noop_dispatch,
            result_waiter=_noop_wait,
        )
