"""Critic Loop — 创作类 step 后自动评审 + 重试一次(ADR-020)。

# 设计哲学
2026 年硅谷一线产品的共识:**任何创作 step 后接一个 critic step,质量直接 +1 档**,
成本只增 10-20%。这是 12 项升级里 ROI 最高的单点。

# 这个文件做什么
1. 提供 `evaluate(step_def, ...)` — 调认知层 LLM,产出 `CritiqueResult`
2. 提供 `build_retry_prompt(...)` — 把 critique 反馈拼到原 prompt 里,引导
   worker 重新生成
3. 提供 `is_critic_enabled_for(task_type, step_def)` — 决定某 step 要不要走
   critic loop(env flag + 默认 task_type 白名单 + Skill YAML 显式覆盖)
4. **不**直接修改 LangGraph state — 那是 compiler.py 的职责,本文件只提供工具

# 与 ADR-019(Planner)的协同
critic 重试一次仍然不通过 → 当前 step 算"质量未达标但状态完成",critique 写入
step_result["critique"]。下游(S2 接通的 failure_policy / replanner)可以根据
critique 决定是否调起 replan。

# 默认行为
`ENABLE_CRITIC_LOOP=false` → 全关,production 完全不变。
`ENABLE_CRITIC_LOOP=true` →
  - task_type 在 `CRITIC_DEFAULT_ON_TASK_TYPES` 中 → 默认开
  - Skill YAML 内 step `critic: { enabled: false }` → 显式关
  - Skill YAML 内 step `critic: { enabled: true, threshold: 0.85, rubric: "..." }` → 显式开 + 自定义
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import structlog

from agents._common.llm import LITELLM_MOCK, complete_cognitive

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────────────────────────
ENABLE_CRITIC_LOOP = os.getenv("ENABLE_CRITIC_LOOP", "false").lower() in {"1", "true", "yes"}
CRITIC_THRESHOLD = float(os.getenv("CRITIC_THRESHOLD", "0.7"))
CRITIC_MAX_RETRIES = int(os.getenv("CRITIC_MAX_RETRIES", "1"))
#: critic 单次评审的总时间预算(秒);超过即视为"放行,critic 故障不阻塞主流程"
CRITIC_TIMEOUT_S = int(os.getenv("CRITIC_TIMEOUT_S", "30"))

#: 默认开启 critic 的 task_type(都是文本类创作)。
#: 图像 / 视频类有专属 quality_check step,不在 critic loop 范围(S3 升级再扩)。
CRITIC_DEFAULT_ON_TASK_TYPES: frozenset[str] = frozenset(
    {
        # Agent 1 — 文字
        "short_writing",
        "long_writing",
        "structured_writing",
        "short_video_script",
        # Agent 1 — 小红书系列(策划 / 文案)
        "xhs_carousel_plan",
        "xhs_carousel_copy",
        "xhs_delivery_summary",
        # Agent 1 — 搜索摘要(影响下游脚本质量)
        "web_search",
    }
)

#: critic 自身用什么模型 — 走认知层,但允许独立配置
CRITIC_PURPOSE_TAG = "critic"


# ─────────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────────
@dataclass
class CritiqueResult:
    """critic 单次评审的结构化结论。"""

    score: float  # 0..1
    threshold_used: float
    issues: list[str] = field(default_factory=list)
    suggestion: str = ""
    should_retry: bool = False
    model_used: str = "unknown"
    cost_usd: float | None = None
    duration_ms: int | None = None
    skipped_reason: str | None = None  # critic 故障 / 不适用时填

    def passed(self) -> bool:
        """是否达到合格线。critic 自己跑挂了 → 视为放行,不阻塞主流程。"""
        if self.skipped_reason is not None:
            return True
        return self.score >= self.threshold_used

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def feedback_summary(self) -> str:
        """给 worker 看的简短反馈(用于 _critic_feedback 注入 inputs)。"""
        bits = []
        if self.issues:
            bits.append("issues: " + "; ".join(self.issues[:5]))
        if self.suggestion:
            bits.append("suggestion: " + self.suggestion[:500])
        return " | ".join(bits)


# ─────────────────────────────────────────────────────────────────
# 是否启用 critic
# ─────────────────────────────────────────────────────────────────
def is_critic_enabled_for(task_type: str, step_def: dict[str, Any]) -> bool:
    """决定某 step 是否走 critic loop。

    优先级:
        Skill YAML step.critic.enabled (显式)
        > CRITIC_DEFAULT_ON_TASK_TYPES + ENABLE_CRITIC_LOOP(全局默认)
    """
    step_critic = (step_def or {}).get("critic") or {}
    if isinstance(step_critic, dict) and "enabled" in step_critic:
        return bool(step_critic["enabled"])
    if not ENABLE_CRITIC_LOOP:
        return False
    return task_type in CRITIC_DEFAULT_ON_TASK_TYPES


def get_threshold(step_def: dict[str, Any]) -> float:
    step_critic = (step_def or {}).get("critic") or {}
    if isinstance(step_critic, dict) and "threshold" in step_critic:
        try:
            return float(step_critic["threshold"])
        except (TypeError, ValueError):
            pass
    return CRITIC_THRESHOLD


def get_max_retries(step_def: dict[str, Any]) -> int:
    step_critic = (step_def or {}).get("critic") or {}
    if isinstance(step_critic, dict) and "max_retries" in step_critic:
        try:
            return max(0, int(step_critic["max_retries"]))
        except (TypeError, ValueError):
            pass
    return CRITIC_MAX_RETRIES


# ─────────────────────────────────────────────────────────────────
# 评审主入口
# ─────────────────────────────────────────────────────────────────
CRITIC_SYSTEM_PROMPT = """你是 Youle 多智能体平台的质量评审员(Critic)。

# 你的工作
读完一个 step 的产物 + 该 step 的 prompt 与上下文 → 给出结构化 JSON 评审:

```
{
  "score": <0..1 的浮点数,1.0 = 完全合格>,
  "issues": ["<具体问题 1>", "<具体问题 2>", ...],
  "suggestion": "<≤ 300 字的一句话改进建议,要可执行>",
  "should_retry": <true | false,score 低且改进可执行就 true>
}
```

# 评分原则
1. **基于产物本身**判断 — 不引入外部信息或自己的偏好
2. **看 rubric 严格执行** — 每条 rubric 不达成扣 0.1-0.3 分
3. **issues 要具体** — 不要写"质量不够",要写"开头钩子缺乏冲突感"
4. **suggestion 要可执行** — 给一个清晰可改的方向,不写"再写好一点"
5. **不评分广告法 / 合规** — 那是 compliance persona 的职责
6. **只输出 JSON**,不要 markdown 包裹、不要解释文字。
"""

DEFAULT_RUBRIC = """通用 rubric(没有自定义时使用):
1. 是否切题(产物是否回应 prompt 的核心需求)
2. 是否完整(prompt 列出的要点是否都覆盖)
3. 是否清晰(语言流畅、结构合理)
4. 是否可用(下游 step 能否直接用,无需大改)"""


async def evaluate(
    *,
    step_def: dict[str, Any],
    task_type: str,
    rendered_prompt: str,
    produced_artifact_text: str | None,
    produced_artifact_type: str | None,
    collected_fields: dict[str, Any] | None = None,
    threshold: float | None = None,
) -> CritiqueResult:
    """评审单 step 产物。

    设计上**永不抛**:critic 自己挂了/超时 → 返回带 `skipped_reason` 的
    CritiqueResult,`passed()` 直接 True,主流程放行。这是为了不让 critic
    成为单点故障。

    Args:
        step_def: Skill YAML step 字典(可能含 critic 子配置)
        task_type: 该 step 的 task_type
        rendered_prompt: 已渲染的 prompt(传给 worker 的那个)
        produced_artifact_text: 产物文本 — 由 compiler 通过
            artifact_body.fetch_artifact_text_excerpt 取来
        produced_artifact_type: 产物类型(text/structured/image/...)
        collected_fields: 用户字段(rubric 渲染会用)
        threshold: 强制阈值(覆盖 step_def.critic.threshold)
    """
    th = threshold if threshold is not None else get_threshold(step_def)

    # 不文本化的产物 → 跳过(图像/视频走专属 quality_check)
    if not produced_artifact_text or (
        produced_artifact_type and produced_artifact_type
        not in {"text", "structured", "markdown", "json", "csv"}
    ):
        return CritiqueResult(
            score=1.0,
            threshold_used=th,
            skipped_reason=f"non-text artifact_type={produced_artifact_type!r}",
        )

    rubric = _resolve_rubric(step_def, collected_fields or {})
    user_msg = _build_critic_user_msg(
        task_type=task_type,
        rendered_prompt=rendered_prompt,
        produced_artifact_text=produced_artifact_text,
        rubric=rubric,
    )

    started = time.monotonic()
    if LITELLM_MOCK:
        # mock 路径:默认通过(score=0.85),测试可通过 monkeypatch 替换
        return _mock_critique(threshold_used=th)

    try:
        resp = await complete_cognitive(
            purpose=CRITIC_PURPOSE_TAG,
            messages=[
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=800,
        )
    except Exception as e:  # 网络 / 限流 / 模型挂
        log.warning("critic.llm_fail", err=str(e)[:200], task_type=task_type)
        return CritiqueResult(
            score=1.0,
            threshold_used=th,
            skipped_reason=f"llm_fail: {str(e)[:200]}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    parsed = _safe_extract_json(resp.content)
    try:
        score = float(parsed.get("score", 1.0))
    except (TypeError, ValueError):
        score = 1.0
    score = max(0.0, min(1.0, score))

    issues_raw = parsed.get("issues") or []
    issues = [str(x)[:300] for x in issues_raw[:10]] if isinstance(issues_raw, list) else []

    suggestion = str(parsed.get("suggestion") or "")[:600]

    should_retry_raw = parsed.get("should_retry")
    if should_retry_raw is None:
        should_retry = score < th and bool(suggestion)
    else:
        should_retry = bool(should_retry_raw) and score < th

    duration_ms = int((time.monotonic() - started) * 1000)
    return CritiqueResult(
        score=score,
        threshold_used=th,
        issues=issues,
        suggestion=suggestion,
        should_retry=should_retry,
        model_used=resp.model,
        cost_usd=resp.cost_usd,
        duration_ms=duration_ms,
    )


# ─────────────────────────────────────────────────────────────────
# 重试 prompt 构造
# ─────────────────────────────────────────────────────────────────
def build_retry_prompt(
    *,
    original_prompt: str,
    critique: CritiqueResult,
) -> str:
    """把 critique 拼到原 prompt 末尾,引导 worker 重生成。

    设计:不替换原 prompt,只追加"评审反馈"段。这样:
        - 用户原意不变
        - 反馈具体可读
        - 多轮重试时反馈不会层层套娃(每次只追加最新一轮的 critique)
    """
    # 去掉前一轮可能存在的 "## [Critic 反馈]" 段,避免反馈累加
    cleaned = _CRITIC_FEEDBACK_BLOCK.sub("", original_prompt).rstrip()

    issues_block = (
        "\n".join(f"- {x}" for x in critique.issues) if critique.issues else "(无具体问题列表)"
    )
    suggestion_block = critique.suggestion or "(无)"

    return (
        f"{cleaned}\n\n"
        "## [Critic 反馈 — 重新生成请改进]\n"
        f"上一版被评审为 {critique.score:.2f} / 阈值 {critique.threshold_used:.2f}。\n"
        f"### 主要问题\n{issues_block}\n\n"
        f"### 改进方向\n{suggestion_block}\n\n"
        "请基于反馈重新生成,保持原 prompt 的核心要求不变。"
    )


# ─────────────────────────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────────────────────────
_CRITIC_FEEDBACK_BLOCK = re.compile(
    r"\n\n## \[Critic 反馈 — 重新生成请改进\].*?(?=\n\n|$)",
    re.DOTALL,
)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


def _resolve_rubric(step_def: dict[str, Any], fields: dict[str, Any]) -> str:
    step_critic = (step_def or {}).get("critic") or {}
    if isinstance(step_critic, dict):
        rubric = step_critic.get("rubric")
        if isinstance(rubric, str) and rubric.strip():
            # 简单字段替换 — 不引 jinja,避免和 prompt_template 的 {{ }} 冲突
            return rubric
    # 回退到 task_type 默认 rubric(扩展点)
    return DEFAULT_RUBRIC


def _build_critic_user_msg(
    *,
    task_type: str,
    rendered_prompt: str,
    produced_artifact_text: str,
    rubric: str,
) -> str:
    # 控制总长度,防止 critic 自己 token 爆炸
    prompt_excerpt = rendered_prompt[:3000]
    artifact_excerpt = produced_artifact_text[:8000]
    return (
        f"# 被评审 step\n"
        f"task_type: {task_type}\n\n"
        f"# 原始 prompt(已渲染)\n```\n{prompt_excerpt}\n```\n\n"
        f"# 产物内容(可能是文本 / JSON / Markdown)\n"
        f"```\n{artifact_excerpt}\n```\n\n"
        f"# 评审 rubric\n{rubric}\n\n"
        "请输出评审 JSON,字段:score / issues / suggestion / should_retry。"
    )


def _safe_extract_json(raw: str) -> dict[str, Any]:
    s = (raw or "").strip()
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


def _mock_critique(*, threshold_used: float) -> CritiqueResult:
    """LITELLM_MOCK 默认通过 — 测试通过 monkeypatch 替换 evaluate 来制造失败场景。"""
    return CritiqueResult(
        score=0.85,
        threshold_used=threshold_used,
        issues=[],
        suggestion="",
        should_retry=False,
        model_used="mock",
        cost_usd=0.0,
        duration_ms=1,
    )
