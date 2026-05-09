# LLM API 测试记录

日期: 2026-05-06

本文记录本轮对「有了」Agent LLM 路由、真实 API 连通性、handler 任务完成度的测试过程、结果与遗留问题。本文不记录任何真实 API Key。

## 测试目标

1. 验证当前各 Agent 已注册 task handler 在 mock 外部 IO 的情况下都能完成。
2. 验证会调用 LLM 的任务能通过真实 API 返回结果。
3. 验证模型别名到真实 provider model id 的映射可用。
4. 验证 `veo-3`、`seedance-2`、`kling-2` 已改为走 OpenRouter。

## 涉及代码

- `youle/agents/_common/llm.py`
- `youle/backend/app/router.py`
- `youle/agents/av_agent/handlers/audio_to_text.py`
- `youle/agents/av_agent/handlers/tts_generate.py`
- `test/test_agent_task_handlers.py`
- `test/test_agent_task_handlers_live_api.py`

## 当前 Provider 路由规则

`_resolve_model()` 先把业务友好模型名映射成真实 provider model id。

`_provider_for_model()` 再按模型名前缀选择 provider:

| 模型前缀 / 关键词 | Provider |
| --- | --- |
| `gpt*`, `openai/*` | OpenRouter |
| `claude*`, `anthropic/*` | OpenRouter |
| `google/*` | OpenRouter |
| `bytedance-seed/*` | OpenRouter |
| `openrouter/*` | OpenRouter |
| `deepseek*` | DeepSeek |
| 其他 | SiliconFlow |

## 关键 Alias 映射

| 业务名 | 实际模型 ID | Provider |
| --- | --- | --- |
| `gpt-image-2` | `openai/gpt-5.4-image-2` | OpenRouter |
| `gpt-5-vision` | `openai/gpt-5-mini` | OpenRouter |
| `claude-sonnet-vision` | `anthropic/claude-sonnet-4.6` | OpenRouter |
| `kimi-k2` | `Pro/moonshotai/Kimi-K2.6` | SiliconFlow |
| `qwen3.6-plus` | `Qwen/Qwen3.6-Plus` | SiliconFlow |
| `volcengine-tts` | `Qwen/Qwen3-Omni-30B-A3B-Instruct` | SiliconFlow |
| `whisper-v3` | `Qwen/Qwen3-Omni-30B-A3B-Instruct` | SiliconFlow |
| `veo-3` | `google/gemini-2.5-flash` | OpenRouter |
| `seedance-2` | `bytedance-seed/seed-2.0-lite` | OpenRouter |
| `kling-2` | `openrouter/auto` | OpenRouter |

## 执行过的测试

### 1. Mock handler 全量 smoke test

命令:

```bash
env DEBUG=true youle/backend/.venv/bin/pytest test/test_agent_task_handlers.py -q
```

结果:

```text
30 passed
```

说明:

- 覆盖当前各 Agent 注册的 30 种 task handler。
- `OSS`、`MCP`、`DB`、`Celery` 均使用 monkeypatch mock。
- `LITELLM_MOCK=true`，不访问真实 LLM。

### 2. Backend smoke + mock handler 回归

命令:

```bash
env DEBUG=true youle/backend/.venv/bin/pytest \
  test/test_agent_task_handlers.py \
  youle/backend/tests/smoke/test_infra.py \
  -q
```

结果:

```text
34 passed
```

说明:

- 初次执行时遇到当前 shell 环境变量 `DEBUG=release`，Pydantic bool 解析失败。
- 使用 `env DEBUG=true` 后通过。

### 3. 真实 LLM API 全量 handler 测试

命令:

```bash
youle/backend/.venv/bin/pytest test/test_agent_task_handlers_live_api.py -q
```

结果:

```text
30 passed in 750.63s (0:12:30)
```

说明:

- LLM 调用走真实 API。
- `OSS`、`MCP`、`DB`、`Celery` 仍 mock。
- 这样可以隔离验证 LLM 真实连通性，不受本地工具服务是否启动影响。

### 4. 视频模型 Alias 真实 API 连通测试

测试代码直接调用 `agents._common.llm.complete()`，通过 `routing_hints.primary` 分别指定 3 个 alias:

```python
("veo-3", "text_to_video")
("seedance-2", "text_to_video")
("kling-2", "image_to_video")
```

结果:

```text
veo-3     => google/gemini-2.5-flash | video routing live api ok
seedance-2 => bytedance-seed/seed-2.0-lite-20260309 | video routing live api ok
kling-2   => openrouter/auto -> mistralai/mistral-7b-instruct-v0.1
```

说明:

- 这组测试验证的是 LLM 路由层和 OpenRouter 真实 API 连通。
- 当前 `text_to_video` / `image_to_video` handler 仍是 V1.5 stub，不会真实生成视频。

## 测试过程中发现并修复的问题

### 1. Agent 2 没有 LLM 路由

现状:

- Agent 2 当前主要走 `document_tools` / `image_tools` MCP。
- `pptx_assemble`、`xlsx_assemble`、`docx_assemble`、`pdf_extract`、`pdf_ocr` 不调用 `llm.complete()`。

结论:

- 当前没有专门的 Agent 2 LLM 默认模型。
- 如后续要做文档总结、PPT 内容生成，需要新增对应 `task_type` 和 handler。

### 2. `image_quality_check` 初次真实 API 失败

失败现象:

```text
400 Bad Request
model=gpt-5-vision
url=https://openrouter.ai/api/v1/chat/completions
```

原因:

- `gpt-5-vision` 是业务友好名，不是 OpenRouter 真实模型 ID。

修复:

```python
"gpt-5-vision": "openai/gpt-5-mini"
```

结果:

- 后续 live API 测试通过。

### 3. `image_describe` 初次真实 API 失败

失败现象:

```text
400 Bad Request
model=deepseek-v4-flash
task_type=image_describe
```

原因:

- Agent 侧 `AGENT_ROUTING` 漏了 `image_describe`。
- 缺省回落到 `deepseek-v4-flash`，但 handler 发的是多模态 message，DeepSeek chat endpoint 不支持该格式。

修复:

```python
"image_describe": {"primary": ["claude-sonnet-vision"], "fallback": ["gpt-5-vision"]}
```

结果:

- `image_describe` live API 测试通过。

### 4. `audio_to_text` 初次真实 API 失败

失败现象:

```text
400 Bad Request
model=TeleAI/TeleSpeechASR
url=https://api.siliconflow.cn/v1/chat/completions
```

原因:

- `TeleAI/TeleSpeechASR` 不是当前 chat-completions wrapper 可直接调用的形态。
- 当前 `audio_to_text_handler` 仍是 chat-completions 兼容实现，不是真正 ASR endpoint。

临时修复:

```python
"whisper-v3": "Qwen/Qwen3-Omni-30B-A3B-Instruct"
"aliyun-asr": "Qwen/Qwen3-Omni-30B-A3B-Instruct"
```

结果:

- 当前 handler live API 测试通过。

限制:

- 这不是严格意义上的真实 ASR。
- 后续应接音频专用 endpoint 或 MCP audio tools。

### 5. `audio_to_text_handler` 返回字段错误

问题:

```python
ArtifactRef(..., metadata={...})
```

但协议字段实际为:

```python
extra_metadata
```

修复:

```python
ArtifactRef(..., extra_metadata={...})
```

结果:

- handler smoke test 通过。

### 6. `tts_generate` 当前有兜底静音音频

`origin/dev` 中已把 TTS handler 改为优先调用:

```python
llm.audio_speech(...)
```

如果 `/audio/speech` 失败，则返回静音 mp3 占位，不阻塞视频合成 pipeline。

现状:

- `volcengine-tts` / `aliyun-tts` alias 当前仍映射到 `Qwen/Qwen3-Omni-30B-A3B-Instruct`。
- 这主要保证当前 chat / audio wrapper 的测试连通和兜底流程。

限制:

- 真 TTS 音色质量仍需接真实 TTS endpoint 后单测。

### 7. `veo-3` 初次映射到 `google/gemini-2.5-pro` 时 content 为 null

现象:

- OpenRouter 请求成功。
- 返回 `reasoning`，但 `message.content` 为 `null`。
- 当前 `LLMResponse.content` 假定 content 一定是字符串，容易失败。

修复:

```python
"veo-3": "google/gemini-2.5-flash"
```

结果:

- `veo-3` 真实 API 连通测试返回正常 content。

### 8. `seedance-2` / `kling-2` 改为走 OpenRouter

旧映射:

```python
"seedance-2": "Wan-AI/Wan2.2-T2V-A14B"
"kling-2": "Wan-AI/Wan2.2-I2V-A14B"
```

新映射:

```python
"seedance-2": "bytedance-seed/seed-2.0-lite"
"kling-2": "openrouter/auto"
```

结果:

- 二者都通过 OpenRouter 真实 API 连通测试。

限制:

- OpenRouter `/models` 当前没有直接的 `kling` 生成视频模型 ID。
- `kling-2` 目前用 `openrouter/auto` 兜底，实际返回模型可能变化。

## 当前已知限制

1. `fallback` 列表目前主要是配置，客户端没有自动失败后逐个 fallback 重试。
2. `text_to_video` / `image_to_video` 目前是 V1.5 stub，不会真实生成视频。
3. TTS / ASR 仍未完成真实音频 endpoint 的端到端质量验证。
4. OpenRouter 没有直接暴露 `veo` / `kling` / 传统视频生成模型 ID，本轮只验证 OpenRouter chat-completions 层连通。
5. `LLMResponse.content` 对 `content=null` 的兼容性不足，遇到 reasoning-only 响应会报错或返回空。

## 后续建议

1. 为 `complete()` 增加自动 fallback 重试。
2. 把 `MODEL_ALIASES` 抽成配置文件或数据库配置，减少代码发版频率。
3. 为 `LLMResponse.content` 增加 `reasoning` / 多 part content 的容错。
4. 给 Agent 2 新增真正 LLM 型文档任务，例如 `doc_summary`、`slide_outline`。
5. 为 TTS / ASR 接入专用 endpoint，并单独做音频文件级别测试。
6. 视频生成正式实现时，不应继续走 V1.5 stub，应接入视频任务 API 或 MCP video tools。
