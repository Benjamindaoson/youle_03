"""Step Persona — 能力维度的 worker 上层人格(ADR-021)。

# 与 ReactPersona(worker persona)的关系
- `ReactPersona`(react_personas.py)= **worker 维度**:agent_1..4 的进程级身份
  ("文字与调研专员" / "设计专员" / ...),按媒介分。
- `StepPersona`(本文件)= **能力维度**:Planner 在 plan 里给单个 step 指定的
  角色身份(researcher / critic / fact_checker / ...),按职责分。

两者**正交,组合应用**:
    final system prompt = ReactPersona.title + frugality_rules
                        + StepPersona.addendum

工具白名单:
    final tools = (Skill.mcp_tools ∪ ReactPersona.default_mcp_uris)
                ∩ StepPersona.allowed_pattern
                ∖ StepPersona.denied_pattern

# 数据来源
Plan 在 `Plan.to_skill_yaml()` 阶段把 persona 名字写进 step.parameters._planner.persona,
react_runner.py 从 `task.parameters._planner.persona` 取出来。

# 默认行为
未指定 persona / 指定了 unknown 名字 → fall back to `default`(零改动)。
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger(__name__)

ENABLE_STEP_PERSONA = os.getenv("ENABLE_STEP_PERSONA", "true").lower() in {
    "1",
    "true",
    "yes",
}
#: budget_tokens 硬上限 — 防止 plan 写大数搞挂 worker
STEP_PERSONA_MAX_BUDGET_TOKENS = int(os.getenv("STEP_PERSONA_MAX_BUDGET_TOKENS", "32000"))


@dataclass(frozen=True)
class StepPersona:
    """单个 step 的能力人格。

    Args:
        name: 注册名,与 plan_schema.PlanStep.persona 对应
        addendum: 追加到 system prompt 末尾的指引(简明)
        allowed_pattern: MCP URI 白名单(fnmatch 语义,如 `mcp://search/*`);空 = 不限制
        denied_pattern: 黑名单,优先级高于白名单
        forced_artifact_type: 强制 agent_finish 的 artifact_type(critic 用 structured)
        temperature: 覆盖 ReAct 默认温度(critic 0.1,creative 0.5)
        readonly: True 则禁止任何外部副作用工具(只允许 search/fetch 类读)
        require_structured_output: 必须用 structured_payload 返回
    """

    name: str
    addendum: str = ""
    allowed_pattern: tuple[str, ...] = ()
    denied_pattern: tuple[str, ...] = ()
    forced_artifact_type: str | None = None
    temperature: float | None = None
    readonly: bool = False
    require_structured_output: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────
# 注册表
# ─────────────────────────────────────────────────────────────────
_REGISTRY: dict[str, StepPersona] = {
    "default": StepPersona(name="default"),
    "researcher": StepPersona(
        name="researcher",
        addendum=(
            "你现在以**研究员**身份工作。"
            "优先 web_search / web_fetch 收集信息,产出结构化研究摘要。"
            "对不确定的事实明确标注'存疑',不要编造。"
            "整理来源链接,后续 step 才好引用。"
        ),
        allowed_pattern=(
            "mcp://search/*",
            "mcp://document_tools/pdf_extract",
            "mcp://oss/sign_url",
        ),
        readonly=True,
    ),
    "critic": StepPersona(
        name="critic",
        addendum=(
            "你现在以**质量评审员**身份工作。"
            "**只读**产物,**不修改**。输出 score(0..1)+ issues + suggestion + should_retry,"
            "用 structured_payload 返回,artifact_type=structured。"
            "不调用任何外部工具,不发起 MCP 请求 — 评审是纯认知任务。"
        ),
        allowed_pattern=(),  # 空白名单 + 黑名单全 = 实际不允许任何 MCP
        denied_pattern=("mcp://*",),
        forced_artifact_type="structured",
        temperature=0.1,
        readonly=True,
        require_structured_output=True,
    ),
    "fact_checker": StepPersona(
        name="fact_checker",
        addendum=(
            "你现在以**事实核查员**身份工作。"
            "对产物中的每条事实声明逐条核对,标记为 verified / disputed / unverifiable。"
            "用 structured_payload 返回 list of {claim, status, source_url?, note?}。"
            "不确定的标 unverifiable,**不要补全或猜测**。"
        ),
        allowed_pattern=("mcp://search/*",),
        forced_artifact_type="structured",
        temperature=0.1,
        readonly=True,
        require_structured_output=True,
    ),
    "art_director": StepPersona(
        name="art_director",
        addendum=(
            "你现在以**艺术指导**身份工作。"
            "基于品牌调性 + 上游产物简报,产出**视觉风格指南**(palette / mood / "
            "composition / typography),不直接生成图像 — 把指南交给下游 image_generate step。"
        ),
        allowed_pattern=("mcp://image_tools/quality_check", "mcp://search/*"),
        forced_artifact_type="structured",
        temperature=0.4,
    ),
    "editor": StepPersona(
        name="editor",
        addendum=(
            "你现在以**编辑**身份工作。"
            "对上游产物做**润色 / 结构调整 / 表述优化**,保留事实和原意,"
            "不引入新事实声明。如果产物有事实问题,明确指出并请求 fact_checker 介入。"
        ),
        allowed_pattern=(),
        denied_pattern=("mcp://*",),  # 编辑不调外部工具
        temperature=0.3,
    ),
    "seo_specialist": StepPersona(
        name="seo_specialist",
        addendum=(
            "你现在以**SEO 专员**身份工作。"
            "基于产物 + 关键词调研,输出标题 / meta description / H1-H3 建议 / 长尾词建议。"
            "用 structured_payload 返回。"
        ),
        allowed_pattern=("mcp://search/*",),
        forced_artifact_type="structured",
        temperature=0.3,
        require_structured_output=True,
    ),
    "compliance": StepPersona(
        name="compliance",
        addendum=(
            "你现在以**合规审核员**身份工作。"
            "识别广告法 / 内容安全 / 平台规范风险,输出 list of "
            "{violation_type, severity, excerpt, suggestion}。"
            "**只读**,不修改产物。用 structured_payload。"
        ),
        allowed_pattern=("mcp://search/web_fetch",),
        forced_artifact_type="structured",
        temperature=0.1,
        readonly=True,
        require_structured_output=True,
    ),
}


def get_step_persona(name: str | None) -> StepPersona:
    """从注册表查 persona;不存在 / None / 空 → default。

    永不抛 — persona 名字异常不该让任务挂。
    """
    if not name or not isinstance(name, str):
        return _REGISTRY["default"]
    if not ENABLE_STEP_PERSONA:
        return _REGISTRY["default"]
    p = _REGISTRY.get(name.strip().lower())
    if p is None:
        log.warning("step_persona.unknown", name=name)
        return _REGISTRY["default"]
    return p


def list_personas() -> list[str]:
    return list(_REGISTRY.keys())


def register_persona(persona: StepPersona, *, override: bool = False) -> None:
    """主要用于测试 / 二开扩展;production 通过修改本文件直接加。"""
    key = persona.name.strip().lower()
    if not override and key in _REGISTRY:
        raise ValueError(f"persona {key!r} already registered")
    _REGISTRY[key] = persona


# ─────────────────────────────────────────────────────────────────
# AgentTask 上提取 persona 元信息(plan_schema 已经把这些放进了 _planner)
# ─────────────────────────────────────────────────────────────────
def extract_planner_meta(task_parameters: dict[str, Any] | None) -> dict[str, Any]:
    """从 task.parameters 取出 ADR-019 写入的 _planner 元信息。

    返回总是 dict(空 dict 即未注入)。
    """
    if not isinstance(task_parameters, dict):
        return {}
    meta = task_parameters.get("_planner")
    return dict(meta) if isinstance(meta, dict) else {}


def resolve_step_persona_for_task(task_parameters: dict[str, Any] | None) -> StepPersona:
    """便利函数:给 react_runner 一行解析。"""
    meta = extract_planner_meta(task_parameters)
    return get_step_persona(meta.get("persona"))


def resolve_budget_tokens(
    task_parameters: dict[str, Any] | None, *, default: int | None
) -> int | None:
    """从 _planner.budget_tokens 取预算,带硬上限保护。

    None → 用 default;default 也是 None → 不设上限。
    """
    meta = extract_planner_meta(task_parameters)
    raw = meta.get("budget_tokens") if isinstance(meta, dict) else None
    if raw is None:
        return default
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    if n <= 0:
        return default
    return min(n, STEP_PERSONA_MAX_BUDGET_TOKENS)


# ─────────────────────────────────────────────────────────────────
# 工具白名单过滤
# ─────────────────────────────────────────────────────────────────
def filter_mcp_uris_by_persona(
    uris: list[str], persona: StepPersona
) -> tuple[list[str], list[str]]:
    """按 persona 的 allowed/denied 模式过滤 MCP URI 列表。

    Returns:
        (kept, dropped) 两个列表 — kept 是允许的,dropped 是被 persona 拒绝的(供日志用)。

    规则:
      - denied_pattern 命中 → 拒绝(优先级最高)
      - allowed_pattern 为空 → 不限制(只看 denied)
      - allowed_pattern 非空 → URI 必须命中至少一条 allowed_pattern
    """
    kept: list[str] = []
    dropped: list[str] = []
    for u in uris:
        if not isinstance(u, str) or not u.strip():
            continue
        if any(fnmatch.fnmatchcase(u, pat) for pat in persona.denied_pattern):
            dropped.append(u)
            continue
        if persona.allowed_pattern and not any(
            fnmatch.fnmatchcase(u, pat) for pat in persona.allowed_pattern
        ):
            dropped.append(u)
            continue
        kept.append(u)
    return kept, dropped
