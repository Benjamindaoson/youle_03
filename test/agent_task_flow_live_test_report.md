# Agent Task Flow Live Test Report

测试日期: 2026-05-07
测试范围: Agent 1/2/3/4 当前入口注册的全部 task_type
测试链路: LangGraph -> backend dispatcher -> Redis Streams -> AgentConsumer -> handler -> Redis result stream -> LangGraph state

## 测试脚本

- `test/test_all_agent_task_flows_langgraph_redis_live.py`
- `test/test_agent1_short_writing_langgraph_redis_live.py`
- `test/test_agent1_short_writing_live.py`

## 执行命令

```bash
haole/backend/.venv/bin/pytest test/test_all_agent_task_flows_langgraph_redis_live.py -q -s
```

首次全量结果:

```text
39 passed, 1 failed in 494.77s
```

唯一失败:

- `agent_3-batch_generate`
- 原因: LangGraph step timeout 为 240s；真实 `openai/gpt-5.4-image-2` 图像生成第一张约 220s，第二张刚开始时 LangGraph 已超时。

调高 `batch_generate` live test timeout 到 600s 后单独复测:

```bash
haole/backend/.venv/bin/pytest 'test/test_all_agent_task_flows_langgraph_redis_live.py::test_all_agent_task_flows_via_langgraph_redis_live[agent_3-batch_generate]' -q -s
```

结果:

```text
1 passed in 403.09s
```

最终结论: 40 条任务流均能通过 LangGraph/Redis/AgentConsumer 链路；`batch_generate` 需要显著更长 timeout。

## 覆盖任务

Agent 1:

- `web_search`
- `long_writing`
- `short_video_script`
- `short_writing`
- `version_compare`
- `structured_writing`
- `summarization`
- `analysis`
- `translation`
- `polish`

Agent 2:

- `image_concat_long`
- `pptx_assemble`
- `xlsx_assemble`
- `docx_assemble`
- `pdf_extract`
- `pdf_ocr`

Agent 3:

- `image_download`
- `batch_generate`
- `image_quality_check`
- `style_extract`
- `image_generate`
- `image_edit`
- `image_describe`
- `background_remove`
- `bg_remove`
- `enhance`

Agent 4:

- `audio_to_text`
- `bgm_select`
- `tts_generate`
- `video_compose`
- `text_to_video`
- `image_to_video`
- `video_describe`
- `video_extract_frames`
- `audio_extract`
- `video_cut`
- `subtitle_generate`
- `subtitle_add`
- `bgm_add`
- `transition_apply`

## 关键观察

1. Redis/LangGraph 主链路可用。
  每个普通任务都能完成 `dispatcher.dispatched -> agent.consumer.completed -> LangGraph planner/finalize`。
2. 真实 LLM 路由可用。
  文本任务主要走 DeepSeek；图像理解走 OpenRouter Claude/GPT；音频转文本走 SiliconFlow Omni 路由。
3. `batch_generate` 当前真实耗时过长。
  单独复测耗时约 402.5s。`ecommerce_detail_image.yaml` 里 `segment_images` 的 `timeout: 90` 对真实图像生成不够。
4. `tts_generate` 路由可达但 TTS endpoint 返回 403。
  handler 捕获异常并使用 silent mp3 fallback，所以任务流完成，但不是真实 TTS 音频。
5. `video_compose` 是 `pending_external` 长任务。
  本测试验证到 Redis dispatch、AgentConsumer、Celery dispatch stub、`pending_external` 回执。没有等待真实 Celery 视频渲染完成。
6. Agent 4 V1.5 视频/字幕/剪辑类任务仍是 stub。
  这些 task_type 链路能走通，但按设计返回 `failed`，`error_detail.reason=v1_5_not_supported`。

## 测试夹具说明

为了聚焦主链路，以下外部依赖在测试中 mock:

- OSS 写入: 返回 `oss://live-test/...`
- MCP tools: `search` / `image_tools` / `document_tools`
- BGM 数据库查询: 返回 placeholder BGM
- Celery `video_compose_workflow.delay`: 返回 fake workflow id

没有 mock 的部分:

- 后端 dispatcher
- Redis Streams
- AgentConsumer
- LangGraph 编译和执行
- LLM HTTP 调用
