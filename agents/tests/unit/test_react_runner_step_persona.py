"""ReAct Runner ↔ StepPersona 集成测试(ADR-021)。

只测**纯函数 / 同步部分**:`_build_tools` 与 `_system_instruction`,
不真跑 LLM 循环(那需要 mock complete_chat,放在端到端测试里)。

覆盖:
- 默认 persona → 行为不变(无白名单过滤,system prompt 无 addendum)
- critic persona → 黑名单覆盖 → 无 MCP 工具暴露给 LLM
- researcher persona → 只允许 search/* → image 工具被剥
- system prompt 含 [Step Persona: critic] 段 + readonly / structured 约束
- budget_tokens → max_tokens 透传(通过解析函数验证)
"""

from __future__ import annotations

from uuid import uuid4

from agents._common.react_personas import get_persona
from agents._common.react_runner import (
    _build_tools,
    _merged_mcp_uris,
    _system_instruction,
)
from agents._common.step_persona import (
    resolve_budget_tokens,
    resolve_step_persona_for_task,
)
from agents._common.protocol import AgentTask


def _mk_task(
    *,
    task_type: str = "long_writing",
    mcp_tools: list[str] | None = None,
    parameters: dict | None = None,
) -> AgentTask:
    return AgentTask(
        task_id=uuid4(),
        step_id="s1",
        agent_id="agent_1",
        task_type=task_type,
        user_id=uuid4(),
        conversation_id=uuid4(),
        inputs={},
        parameters=parameters or {},
        routing_hints={},
        mcp_tools=mcp_tools or [],
    )


# ─── default persona:行为不变 ───
def test_default_persona_preserves_tools() -> None:
    task = _mk_task(
        mcp_tools=["mcp://search/web_search", "mcp://image_tools/quality_check"],
        parameters={"_planner": {"persona": "default"}},
    )
    worker = get_persona("agent_1")
    sp = resolve_step_persona_for_task(task.parameters)
    assert sp.name == "default"

    parsed = _merged_mcp_uris(task, worker, sp)
    servers = {s for s, _ in parsed}
    assert "search" in servers
    assert "image_tools" in servers


def test_default_persona_no_addendum_in_system() -> None:
    task = _mk_task(parameters={"_planner": {"persona": "default"}})
    worker = get_persona("agent_1")
    sp = resolve_step_persona_for_task(task.parameters)
    sysmsg = _system_instruction(task, worker, sp)
    assert "[Step Persona" not in sysmsg


# ─── critic:黑名单全 + addendum ───
def test_critic_persona_blocks_all_mcp() -> None:
    task = _mk_task(
        mcp_tools=["mcp://search/web_search", "mcp://image_tools/quality_check"],
        parameters={"_planner": {"persona": "critic"}},
    )
    worker = get_persona("agent_1")
    sp = resolve_step_persona_for_task(task.parameters)
    assert sp.name == "critic"

    parsed = _merged_mcp_uris(task, worker, sp)
    # critic 禁所有 MCP
    assert parsed == []


def test_critic_system_prompt_has_constraints() -> None:
    task = _mk_task(
        task_type="long_writing",
        parameters={"_planner": {"persona": "critic"}},
    )
    worker = get_persona("agent_1")
    sp = resolve_step_persona_for_task(task.parameters)
    sysmsg = _system_instruction(task, worker, sp)
    # 含人格段
    assert "[Step Persona: critic]" in sysmsg
    # 只读约束
    assert "只读" in sysmsg
    # 结构化输出约束
    assert "structured_payload" in sysmsg
    assert "structured" in sysmsg


def test_critic_build_tools_only_has_finish() -> None:
    """critic 拒所有 MCP → tools 只剩 agent_finish。"""
    task = _mk_task(
        mcp_tools=["mcp://search/web_search"],
        parameters={"_planner": {"persona": "critic"}},
    )
    worker = get_persona("agent_1")
    sp = resolve_step_persona_for_task(task.parameters)
    tools, name_map = _build_tools(task, worker, sp)
    fn_names = {t["function"]["name"] for t in tools}
    assert "agent_finish" in fn_names
    assert all("mcp_" not in n for n in fn_names)
    assert name_map == {}


# ─── researcher:只允许 search/* ───
def test_researcher_filters_to_search_only() -> None:
    task = _mk_task(
        mcp_tools=[
            "mcp://search/web_search",
            "mcp://search/web_fetch",
            "mcp://image_tools/quality_check",
            "mcp://video_tools/compose",
        ],
        parameters={"_planner": {"persona": "researcher"}},
    )
    worker = get_persona("agent_1")
    sp = resolve_step_persona_for_task(task.parameters)
    parsed = _merged_mcp_uris(task, worker, sp)
    servers = {s for s, _ in parsed}
    assert "search" in servers
    # image / video 工具被剥
    assert "image_tools" not in servers
    assert "video_tools" not in servers


# ─── budget tokens ───
def test_budget_tokens_extracted_from_planner_meta() -> None:
    task = _mk_task(parameters={"_planner": {"budget_tokens": 8000}})
    n = resolve_budget_tokens(task.parameters, default=2000)
    assert n == 8000


def test_budget_tokens_no_planner_meta_uses_default() -> None:
    task = _mk_task()
    assert resolve_budget_tokens(task.parameters, default=2000) == 2000
    assert resolve_budget_tokens(task.parameters, default=None) is None


# ─── unknown persona 降级 default ───
def test_unknown_persona_falls_back_silently() -> None:
    task = _mk_task(
        mcp_tools=["mcp://search/web_search"],
        parameters={"_planner": {"persona": "completely-made-up"}},
    )
    worker = get_persona("agent_1")
    sp = resolve_step_persona_for_task(task.parameters)
    assert sp.name == "default"
    # 工具不被过滤
    parsed = _merged_mcp_uris(task, worker, sp)
    assert any(s == "search" for s, _ in parsed)


# ─── art_director:可调 image_tools.quality_check + search ───
def test_art_director_allows_design_tools() -> None:
    task = _mk_task(
        mcp_tools=[
            "mcp://image_tools/quality_check",
            "mcp://image_tools/download_batch",
            "mcp://search/web_search",
        ],
        parameters={"_planner": {"persona": "art_director"}},
    )
    worker = get_persona("agent_3")
    sp = resolve_step_persona_for_task(task.parameters)
    parsed = _merged_mcp_uris(task, worker, sp)
    pairs = set(parsed)
    assert ("image_tools", "quality_check") in pairs
    assert ("search", "web_search") in pairs
    # download_batch 不在 art_director 白名单
    assert ("image_tools", "download_batch") not in pairs
