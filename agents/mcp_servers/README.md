# MCP Servers(7 个,ADR-009)

铁律 13:工具集成唯一标准 — Agent handler 通过 mcp_client.call_tool 调用,禁止直接 import tavily / playwright 等。

| Server | 端口 | 实现 | 主要 tools |
|---|---|---|---|
| search | 7001 | Python | web_search / web_fetch |
| image_tools | 7002 | Python(GPU)| bg_remove / enhance / concat_long / quality_check / download_batch |
| video_tools | 7003 | Python(GPU)| compose / extract_frames / subtitle_align |
| audio_tools | 7004 | Python | tts / asr / bgm_match |
| document_tools | 7005 | Python | pptx / xlsx / docx / pdf / pdf_ocr |
| oss | 7006 | Python | upload / download / sign_url |
| platform_publish(V1.5)| 7007 | TypeScript | douyin / xhs / wechat |

每个 server:
- 暴露 HTTP 路由 `POST /tools/<tool_name>` 接受 `{"arguments": {...}}`
- 同时支持 stdio 模式(MCP 协议原生)
- Sprint 1 的 acceptance:`pytest tests/mcp/` 全绿(用 mock SDK 即可)

## 启动(dev)

```bash
cd mcp_servers/search && uv run python -m server      # 7001
cd mcp_servers/image_tools && uv run python -m server # 7002
...
```
