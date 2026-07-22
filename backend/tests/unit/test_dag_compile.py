"""DAG 编译器(task_compiler.compile_to_dag)单测。"""

from __future__ import annotations

import pytest
from agents.orchestrator_agent.task_compiler import (
    CompiledDAG,
    DAGCompileError,
    compile_to_dag,
)


def _skill(workflow: list[dict]) -> dict:
    return {"skill_id": "test", "version": "1.0", "workflow": workflow}


def test_linear_workflow_topo_levels() -> None:
    dag: CompiledDAG = compile_to_dag(
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
        )
    )
    assert dag.levels == [["a"], ["b"]]
    assert len(dag.steps) == 2


def test_diamond_dependency_parallelism() -> None:
    """B 与 C 应当在同一层(可并行)。"""
    dag = compile_to_dag(
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
        )
    )
    assert dag.levels == [["a"], ["b", "c"], ["d"]]


def test_cycle_detection() -> None:
    with pytest.raises(DAGCompileError, match="cycle"):
        compile_to_dag(
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
            )
        )


def test_missing_dependency() -> None:
    with pytest.raises(DAGCompileError, match="missing"):
        compile_to_dag(
            _skill(
                [
                    {
                        "step_id": "a",
                        "agent": "agent_1",
                        "task_type": "web_search",
                        "depends_on": ["nonexistent"],
                    }
                ]
            )
        )


def test_duplicate_step_id() -> None:
    with pytest.raises(DAGCompileError, match="duplicate"):
        compile_to_dag(
            _skill(
                [
                    {"step_id": "a", "agent": "agent_1", "task_type": "web_search"},
                    {"step_id": "a", "agent": "agent_1", "task_type": "long_writing"},
                ]
            )
        )


def test_empty_workflow() -> None:
    with pytest.raises(DAGCompileError):
        compile_to_dag({"workflow": []})


def test_missing_agent_or_task_type() -> None:
    with pytest.raises(DAGCompileError):
        compile_to_dag(_skill([{"step_id": "a", "task_type": "web_search"}]))
    with pytest.raises(DAGCompileError):
        compile_to_dag(_skill([{"step_id": "a", "agent": "agent_1"}]))


def test_primary_artifact_validation() -> None:
    skill = _skill(
        [{"step_id": "a", "agent": "agent_1", "task_type": "web_search"}]
    )
    skill["delivery"] = {"primary_artifact": "missing"}
    with pytest.raises(DAGCompileError, match="primary_artifact"):
        compile_to_dag(skill)


def test_short_video_skill_real() -> None:
    """对真实 short_video.yaml 编译,确保不报错。"""
    from pathlib import Path

    import yaml

    yaml_path = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "playbooks"
        / "short_video.yaml"
    )
    if not yaml_path.exists():
        pytest.skip("skill yaml not found")
    skill = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    dag = compile_to_dag(skill)
    assert len(dag.steps) >= 3
    assert len(dag.levels) >= 2
