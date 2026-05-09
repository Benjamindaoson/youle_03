"""Planner Agent — 主规划官(ADR-019)。

职责:
    用户请求 → 调用认知层 LLM → 产出 `Plan(JSON)`。

不负责:
    Plan 的执行(交给 dynamic_compiler + LangGraphTaskRunner)。
    Skill 匹配(那是 messages.py 的 Skill matcher,只有匹配不到时才轮到 Planner)。
    HITL / 中断处理(由 runner 自己处理,Plan 里只声明 hitl_gate 位置)。

LITELLM_MOCK 模式下走 mock 路径(返回一份合法的最小 Plan),保证单测离线可跑。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

import structlog
from pydantic import ValidationError as PydanticValidationError

from agents._common.llm import COGNITIVE_TIER, LITELLM_MOCK, complete_cognitive
from agents._common.skill_registry import (
    PlaybookIndex,
    SkillRegistry,
    get_default_registry,
)
from agents.orchestrator_agent.planner.episode_retrieval import (
    Episode,
    format_episodes_for_prompt,
    retrieve_similar_episodes,
    summarize_available_mcp_tools,
    summarize_available_skills,
)
from agents.orchestrator_agent.planner.plan_schema import (
    Plan,
    PlanStep,
    PlanValidationError,
)
from agents.orchestrator_agent.planner.prompts import (
    PLANNER_SYSTEM_PROMPT,
    render_planner_user_prompt,
)

log = structlog.get_logger(__name__)

PLANNER_MAX_RETRIES = int(os.getenv("PLANNER_MAX_RETRIES", "2"))


class PlannerError(RuntimeError):
    """规划失败 — 上游应回退到澄清流程或拒答。"""


async def make_plan(
    *,
    user_request: str,
    user_id: str,
    collected_fields: dict[str, Any] | None = None,
    available_skills_index: list[dict[str, Any]] | None = None,
    available_mcp_tools: list[dict[str, str]] | None = None,
    extra_episodes: list[Episode] | None = None,
    skill_registry: SkillRegistry | None = None,
) -> Plan:
    """主入口:产出一份合法 Plan。

    Args:
        user_request: 用户原始请求文本
        user_id: 用于情景记忆按用户切片
        collected_fields: messages.py 已经从用户那里收齐的结构化字段(若有)
        available_skills_index: 显式 skill 摘要清单 — 若为 None 走 skill_registry
        available_mcp_tools: MCP 注册表提供的工具清单(允许 None,函数兜底)
        extra_episodes: 测试或调试时直接注入的历史样例(覆盖 episode_retrieval)
        skill_registry: 显式注入的注册表(测试 / 自定义目录场景)。
            None → 使用 `get_default_registry()` 自动从 SKILLS_DIR 扫描

    Raises:
        PlannerError: 重试 PLANNER_MAX_RETRIES 次仍拿不到合法 JSON / Plan。
    """
    # ─── ADR-022:差异化呈现 MD Skills 与 YAML Playbooks ───
    if available_skills_index is not None:
        # 调用方已经组好(测试 / 单跳),保持向后兼容
        md_summary = ""
        playbook_summary = summarize_available_skills(available_skills_index)
    else:
        reg = skill_registry or get_default_registry()
        snapshot = reg.summary_for_planner()
        md_summary = _format_md_skills_for_prompt(snapshot["md_skills"])
        playbook_summary = _format_playbooks_for_prompt(snapshot["playbooks"])

    tools_summary = summarize_available_mcp_tools(available_mcp_tools or [])

    if extra_episodes is None:
        episodes = await retrieve_similar_episodes(
            user_request=user_request, user_id=user_id
        )
    else:
        episodes = extra_episodes

    user_prompt = render_planner_user_prompt(
        user_request=user_request,
        available_skills_summary=playbook_summary,
        similar_episodes=format_episodes_for_prompt(episodes),
        available_mcp_tools_summary=tools_summary,
        collected_fields=collected_fields,
        available_md_skills_summary=md_summary,
    )

    last_err: Exception | None = None
    for attempt in range(PLANNER_MAX_RETRIES):
        try:
            plan = await _call_and_parse(
                system_prompt=PLANNER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                attempt=attempt,
            )
            log.info(
                "planner.plan_ok",
                attempt=attempt,
                steps=len(plan.steps),
                plan_id=plan.plan_id,
                user_id=user_id,
            )
            return plan
        except (PlanValidationError, PydanticValidationError, _PlanParseError) as e:
            last_err = e
            log.warning(
                "planner.plan_invalid",
                attempt=attempt,
                err=str(e)[:300],
                user_id=user_id,
            )
            # 下一轮在 user_prompt 末尾追加错误提示,引导 LLM 自我纠正
            user_prompt = (
                user_prompt
                + f"\n\n# 上一次输出无效,错误:{str(e)[:500]}\n请重新输出合法 Plan JSON。"
            )

    raise PlannerError(
        f"planner failed to produce valid plan after {PLANNER_MAX_RETRIES} attempts: {last_err}"
    )


# ─────────────────────────────────────────────────────────────────
# Skill / Playbook 摘要格式化
# ─────────────────────────────────────────────────────────────────
def _format_md_skills_for_prompt(md_skills: list[dict[str, Any]]) -> str:
    """MD Skills(知识)— 给 Planner 看的 name + when_to_use + description 摘要。

    Planner 拿到这份摘要后,可在 step.prompt_template 里引用相应 skill 的知识
    (例如"按 xhs-note-creator 的标题规范")。
    """
    if not md_skills:
        return ""
    lines: list[str] = []
    for s in md_skills:
        sid = s.get("skill_id") or s.get("name") or "?"
        name = s.get("name") or sid
        when = (s.get("when_to_use") or "").strip().replace("\n", " ")[:160]
        desc = (s.get("description") or "").strip().replace("\n", " ")[:200]
        if when:
            lines.append(f"- {sid} ({name}) — when: {when}\n  what: {desc}")
        else:
            lines.append(f"- {sid} ({name}): {desc}")
    return "\n".join(lines)


def _format_playbooks_for_prompt(playbooks: list[dict[str, Any]]) -> str:
    """YAML Playbooks(产线)— 给 Planner 的 name + scenario + keywords 摘要。"""
    if not playbooks:
        return ""
    lines: list[str] = []
    for p in playbooks:
        sid = p.get("skill_id") or "?"
        name = p.get("name") or sid
        kw = p.get("keywords") or []
        kw_part = f" [{','.join(kw[:5])}]" if kw else ""
        desc = (p.get("description") or "").strip().replace("\n", " ")[:160]
        lines.append(f"- {sid} ({name}){kw_part}: {desc}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# 内部:LLM 调用 + JSON 解析 + Plan 校验
# ─────────────────────────────────────────────────────────────────
class _PlanParseError(ValueError):
    """LLM 输出无法解析为 JSON。"""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


async def _call_and_parse(
    *,
    system_prompt: str,
    user_prompt: str,
    attempt: int,
) -> Plan:
    if LITELLM_MOCK:
        # mock 路径:返回一份最小合法 Plan,保证单测/CI 离线跑
        return _mock_plan()

    resp = await complete_cognitive(
        purpose="planner",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2 + 0.1 * attempt,  # 重试稍微抬温度
        response_format={"type": "json_object"},
        max_tokens=4000,
    )

    raw = resp.content.strip()
    parsed = _extract_json(raw)
    parsed.setdefault("source", "planner")
    parsed.setdefault("cognitive_model", resp.model)

    try:
        plan = Plan(**parsed)
    except PydanticValidationError as e:
        raise _PlanParseError(f"pydantic: {e}") from e

    plan.validate_deps()
    return plan


def _extract_json(raw: str) -> dict[str, Any]:
    """从 LLM 输出中抽出 JSON object。

    宽容度:
      - 直接是合法 JSON → 直接 parse
      - 用 ```json``` 包裹 → 先抽 fence
      - 前后有解释文字 → 找首个 `{` 到末个 `}`
    """
    s = raw.strip()
    # 1. 直接 parse
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # 2. ```json ... ```
    m = _JSON_FENCE_RE.search(s)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 3. 暴力切到首尾大括号
    lo, hi = s.find("{"), s.rfind("}")
    if 0 <= lo < hi:
        try:
            return json.loads(s[lo : hi + 1])
        except json.JSONDecodeError as e:
            raise _PlanParseError(f"unparseable JSON: {e}") from e
    raise _PlanParseError("no JSON object found in LLM output")


def _mock_plan() -> Plan:
    """LITELLM_MOCK=true 时返回的 fixture Plan(单测/CI 友好)。

    用一个最小的 2 step plan:research → script。覆盖了:
      - 多 step + depends_on
      - HITL gate
      - persona / mcp_tools / routing_hints
    """
    pid = "mock-" + uuid.uuid4().hex[:8]
    return Plan(
        plan_id=pid,
        rationale="[MOCK] minimal 2-step plan for CI",
        primary_artifact="script",
        steps=[
            PlanStep(
                step_id="research",
                agent="agent_1",
                task_type="web_search",
                persona="researcher",
                depends_on=[],
                timeout=60,
                prompt_template="搜索关于 {{topic}} 的资料",
                inputs={},
                parameters={},
                routing_hints={},
                mcp_tools=["mcp://search/web_search"],
                hitl_gate=None,
                budget_tokens=4000,
                expected_artifact="research summary",
            ),
            PlanStep(
                step_id="script",
                agent="agent_1",
                task_type="long_writing",
                persona="default",
                depends_on=["research"],
                timeout=120,
                prompt_template="基于 {{research.output}} 写一段文案",
                inputs={},
                parameters={},
                routing_hints={},
                mcp_tools=[],
                hitl_gate=None,
                budget_tokens=4000,
                expected_artifact="copy",
            ),
        ],
        source="planner",
        cognitive_model=COGNITIVE_TIER["primary"][0],
    )
