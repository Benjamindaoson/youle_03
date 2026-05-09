# 四分身任务路径速查（主编排派 Redis → Consumer）

- **显式 handler**：`main.py` 的 `handlers` 字典命中 → 直接调用该 coroutine（确定性管道）。
- **未注册 task_type**：若配置了 `persona`，则走 **ReAct**（`react_runner.run_react_agent_task`）：LLM + MCP 工具多步，直到 `agent_finish`。
- **主编排**：不在此表；实现在 `agents.orchestrator_agent`。

| agent_id | 进程包 | Handler 覆盖（摘录） | ReAct 兜底 |
|----------|--------|----------------------|------------|
| agent_1 | text_agent | web_search, long/short_writing, version_compare, structured_writing, summarization, analysis, translation, polish, xhs_* | 未声明的 task_type |
| agent_2 | document_agent | 见对应 main handlers | 有 persona 时 |
| agent_3 | image_agent | image_download, batch_generate, compose, quality, style_extract, extras(生成/修图等) | 有 persona 时 |
| agent_4 | av_agent | audio_to_text, tts, bgm_select, video_compose, v15_real 等 | 有 persona 时；video_compose 在部分环境直调 handler |

优化方向：高价值/高不确定 task 应在 Skill 中声明 `mcp_tools` 并在 ReAct 中露出工具；纯脚本型保持 handler。
