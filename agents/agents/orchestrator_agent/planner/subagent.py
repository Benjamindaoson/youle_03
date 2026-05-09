"""Subagent spawn 原语 — context-isolated 子任务(ADR-019)。

# 为什么是主编排层的原语,不是 Worker 的能力
ADR-002:Worker 不互相调用。Subagent 这个原语**只能由主编排层(Planner /
Critic / 主 ReAct loop 的特定节点)发起**,因为它本质上是"启动一个独立任
务上下文,跑完返回结构化结果"。它不破坏 Worker 边界 — 子任务最终仍走
Redis Streams + AgentTask + Worker 消费。

# 本文件的角色
S1 阶段:**接口冻结 + 内存级实现 + 单测**。
    - `Subagent.spawn(goal, ...)` 直接调认知层 LLM,产出结构化 JSON 返回。
    - 不递归启动新 LangGraph 子图(那是 S3 的活)。
    - 用于:Planner 内部分治、Critic 给评分、Reflexion 写改进建议等。

S3 阶段:升级为"递归子图"
    - 子任务 = 一份小 Plan + 独立 LangGraphTaskRunner 实例
    - 父任务在 LangGraph 节点里 await 子图完成
    - context 隔离 = 子图自己的 state,不污染父 state

# 与 Anthropic Task tool 的对应
spawn(goal, persona, return_schema)
   ≈ Task(prompt=goal, system_prompt=persona, output_schema=return_schema)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError as PydanticValidationError

from agents._common.llm import LITELLM_MOCK, complete_cognitive

log = structlog.get_logger(__name__)

DEFAULT_BUDGET_TOKENS = int(os.getenv("SUBAGENT_DEFAULT_BUDGET_TOKENS", "4000"))
SUBAGENT_MAX_DEPTH = int(os.getenv("SUBAGENT_MAX_DEPTH", "3"))


@dataclass
class SubagentResult:
    """spawn 的返回 — 结构化数据 + 元信息。"""

    subagent_id: str
    goal: str
    output: dict[str, Any] | str
    cost_usd: float | None
    duration_ms: int | None
    model_used: str
    depth: int
    status: str  # "completed" | "failed"
    error: str | None = None


class SubagentBudgetExceededError(RuntimeError):
    """超出预算或递归深度限制。"""


_PERSONA_PROMPTS: dict[str, str] = {
    "default": "你是一个高效的 AI 助手,完成主编排器交给你的子任务。",
    "researcher": (
        "你是研究员。基于已有信息,产出结构化研究摘要。"
        "如有不确定的地方明确指出,不要编造。"
    ),
    "critic": (
        "你是质量评审员。读完产物后,给出 score(0..1)、issues 列表、"
        "should_replan(bool)、和具体改进建议。只输出 JSON。"
    ),
    "art_director": (
        "你是艺术指导。基于品牌调性与产物简报,产出图像/视觉风格指南。"
    ),
    "fact_checker": (
        "你是事实核查员。逐条比对产物中的事实声明与已知来源。"
        "不确定的标记为'存疑',不要补全或猜测。"
    ),
    "compliance": (
        "你是合规审核员。识别广告法 / 内容安全 / 平台规范风险,"
        "给出 violations 列表与 severity。只输出 JSON。"
    ),
}

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


class Subagent:
    """主编排层的子任务 spawn 入口。

    用法:
        result = await Subagent.spawn(
            goal="基于 research 产出 critique",
            persona="critic",
            inputs={"artifact_text": "..."},
            return_schema=CritiqueModel,
        )
    """

    @staticmethod
    async def spawn(
        *,
        goal: str,
        persona: str = "default",
        inputs: dict[str, Any] | None = None,
        return_schema: type[BaseModel] | None = None,
        budget_tokens: int = DEFAULT_BUDGET_TOKENS,
        depth: int = 0,
        parent_subagent_id: str | None = None,
    ) -> SubagentResult:
        if depth >= SUBAGENT_MAX_DEPTH:
            raise SubagentBudgetExceededError(
                f"subagent depth {depth} ≥ SUBAGENT_MAX_DEPTH={SUBAGENT_MAX_DEPTH}"
            )
        if budget_tokens > 32000:
            raise SubagentBudgetExceededError(
                f"budget_tokens={budget_tokens} > 32000 (硬上限,防止滥用)"
            )

        sid = "sub-" + uuid.uuid4().hex[:10]
        system = _PERSONA_PROMPTS.get(persona, _PERSONA_PROMPTS["default"])
        user = _build_user_prompt(goal=goal, inputs=inputs, return_schema=return_schema)

        log.info(
            "subagent.spawn",
            subagent_id=sid,
            persona=persona,
            depth=depth,
            parent=parent_subagent_id,
        )

        if LITELLM_MOCK:
            return _mock_spawn(sid, goal, persona, return_schema, depth)

        try:
            resp = await complete_cognitive(
                purpose=f"subagent:{persona}",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                response_format=(
                    {"type": "json_object"} if return_schema is not None else None
                ),
                max_tokens=budget_tokens,
            )
        except Exception as e:  # 上游网络 / 模型 / 限流
            log.warning("subagent.llm_fail", subagent_id=sid, err=str(e)[:200])
            return SubagentResult(
                subagent_id=sid,
                goal=goal,
                output={},
                cost_usd=None,
                duration_ms=None,
                model_used="unknown",
                depth=depth,
                status="failed",
                error=str(e)[:500],
            )

        raw = resp.content.strip()
        output: dict[str, Any] | str = raw
        if return_schema is not None:
            parsed = _safe_extract_json(raw)
            try:
                # Pydantic 校验,不通过则回退到 raw
                obj = return_schema(**parsed)
                output = obj.model_dump()
            except PydanticValidationError as e:
                log.warning("subagent.schema_fail", subagent_id=sid, err=str(e)[:200])
                output = parsed

        return SubagentResult(
            subagent_id=sid,
            goal=goal,
            output=output,
            cost_usd=resp.cost_usd,
            duration_ms=None,
            model_used=resp.model,
            depth=depth,
            status="completed",
        )


# ─────────────────────────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────────────────────────
def _build_user_prompt(
    *,
    goal: str,
    inputs: dict[str, Any] | None,
    return_schema: type[BaseModel] | None,
) -> str:
    parts = [f"# 任务\n{goal}"]
    if inputs:
        parts.append(f"# 输入\n```json\n{json.dumps(inputs, ensure_ascii=False, indent=2)}\n```")
    if return_schema is not None:
        parts.append(
            f"# 输出 schema(必须是合法 JSON,字段如下)\n"
            f"```json\n{json.dumps(return_schema.model_json_schema(), ensure_ascii=False, indent=2)}\n```\n\n"
            "请只输出符合 schema 的 JSON,不要 markdown 包裹、不要解释文字。"
        )
    return "\n\n".join(parts)


def _safe_extract_json(raw: str) -> dict[str, Any]:
    s = raw.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    m = _JSON_FENCE_RE.search(s)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    lo, hi = s.find("{"), s.rfind("}")
    if 0 <= lo < hi:
        try:
            return json.loads(s[lo : hi + 1])
        except json.JSONDecodeError:
            pass
    return {}


def _mock_spawn(
    sid: str,
    goal: str,
    persona: str,
    return_schema: type[BaseModel] | None,
    depth: int,
) -> SubagentResult:
    if return_schema is not None:
        # 给出 schema 默认值的最小有效对象
        try:
            obj = return_schema()  # type: ignore[call-arg]
            output: dict[str, Any] | str = obj.model_dump()
        except Exception:
            output = {"_mock": True, "persona": persona}
    else:
        output = f"[mock subagent:{persona}] {goal[:300]}"
    return SubagentResult(
        subagent_id=sid,
        goal=goal,
        output=output,
        cost_usd=0.0,
        duration_ms=10,
        model_used="mock",
        depth=depth,
        status="completed",
    )
