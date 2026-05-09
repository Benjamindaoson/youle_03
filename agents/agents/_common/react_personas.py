"""四名 Worker 的 ReAct persona — system 提示中与成本纪律、默认可调用 MCP URI。"""

from __future__ import annotations

from dataclasses import dataclass

from agents._common.protocol import AgentId


@dataclass(frozen=True)
class ReactPersona:
    agent_id: AgentId
    title: str
    default_mcp_uris: tuple[str, ...]
    frugality_rules: str


def get_persona(agent_id: AgentId) -> ReactPersona:
    """默认可用 MCP 列表为空:由 Skill `mcp_tools` 显式授权,避免无关步骤乱搜乱调。

    未配置 `mcp_tools` 的步骤仅走 LLM + `agent_finish`(最低工具成本)。
    """
    if agent_id == "agent_1":
        return ReactPersona(
            agent_id=agent_id,
            title="文字与调研专员",
            default_mcp_uris=(),
            frugality_rules=(
                "优先低成本:能 web_search/web_fetch 一次搞定就不要做多轮泛泛推理。"
                "若 routing_hints.primary 偏向贵模型，只在整理与写作阶段使用。"
                "不要重复检索相同关键词。"
            ),
        )
    if agent_id == "agent_2":
        return ReactPersona(
            agent_id=agent_id,
            title="Office / 文档处理专员",
            default_mcp_uris=(),
            frugality_rules=(
                "文档类任务应先读清 inputs 引用再选最小工具链路;能做 pdf_extract 就不做 pdf_ocr。"
                "单次调用尽量带好 arguments,避免试错链式调用。"
            ),
        )
    if agent_id == "agent_3":
        return ReactPersona(
            agent_id=agent_id,
            title="视觉与设计专员",
            default_mcp_uris=(),
            frugality_rules=(
                "先 download_batch / quality_check,再决定是否 enhance 或 concat_long。"
                "禁止无必要的高分辨率链路;够用即可。"
            ),
        )
    return ReactPersona(
        agent_id=agent_id,
        title="影音合成与素材专员",
        default_mcp_uris=(),
        frugality_rules=(
            "能用本地 MCP compose 就不必走外采视频生成模型。"
            "TTS/BGM 只生成一次音频轨;超长文本先 summarize 再 tts。"
        ),
    )
