"""子模块 5:任务编排器(纯程序)。

把 Skill YAML + collected_fields → 可执行 DAG 描述 + AgentTask 列表。

设计:
- TaskRunner._dispatch_eligible 已在 DB 上做"找到所有 deps 都完成的 step 派发"
  ⇒ 真正的并行能力来自这里;compile 只负责**校验 + 把 YAML 翻成结构化对象**。
- compile_to_dag() 额外返回拓扑分层(parallel levels),用于:
  1) 启动前的环检测 / 缺失依赖检测(快速失败)
  2) UI 预览"哪几步会并行执行"
  3) Reflexion 时把"第 N 层卡住"作为根因
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any
from uuid import UUID, uuid4

from jinja2 import Template
from pydantic import BaseModel

from app.schemas.agent import AgentTask


class CompiledStep(BaseModel):
    step_id: str
    agent_id: str
    task_type: str
    inputs: dict[str, Any]
    parameters: dict[str, Any]
    timeout_seconds: int
    depends_on: list[str]
    hitl_gate: dict[str, Any] | None = None


class CompiledDAG(BaseModel):
    """Skill YAML → 静态 DAG 描述。"""

    steps: list[CompiledStep]
    levels: list[list[str]]  # 拓扑分层,同层可并行
    primary_artifact: str | None = None


class DAGCompileError(ValueError):
    """编译期错误(环 / 缺失 dep / 重复 step_id 等)。"""


_JINJA_EXPRESSION_RE = re.compile(r"\{\{.*?\}\}")


def _render_preview_prompt(
    template: str, *, fields: dict[str, Any], step_ids: set[str]
) -> str:
    """渲染用户字段，同时保留只能在运行期解析的上游步骤表达式。"""
    deferred: dict[str, str] = {}

    def _mask(match: re.Match[str]) -> str:
        expression = match.group(0)
        body = expression[2:-2].strip()
        root = re.split(r"[.[]", body, maxsplit=1)[0].strip()
        if root not in step_ids:
            return expression
        token = f"__HAOLE_DEFERRED_STEP_{len(deferred)}__"
        deferred[token] = expression
        return token

    masked = _JINJA_EXPRESSION_RE.sub(_mask, template)
    rendered = Template(masked).render(**fields)
    for token, expression in deferred.items():
        rendered = rendered.replace(token, expression)
    return rendered


def _toposort_levels(
    step_ids: list[str], deps: dict[str, list[str]]
) -> list[list[str]]:
    """Kahn 分层 + 环/缺失检测。"""
    valid = set(step_ids)
    indeg: dict[str, int] = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)
    for sid in step_ids:
        for d in deps.get(sid, []):
            if d not in valid:
                raise DAGCompileError(f"step {sid!r} depends on missing step {d!r}")
            children[d].append(sid)
            indeg[sid] += 1

    levels: list[list[str]] = []
    frontier = sorted(s for s in step_ids if indeg[s] == 0)
    visited = 0
    while frontier:
        levels.append(frontier)
        next_frontier: list[str] = []
        for s in frontier:
            visited += 1
            for c in children.get(s, []):
                indeg[c] -= 1
                if indeg[c] == 0:
                    next_frontier.append(c)
        frontier = sorted(next_frontier)
    if visited != len(step_ids):
        cycle = sorted(s for s in step_ids if indeg[s] > 0)
        raise DAGCompileError(f"cycle in DAG, suspected steps: {cycle}")
    return levels


def compile_to_dag(skill_yaml: dict[str, Any]) -> CompiledDAG:
    """静态校验 + 翻成 CompiledDAG;不需要运行期上下文。"""
    workflow = skill_yaml.get("workflow") or []
    if not workflow:
        raise DAGCompileError("skill workflow is empty")

    seen: set[str] = set()
    deps: dict[str, list[str]] = {}
    compiled_steps: list[CompiledStep] = []
    for step in workflow:
        sid = step.get("step_id")
        if not sid:
            raise DAGCompileError(f"step missing step_id: {step!r}")
        if sid in seen:
            raise DAGCompileError(f"duplicate step_id: {sid!r}")
        seen.add(sid)

        agent = step.get("agent")
        task_type = step.get("task_type")
        if not agent or not task_type:
            raise DAGCompileError(
                f"step {sid!r} missing agent={agent!r} or task_type={task_type!r}"
            )

        d = list(step.get("depends_on") or [])
        deps[sid] = d
        compiled_steps.append(
            CompiledStep(
                step_id=sid,
                agent_id=agent,
                task_type=task_type,
                inputs=dict(step.get("inputs") or {}),
                parameters=dict(step.get("parameters") or {}),
                timeout_seconds=int(step.get("timeout") or 60),
                depends_on=d,
                hitl_gate=step.get("hitl_gate"),
            )
        )

    levels = _toposort_levels([s.step_id for s in compiled_steps], deps)
    primary = (skill_yaml.get("delivery") or {}).get("primary_artifact")
    if primary and primary not in seen:
        raise DAGCompileError(
            f"delivery.primary_artifact {primary!r} not in workflow steps"
        )
    return CompiledDAG(steps=compiled_steps, levels=levels, primary_artifact=primary)


def compile_task(
    *,
    skill_yaml: dict[str, Any],
    collected_fields: dict[str, Any],
    user_id: UUID,
    conversation_id: UUID,
    task_id: UUID | None = None,
) -> tuple[UUID, list[CompiledStep], list[AgentTask]]:
    """同 compile_to_dag,但**注入**当前 task 上下文(渲染 prompt + 生成 AgentTask 草稿)。

    注意:运行期真正的派发由 TaskRunner._dispatch_eligible 完成,这里返回的
    AgentTask 列表仅用于:启动前预检 / 单测 / 离线分析。
    """
    dag = compile_to_dag(skill_yaml)
    task_id = task_id or uuid4()
    agent_tasks: list[AgentTask] = []

    workflow = skill_yaml.get("workflow") or []
    by_id = {s["step_id"]: s for s in workflow}
    step_ids = set(by_id)
    for cs in dag.steps:
        raw = by_id[cs.step_id]
        prompt_tpl = raw.get("prompt_template", "")
        rendered_prompt = (
            _render_preview_prompt(
                prompt_tpl,
                fields=collected_fields,
                step_ids=step_ids,
            )
            if prompt_tpl
            else ""
        )
        if rendered_prompt:
            cs.inputs = {**cs.inputs, "_prompt": rendered_prompt}
        agent_tasks.append(
            AgentTask(
                task_id=task_id,
                step_id=cs.step_id,
                agent_id=cs.agent_id,  # type: ignore[arg-type]
                task_type=cs.task_type,
                user_id=user_id,
                conversation_id=conversation_id,
                inputs=cs.inputs,
                parameters=cs.parameters,
                routing_hints=raw.get("routing_hints", {}),
                skill_id=skill_yaml.get("skill_id"),
                skill_version=skill_yaml.get("version"),
                timeout_seconds=cs.timeout_seconds,
                mcp_tools=list(raw.get("mcp_tools") or []),
            )
        )
    return task_id, dag.steps, agent_tasks
