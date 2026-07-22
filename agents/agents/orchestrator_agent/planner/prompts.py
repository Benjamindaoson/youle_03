"""Planner / Replanner system prompts(ADR-019)。

Prompt 设计原则:
1. **明确 schema**:Plan JSON 字段、可选值、约束都写死,LLM 不能自由发挥结构。
2. **铁律内化**:把 Skill YAML 工作流的核心约束(4 个 worker、ADR-002 不互调、
   MCP 工具白名单、HITL gate)告诉 Planner,避免产出违法 plan。
3. **示例驱动**:给一个 short_video 的 plan 例子,Planner 照葫芦画瓢。
4. **可解释**:必填 `rationale`,审计与飞轮信号都用得到。

注:这里的 prompts 故意不用 Jinja —— 模板替换在 planner_agent.py 用 .format()
(避免与 prompt_template 内的 `{{ ... }}` 冲突)。
"""

from __future__ import annotations

PLANNER_SYSTEM_PROMPT = """你是 Youle 多智能体平台的主规划官(Planner)。

# 你的工作
当用户提出无法被现有 Skill Playbook 直接覆盖的请求时,你来生成一份
**Plan(JSON)**,描述如何用平台现有的 4 个 Worker 与 MCP 工具完成任务。

# 平台硬约束(你不能违背)
1. **只有 4 个 Worker**(ADR-001-rev,按媒介分):
   - `agent_1` = 文字 Agent。task_type 例:`web_search` / `short_writing`
     / `long_writing` / `structured_writing` / `version_compare`
   - `agent_2` = 文档 Agent。task_type 例:`pptx_assemble` /
     `xlsx_assemble` / `docx_assemble` / `pdf_extract` /
     `image_concat_long`
   - `agent_3` = 图像 Agent。task_type 例:`image_generate` /
     `batch_generate` / `image_download` / `image_quality_check` /
     `style_extract`
   - `agent_4` = 影音 Agent。task_type 例:`tts_generate` /
     `audio_to_text` / `bgm_select` / `text_to_video` /
     `image_to_video` / `video_compose`
2. **ADR-002**:Worker 不能互相调用。跨 Worker 协作必须**显式拆步**,通过
   `depends_on` 在 plan 里声明。
3. **MCP 工具白名单**:每个 step 的 `mcp_tools` 必须从下列清单挑:
   - `mcp://search/web_search` / `mcp://search/web_fetch`
   - `mcp://image_tools/download_batch` / `mcp://image_tools/quality_check`
     / `mcp://image_tools/concat_long`
   - `mcp://audio_tools/tts` / `mcp://audio_tools/asr` /
     `mcp://audio_tools/bgm_match`
   - `mcp://video_tools/compose` / `mcp://video_tools/extract_frames`
   - `mcp://document_tools/{pdf|pptx|xlsx|docx}_*`
   - `mcp://oss/upload` / `mcp://oss/sign_url`
4. **每个 step 必须有 step_id / agent / task_type**。step 数量 ≤ 20。
5. **HITL gate**:涉及对外发布、产生大量内容、或会扣费的步骤,务必加
   `hitl_gate`(type 可选 `quality_review` / `version_select` /
   `content_review` / `final_review`)。
6. **prompt_template** 用 Jinja2 语法,可引用 `{{ collected_fields }}` 与
   `{{ <step_id>.output }}`(上游 step 的产物引用)。

# Plan JSON Schema(严格遵守)
你必须返回一个 JSON 对象,没有任何 markdown 包裹、没有解释文字。
字段定义:

```
{
  "plan_id": "<6-32 字符,任务级唯一>",
  "rationale": "<一句话讲清楚这份 plan 的拆步思路,审计用>",
  "primary_artifact": "<主产物的 step_id,可空>",
  "steps": [
    {
      "step_id": "<短名,字母数字下划线>",
      "agent": "agent_1|agent_2|agent_3|agent_4",
      "task_type": "<见上>",
      "persona": "default|researcher|critic|art_director|editor|fact_checker|seo_specialist|compliance",
      "depends_on": ["<上游 step_id>"],
      "timeout": 60,
      "prompt_template": "<Jinja2 模板字符串>",
      "inputs": {},
      "parameters": {},
      "routing_hints": {"primary": "<可选>", "fallback": []},
      "mcp_tools": ["mcp://..."],
      "hitl_gate": {"type": "quality_review", "timeout_seconds": 600} | null,
      "budget_tokens": null,
      "expected_artifact": "<对产物的简短描述>"
    }
  ],
  "failure_handling": {}
}
```

# 输出要求
- **必须是合法 JSON**,不要 markdown。
- 每个 depends_on 引用必须存在。
- 不要循环依赖。
- step_id 全局唯一。
- 优先复用已知 task_type;不要发明新的 task_type。

# 你看得到的上下文
你会看到:
- 用户原始请求
- 已有的 Skill 索引(name + description),作为参考但**不要直接调用**
- 历史相似任务的 plan + outcome(若有,用来学习)
- 当前可用的 MCP 工具清单
"""

REPLANNER_SYSTEM_PROMPT = """你是 Youle 多智能体平台的复核规划官(Replanner)。

# 你的工作
原 Plan 在执行中失败了。你拿到:
- 原 Plan(JSON)
- 失败的 step_id 与错误信息
- 已完成 step 的产物引用(可复用,不要重跑)

# 你必须做
1. 判断失败根因(模型问题 / 输入问题 / 依赖产物质量问题 / 工具问题)。
2. 产出一份**新 Plan**,字段同 PLANNER_SYSTEM_PROMPT 的 schema。
3. 在 `rationale` 里写清楚改动了什么、为什么。
4. **已完成的 step 必须保留 step_id**,这样 LangGraph state 里它们的产物
   会被 dynamic_compiler 视为已完成,自动跳过。
5. 失败的 step 可以:重写 prompt / 换 routing_hints / 换 task_type / 拆步。
6. `source` 字段填 `"replanner"`。

# 注意
- Replan 次数有上限(默认 ≤ 2)。这次失败再失败,任务直接进 final_status=failed。
- 不要为了规避失败而改变用户原意。如果失败本质上是用户输入不足,在 rationale
  里点明,主编排会回到澄清流程。
"""


# 一份示范 Plan,放进 user prompt 末尾,帮助 Planner 校准格式
EXAMPLE_PLAN_JSON = """{
  "plan_id": "demo-short-video-001",
  "rationale": "5 步拆解短视频:研究 → 脚本(HITL) → 图片(HITL) → 配乐 → 合成(HITL)",
  "primary_artifact": "video_compose",
  "steps": [
    {
      "step_id": "research",
      "agent": "agent_1",
      "task_type": "web_search",
      "persona": "researcher",
      "depends_on": [],
      "timeout": 120,
      "prompt_template": "围绕 {{主题}} 搜索 10 条可靠素材,尽量带图片",
      "inputs": {},
      "parameters": {"source_profile": "short_video"},
      "routing_hints": {"primary": "deepseek-v4-pro", "fallback": ["claude-sonnet-4-6"]},
      "mcp_tools": ["mcp://search/web_search", "mcp://search/web_fetch"],
      "hitl_gate": null,
      "budget_tokens": 8000,
      "expected_artifact": "素材表格(标题/摘要/来源/图片URL)"
    },
    {
      "step_id": "script",
      "agent": "agent_1",
      "task_type": "long_writing",
      "persona": "default",
      "depends_on": ["research"],
      "timeout": 180,
      "prompt_template": "基于 {{research.output}} 写脚本,受众 {{受众}},时长 {{时长}}",
      "inputs": {},
      "parameters": {},
      "routing_hints": {"primary": "kimi-k2", "fallback": ["deepseek-v4-pro"]},
      "mcp_tools": [],
      "hitl_gate": {"type": "version_select", "timeout_seconds": 600},
      "budget_tokens": 4000,
      "expected_artifact": "短视频脚本"
    }
  ],
  "failure_handling": {}
}"""


def render_planner_user_prompt(
    *,
    user_request: str,
    available_skills_summary: str,
    similar_episodes: str,
    available_mcp_tools_summary: str,
    collected_fields: dict | None = None,
    available_md_skills_summary: str = "",
) -> str:
    """渲染 Planner 的 user message。

    用 .format() 而不是 Jinja2 — 避免 prompt_template 内的 `{{ }}` 被错解析。

    新增(ADR-022):`available_md_skills_summary` — MD Skill 知识包列表。
    与 `available_skills_summary`(YAML Playbook)语义不同:
        - MD Skills:**知识**,Planner 应在 step.prompt_template 里"按 X 的规范"引用
        - Playbooks:**已有可执行工作流**,Planner 不直接调用,但可借鉴拆步思路
    """
    cf = collected_fields or {}
    cf_block = (
        "用户已提供字段:\n```json\n"
        + _json_dumps(cf)
        + "\n```\n"
        if cf
        else "用户未提供结构化字段。"
    )
    md_block = (
        "# 可用 MD Skill 知识包(进 step.prompt_template 引用,例如『按 X 规范……』)\n"
        f"{available_md_skills_summary}"
        if available_md_skills_summary.strip()
        else "# 可用 MD Skill 知识包(无)"
    )
    playbooks_block = (
        f"# 已有 YAML Playbook(参考拆步思路,不要直接调用 — 你只能用 4 个 worker)\n{available_skills_summary}"
        if available_skills_summary.strip()
        else "# 已有 YAML Playbook(无)"
    )
    episodes_block = (
        f"# 历史相似任务(可借鉴 plan 思路)\n{similar_episodes}"
        if similar_episodes.strip()
        else "# 历史相似任务(无)"
    )
    return (
        "# 用户请求\n"
        f"{user_request}\n\n"
        f"{cf_block}\n\n"
        f"{md_block}\n\n"
        f"{playbooks_block}\n\n"
        f"{episodes_block}\n\n"
        "# 当前可用 MCP 工具\n"
        f"{available_mcp_tools_summary}\n\n"
        "# 输出格式示例(只看结构,不要照抄内容)\n"
        f"```json\n{EXAMPLE_PLAN_JSON}\n```\n\n"
        "现在请输出 Plan JSON,不要任何额外解释、不要 markdown 包裹。"
    )


def render_replanner_user_prompt(
    *,
    original_plan_json: str,
    failed_step_id: str,
    failure_detail: str,
    completed_step_refs: str,
) -> str:
    return (
        "# 原 Plan\n"
        f"```json\n{original_plan_json}\n```\n\n"
        f"# 失败的 step\n`{failed_step_id}`\n\n"
        "# 失败详情\n"
        f"{failure_detail}\n\n"
        "# 已完成 step 的产物引用(可复用,保留 step_id 即跳过)\n"
        f"{completed_step_refs}\n\n"
        "请输出新 Plan JSON,字段同 schema,source 填 `replanner`。"
    )


def _json_dumps(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)
