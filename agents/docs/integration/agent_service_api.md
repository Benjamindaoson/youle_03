# 智能体服务接口文档(后端对接)

## 元信息

| 项 | 内容 |
|---|---|
| 文档版本 | v2.0 |
| 生成时间 | 2026-05-09 |
| 维护人 | Benjamin |
| 部署架构 | K8s 同 namespace,Redis broker 共享,所有跨进程通信走 Redis Streams + HTTP(MCP)|
| 鉴权 | K8s NetworkPolicy + 同 namespace 隔离 |

## 总览

| 类别 | 数量 | 协议 |
|---|---|---|
| 入站接口(后端 → 智能体) | 13 | Redis Streams 4 + HTTP 9 |
| 出站契约(智能体 → 后端) | 5 | Redis Streams |
| 后端接入套件 | 8 | result_waiter / migration / K8s YAML / env vars / quick start |

```
                        ┌──────────────┐
                        │   Frontend   │
                        └──────┬───────┘
                               │ WebSocket
                        ┌──────▼───────┐
                        │   Backend    │←─── Redis Streams ───┐
                        │  (FastAPI)   │  agent_results:*      │
                        └──────┬───────┘  flywheel:signals     │
                               │          agent_dlq:*          │
                               │ XADD     agent_heartbeats     │
                               │ agent_tasks:{text|...}        │
                               │                                │
        ┌──────────────────────┴────────────────────┐          │
        │                                            │          │
        ▼                                            ▼          │
┌───────────────┐                          ┌───────────────┐   │
│ Worker × 4    │ ──── HTTP /tools/* ────► │ MCP × 9       │   │
│ text/doc/img/av│                          │ search/oss/...│   │
└───────┬───────┘                          └───────────────┘   │
        │                                                       │
        └──── Redis Streams (results / flywheel / dlq) ─────────┘
```

---

## Part 1: 入站接口(后端 → 智能体)

### 1.1 Worker Task Streams

> 后端通过 `XADD agent_tasks:<channel> data='<AgentTask JSON>'` 派活;每个 worker 进程独立消费一个 stream。Worker 完成后通过 `agent_results:{task_id}` Stream 返回结果(见 Part 2)。

#### 公共契约

**Consumer group**:`<agent_id>-group`(由 worker 端 `xgroup_create(id="$", mkstream=True)` 自动建,后端不需创建)

**Stream entry 格式**:

```
field: data
value: <AgentTask JSON>
```

**`AgentTask` JSON Schema**:

```json
{
  "task_id": "<UUID>",
  "step_id": "<string>",
  "agent_id": "agent_1 | agent_2 | agent_3 | agent_4",
  "task_type": "<string,见各 agent 白名单>",
  "user_id": "<UUID>",
  "conversation_id": "<UUID>",
  "inputs": {},
  "parameters": {},
  "routing_hints": {},
  "skill_id": "<string|null>",
  "skill_version": "<string|null>",
  "timeout_seconds": 60,
  "mcp_tools": ["mcp://search/web_search"],
  "orchestration_run_id": "<UUID|null>",
  "trace_id": "<32-hex|null>",
  "idempotency_key": "<string|null>",
  "dispatch_attempt": 0
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| task_id | UUID | ✅ | 任务唯一 ID;worker 写回执时用同一 ID |
| step_id | string | ✅ | Skill workflow 中的 step 标识 |
| agent_id | enum | ✅ | 必须与 stream 频道对应(boundary 校验)|
| task_type | string | ✅ | 见各 agent 支持白名单(下);不在白名单直接 DLQ |
| user_id | UUID | ✅ | 用户 ID(飞轮 / 配额 / 偏好)|
| conversation_id | UUID | ✅ | 会话 ID |
| inputs | dict | - | 约定字段:`_prompt`(渲染后 prompt)、`_upstream`(上游 step 产物 ref)|
| parameters | dict | - | step 参数(可含 `_planner.persona/budget_tokens` 等)|
| routing_hints | dict | - | 模型路由,如 `{"primary": "kimi-k2", "fallback": [...]}`|
| skill_id | string | - | 关联 Skill ID;动态 plan 路径为 `dynamic-<plan_id>` |
| skill_version | string | - | Skill 版本号 |
| timeout_seconds | int | - | 默认 60,worker 强制下限 10 |
| mcp_tools | list[str] | - | MCP 工具白名单 URI |
| orchestration_run_id | UUID | - | 编排运行 ID(同任务多 step 共享)|
| trace_id | 32-hex | - | W3C-compatible trace,日志透传 |
| idempotency_key | string | - | 派发幂等 key(worker 端按需 dedup)|
| dispatch_attempt | int | - | 编排端重试计数 |

#### IN-001 · `agent_tasks:text`(Agent 1 — 文字 / 调研)

**支持的 task_type**:

```
short_writing  long_writing  structured_writing
summarization  extraction  analysis
web_search  web_scrape  data_organize
translation  polish  version_compare
short_video_script  short_video_hook
xhs_carousel_plan  xhs_carousel_copy  xhs_delivery_summary
```

#### IN-002 · `agent_tasks:document`(Agent 2 — 文档专员)

```
pptx_assemble  pptx_modify  pptx_extract
xlsx_assemble  xlsx_read  xlsx_chart  xlsx_format
docx_assemble  docx_modify  docx_extract
pdf_extract  pdf_create  pdf_watermark  pdf_ocr
image_concat_long
```

#### IN-003 · `agent_tasks:image`(Agent 3 — 设计师)

```
image_generate  image_edit  image_compose
batch_generate
image_describe  image_classify  image_quality_check
image_ocr  image_inpaint  image_outpaint
image_enhance  enhance
background_remove  bg_remove
image_download  style_extract  style_transfer
xhs_cover_image  xhs_slide_text_image  xhs_product_image
xhs_ambience_image  xhs_series_image  xhs_local_edit_image
```

#### IN-004 · `agent_tasks:av`(Agent 4 — 影音师)

```
text_to_video  image_to_video  video_compose
video_describe  video_extract_frames  video_cut
audio_extract
subtitle_generate  subtitle_add
bgm_add  bgm_select
transition_apply
tts_generate  audio_to_text
```

`video_compose` 走 Celery 异步:worker 立即返 `status="pending_external" + external_workflow_id`,Celery 完成后再次 `XADD agent_results:{task_id}`。

#### Worker 错误处理

| 错误源 | 类型 | 行为 |
|---|---|---|
| JSON / Pydantic / boundary 校验失败 | 永久错 | 直接 DLQ,**不重试**(`type=permanent_error`)+ 同时往 `agent_results:{task_id}` 写 status=failed |
| handler 超时(`timeout_seconds`)| 运行时错 | 重试 ≤ `AGENT_MAX_RETRIES`(默认 2),耗尽后 DLQ |
| handler 抛异常 | 运行时错 | 同上 |

后端可视 `agent_results:{task_id}` 中第一条非 `pending_external` 状态为终态。

---

### 1.2 MCP HTTP Servers

> 9 个独立 FastAPI 进程,每个暴露三个端点:
>
> ```
> GET  /health                 → {"status": "ok", "server": "<name>"}
> GET  /tools                  → [{"name": "<tool_name>"}, ...]
> POST /tools/<tool_name>      → tool 输出 dict,Body: {"arguments": {...}}
> ```
>
> 主要消费方是 worker 进程([_common/mcp_client.py](../../agents/_common/mcp_client.py));后端可直接调用做 healthcheck 或运维操作。

| ID | Server | 默认端口 | Env 覆盖 | Tools |
|---|---|---|---|---|
| IN-005 | mcp-search | 7001 | `MCP_SEARCH_URL` | `web_search`, `web_fetch` |
| IN-006 | mcp-image-tools | 7002 | `MCP_IMAGE_TOOLS_URL` | `concat_long`, `download_batch`, `bg_remove`, `enhance`, `quality_check` |
| IN-007 | mcp-video-tools | 7003 | `MCP_VIDEO_TOOLS_URL` | `compose`, `extract_frames`, `subtitle_align` |
| IN-008 | mcp-audio-tools | 7004 | `MCP_AUDIO_TOOLS_URL` | `tts`, `asr`, `subtitle_generate`, `bgm_match` |
| IN-009 | mcp-document-tools | 7005 | `MCP_DOCUMENT_TOOLS_URL` | `pptx_assemble`, `xlsx_assemble`, `docx_assemble`, `pdf_extract`, `pdf_ocr` |
| IN-010 | mcp-oss | 7006 | `MCP_OSS_URL` | `upload_bytes`, `download_bytes`, `sign_url` |
| IN-011 | mcp-platform-publish | 7007 | `MCP_PLATFORM_PUBLISH_URL` | `douyin_publish`, `xhs_publish`, `wechat_publish`, `check_publish_status` |
| IN-012 | mcp-browser-use | 7008 | `PORT` | `navigate`, `click`, `fill`, `extract_text`, `extract_links`, `screenshot`, `wait_for`, `close` |
| IN-013 | mcp-code-executor | 7009 | `PORT` | `python_exec`, `shell_exec`, `write_file`, `read_file`, `list_dir`, `install_package`, `close_session`（均需 `task_id`） |

#### 关键 Tool 参数清单

**mcp-search**

```
POST /tools/web_search
{"arguments": {"query": "...", "max_results": 5, "source_profile?": "...", "include_domains?": [], "exclude_domains?": []}}

POST /tools/web_fetch
{"arguments": {"url": "...", "render_js?": false}}
```

**mcp-image-tools**

```
POST /tools/concat_long
{"arguments": {"images": ["oss://..."], "direction?": "vertical|horizontal"}}

POST /tools/download_batch
{"arguments": {"urls": [...], "check_quality?": false, "min_resolution?": "720p|1080p"}}

POST /tools/quality_check
{"arguments": {"ref|oss_ref|url": "...", "min_width?": 720}}
```

**mcp-video-tools**

```
POST /tools/compose
{"arguments": {
  "voice_ref": "oss://...",
  "bgm_ref": "oss://...",
  "image_refs": ["oss://..."],
  "duration": 60,
  "subtitle?": "...",
  "resolution?": [1080, 1920],
  "bgm_volume?": 0.2,
  "voice_volume?": 1.0
}}
```

**mcp-audio-tools**

```
POST /tools/tts
{"arguments": {"text": "...", "voice?": "female_warm"}}

POST /tools/asr
{"arguments": {"audio_url|ref|oss_ref": "...", "language?": "zh"}}
```

**mcp-document-tools**

```
POST /tools/pptx_assemble
{"arguments": {"title": "...", "slides": [{...}]}}

POST /tools/pdf_extract
{"arguments": {"ref|oss_ref|url": "...", "max_pages?": 50}}
```

**mcp-oss**

```
POST /tools/upload_bytes
{"arguments": {"object_key": "...", "bucket?": "...", "content_type?": "...", "body": "<string>"}}

POST /tools/sign_url
{"arguments": {"oss_ref|object_key|key": "...", "expires_in?": 3600}}
```

**mcp-browser-use**

```
POST /tools/navigate
{"arguments": {"url": "...", "wait_until?": "load", "timeout_ms?": 15000}}

POST /tools/extract_text
{"arguments": {"selector?": "...", "max_chars?": 50000}}

POST /tools/screenshot
{"arguments": {"full_page?": false}}
→ {"format": "png", "size_bytes": <int>, "base64": "<string>"}
```

**mcp-code-executor**

```
POST /tools/python_exec
{"arguments": {"code": "...", "timeout_s?": 60, "max_stdout_bytes?": 4194304}}
→ {"stdout": "...", "stderr": "...", "returncode": 0, "duration_ms": 120, "ok": true}

POST /tools/write_file
{"arguments": {"path": "data.csv", "content": "...", "encoding?": "utf-8|base64"}}
```

---

## Part 2: 出站契约(智能体 → 后端)

> 全部走 Redis Streams,无同步 HTTP 反向调用。

### OUT-001 · `agent_results:{task_id}` — 任务回执(主流)

| 字段 | 值 |
|---|---|
| Stream key | `agent_results:{task_id}`(每任务独立)|
| 字段名 | `data` |
| 字段值 | `<AgentResult JSON>` |
| 触发时机 | worker handler 完成 / DLQ 兜底 / Celery 长任务完成 |
| 频次 | 每任务 ≥ 1 条;`pending_external` 时 2 条(中间 + 最终)|
| MAXLEN | `50, approximate=True`(智能体侧)|

**`AgentResult` JSON Schema**:

```json
{
  "task_id": "<UUID>",
  "step_id": "<string>",
  "status": "completed | failed | pending_external",
  "output": {
    "artifact_id": "<UUID>",
    "type": "<string>",
    "reference": "oss://bucket/path",
    "extra_metadata": {}
  },
  "extra_artifacts": [],
  "cost_usd": 0.0023,
  "duration_ms": 1234,
  "model_used": "deepseek-v4-flash",
  "error_detail": null,
  "external_workflow_id": null
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| status | enum | `completed` / `failed` / `pending_external` |
| output | ArtifactRef | 产物引用;`failed` / `pending_external` 可空 |
| extra_artifacts | list[ArtifactRef] | 多产物场景(如 batch_generate)|
| cost_usd | float | LLM/MCP 实际成本 |
| duration_ms | int | handler 执行时长 |
| model_used | string | 实际命中的模型名 |
| error_detail | dict | `failed` 时填,常见键:`reason`/`type`/`attempts`/`error` |
| external_workflow_id | string | `pending_external` 时填(异步外部工作流句柄)|

**消费规则**:

1. 收到 `pending_external` → **不要终止 await**,继续监听同一 stream
2. 收到 `completed` / `failed` → 终态,可终止 await + `DEL` stream
3. 终态字段 `error_detail.type`:
   - `permanent_error`:解析 / 边界错(JSON 损坏 / unknown task_type)
   - `max_retries_exceeded`:运行时错重试耗尽

### OUT-002 · `agent_results:stream:{task_id}` — LLM 流式 chunks

| 字段 | 值 |
|---|---|
| Stream key | `agent_results:stream:{task_id}` |
| 触发 | `long_writing` / `short_video_script` 等流式 task_type |
| 频次 | 每 LLM chunk 一条 entry |
| MAXLEN | `500, approximate=True` |

**Stream 字段(扁平,非 JSON)**:

```
step_id: <string>
seq:     <int as string>
chunk:   <string,LLM 增量内容>
done:    "0" | "1"
```

`done="1"` 是哨兵帧,表示流结束;最终 artifact 仍由 OUT-001 提供。

### OUT-003 · `agent_dlq:{agent_id}` — 死信

| 字段 | 值 |
|---|---|
| Stream key | `agent_dlq:agent_1` ... `agent_dlq:agent_4` |
| 触发 | 永久错或重试耗尽 |
| MAXLEN | `2000, approximate=True` |

**Stream 字段**:

```
msg_id:    <原 stream message id>
data:      <原 AgentTask JSON>
error:     <错误描述,≤500 字符>
attempts:  <尝试次数 as string>
type:      "permanent_error" | "max_retries_exceeded"
ts:        <ISO8601>
```

DLQ 是 forensic 数据,无需主流程消费;建议接告警(见 Part 5)。

### OUT-004 · `agent_heartbeats` — 心跳

| 字段 | 值 |
|---|---|
| Stream key | `agent_heartbeats` |
| 频次 | 每 worker 每 `AGENT_HEARTBEAT_INTERVAL` 秒(默认 20s)|
| MAXLEN | `1000, approximate=True` |

**Stream 字段**:

```
agent_id:  "agent_1" | "agent_2" | "agent_3" | "agent_4"
status:    "working" | "idle"
ts:        <ISO8601>
consumer:  <consumer name>
user_id:   <最近用户 ID;空字符串表示无>
```

### OUT-005 · `flywheel:signals` — 飞轮统一通道

| 字段 | 值 |
|---|---|
| Stream key | `flywheel:signals` |
| 字段 | `type` + `payload` (JSON) |
| 触发 | 见下表 |

**Signal types**:

| type | 触发时机 | payload 关键字段 |
|---|---|---|
| `trace` | 每任务 step 完成时(consumer 自动)| `task_id`, `step_id`, `agent_id`, `task_type`, `status`, `duration_ms`, `model_used`, `cost_usd`, `trace_id`, `orchestration_run_id`, `idempotency_key`, `dispatch_attempt` |
| `preference` | handler 内 style_extract 等显式 emit | `user_id`, `mood[]`, `prompt_inject`, `style_pref` |
| `reflexion` | 失败任务 / Critic 低分 step | `task_id`, `prompt_name`, `failure_reason`, `trace_excerpt`, `source` (`step_failed` \| `critic_low_score`), `metadata` |
| `skill_draft` | Skill induction(高频 dynamic plan 凝固为草稿)| `user_id`, `draft`, `source` |

**`reflexion` payload 详细 schema**:

```json
{
  "task_id": "<UUID>",
  "prompt_name": "short_video::step_script::long_writing",
  "failure_reason": "[critic_low_score] score=0.35 < threshold=0.70 ...",
  "trace_excerpt": "...",
  "source": "step_failed | critic_low_score",
  "metadata": {
    "step_id": "<string>",
    "task_type": "<string>",
    "skill_id": "<string|null>",
    "score": 0.35,
    "threshold": 0.7,
    "n_issues": 1
  }
}
```

后端的 `flywheel_consumer` 应当:
- `trace` → `flywheel:stats:{user_id}` Hash(任务统计)
- `preference` → `flywheel:prefs:{user_id}` Hash(7d TTL)
- `reflexion` → `flywheel:reflexion` Stream(maxlen=2000)→ Reflexion runner 异步消费
- `skill_draft` → `flywheel:skill_drafts` Stream(maxlen=500)→ 人工审核

---

## Part 3: 后端接入套件(Backend Integration Kit)

### 3.1 Result Waiter 完整参考实现

```python
# backend/app/services/agent_result_waiter.py
"""派发 task → 等回执 → 推进任务 / WS 转发 — 完整参考。"""
from __future__ import annotations
import asyncio
import json
from typing import AsyncIterator
from uuid import UUID

import redis.asyncio as aioredis
import structlog

from app.schemas.agent import AgentResult

log = structlog.get_logger(__name__)

REDIS_URL = "redis://redis:6379/0"
RESULT_BLOCK_MS = 5000           # XREADGROUP block timeout
RESULT_HARD_TIMEOUT_S = 1800     # 单任务最长等待(30 分钟)
RESULT_CONSUMER = "backend-result-waiter"


async def wait_for_task_result(
    *,
    task_id: UUID,
    expect_step_ids: set[str],
    redis: aioredis.Redis,
) -> AsyncIterator[AgentResult]:
    """监听 agent_results:{task_id} 直到所有 expected step 都到终态。

    每条非 pending_external 的 result yield 出去给上层(更新 DB / 推 WS)。
    收到 pending_external 时不视为终态 — 同 stream 后续会再来一条 completed/failed。
    """
    stream = f"agent_results:{task_id}"
    group = f"backend-result-waiter:{task_id}"

    # 容忍 BUSYGROUP(已存在)
    try:
        await redis.xgroup_create(stream, group, id="0", mkstream=True)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    pending: set[str] = set(expect_step_ids)
    deadline = asyncio.get_event_loop().time() + RESULT_HARD_TIMEOUT_S

    while pending:
        if asyncio.get_event_loop().time() > deadline:
            log.error("result_waiter.timeout", task_id=str(task_id), pending=list(pending))
            break
        try:
            resp = await redis.xreadgroup(
                group, RESULT_CONSUMER,
                streams={stream: ">"},
                count=8, block=RESULT_BLOCK_MS,
            )
        except Exception as e:
            log.warning("result_waiter.read_error", err=str(e))
            await asyncio.sleep(1)
            continue
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                payload = fields.get("data") or "{}"
                try:
                    result = AgentResult.model_validate(json.loads(payload))
                except Exception as e:
                    log.warning("result_waiter.parse_fail", err=str(e), msg_id=msg_id)
                    await redis.xack(stream, group, msg_id)
                    continue
                yield result
                if result.status != "pending_external":
                    pending.discard(result.step_id)
                await redis.xack(stream, group, msg_id)

    # 终态后清理 stream(智能体侧 MAXLEN=50 是兜底)
    try:
        await redis.delete(stream)
    except Exception as e:
        log.debug("result_waiter.cleanup_skip", err=str(e))


# 用法:
async def run_task(task_id: UUID, expect_steps: set[str]) -> None:
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    async for result in wait_for_task_result(
        task_id=task_id, expect_step_ids=expect_steps, redis=redis,
    ):
        # 更新 DB / 推 WS / 触发下一 step
        await update_task_step(result)
        if result.status in ("completed", "failed"):
            await ws_publish_step_event(task_id, result)
```

### 3.2 流式 chunks 消费器(WS 转发)

```python
# backend/app/services/agent_stream_forwarder.py
async def forward_stream_chunks_to_ws(*, task_id: UUID, user_id: str, redis):
    stream = f"agent_results:stream:{task_id}"
    last_id = "0"
    while True:
        resp = await redis.xread({stream: last_id}, count=20, block=2000)
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id
                await ws_manager.publish(user_id, {
                    "type": "step_streaming",     # WSEventType.STEP_STREAMING
                    "task_id": str(task_id),
                    "step_id": fields.get("step_id"),
                    "chunk": fields.get("chunk", ""),
                })
                if fields.get("done") == "1":
                    return  # 此 step 流结束;若多 step 流并存,需循环外层处理
```

### 3.3 `prompt_improvement_candidates` 表 alembic migration

```python
# backend/alembic/versions/<rev>_add_source_to_prompt_candidates.py
"""add source + extra_metadata to prompt_improvement_candidates

Revision ID: 4a2c1e6f8b3d
Revises: <previous>
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "4a2c1e6f8b3d"
down_revision = "<previous>"


def upgrade() -> None:
    op.add_column(
        "prompt_improvement_candidates",
        sa.Column("source", sa.String(32), nullable=True),
    )
    op.add_column(
        "prompt_improvement_candidates",
        sa.Column("extra_metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        "idx_pic_source",
        "prompt_improvement_candidates",
        ["source"],
    )


def downgrade() -> None:
    op.drop_index("idx_pic_source", table_name="prompt_improvement_candidates")
    op.drop_column("prompt_improvement_candidates", "extra_metadata")
    op.drop_column("prompt_improvement_candidates", "source")
```

`source` 取值:`step_failed`(任务级失败)/ `critic_low_score`(创作 step 评分低)。

### 3.4 Reflexion runner 透传 source

```python
# backend/app/services/reflexion_runner.py(增量改动)
class ReflexionState(TypedDict, total=False):
    task_id: str
    prompt_name: str
    trace_excerpt: str
    failure_reason: str
    source: str | None              # NEW
    extra_metadata: dict | None     # NEW
    # ... 其他字段不变


async def _persist(state: ReflexionState) -> dict[str, Any]:
    # ...
    cand = PromptImprovementCandidate(
        id=uuid4(),
        prompt_name=state.get("prompt_name") or "unknown",
        failure_task_id=UUID(state["task_id"]) if state.get("task_id") else None,
        root_cause=state.get("root_cause"),
        proposed_changes=state.get("proposed_changes"),
        source=state.get("source"),                     # NEW
        extra_metadata=state.get("extra_metadata") or {},  # NEW
        status="pending",
    )
    # ...


async def process_reflexion_event(payload: dict) -> dict:
    initial = ReflexionState(
        task_id=str(payload.get("task_id")),
        prompt_name=payload.get("prompt_name") or "unknown",
        trace_excerpt=payload.get("trace_excerpt") or "",
        failure_reason=payload.get("failure_reason") or "",
        source=payload.get("source"),                   # NEW
        extra_metadata=payload.get("metadata"),         # NEW
        messages=[],
    )
    # ...
```

### 3.5 K8s deployment YAML(参考)

#### Worker × 4

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: haole-agent-text
  namespace: haole
spec:
  replicas: 4
  selector:
    matchLabels: {app: haole-agent-text}
  template:
    metadata:
      labels: {app: haole-agent-text}
    spec:
      containers:
      - name: agent
        image: haole/agent:<tag>
        command: ["python", "-m", "agents.text_agent.main"]
        env:
        - {name: REDIS_URL,            value: "redis://redis.haole.svc:6379/0"}
        - {name: LITELLM_URL,          value: "http://litellm-proxy.haole.svc:4000"}
        - {name: LITELLM_API_KEY,      valueFrom: {secretKeyRef: {name: litellm-key, key: token}}}
        - {name: OSS_ENDPOINT,         value: "https://oss-cn-shanghai.aliyuncs.com"}
        - {name: OSS_ACCESS_KEY,       valueFrom: {secretKeyRef: {name: oss, key: ak}}}
        - {name: OSS_SECRET_KEY,       valueFrom: {secretKeyRef: {name: oss, key: sk}}}
        - {name: OSS_BUCKET,           value: "haole-prod"}
        - {name: AGENT_MAX_RETRIES,    value: "2"}
        - {name: AGENT_HEARTBEAT_INTERVAL, value: "20"}
        # MCP endpoints
        - {name: MCP_SEARCH_URL,        value: "http://mcp-search.haole.svc:7001"}
        - {name: MCP_IMAGE_TOOLS_URL,   value: "http://mcp-image-tools.haole.svc:7002"}
        - {name: MCP_VIDEO_TOOLS_URL,   value: "http://mcp-video-tools.haole.svc:7003"}
        - {name: MCP_AUDIO_TOOLS_URL,   value: "http://mcp-audio-tools.haole.svc:7004"}
        - {name: MCP_DOCUMENT_TOOLS_URL,value: "http://mcp-document-tools.haole.svc:7005"}
        - {name: MCP_OSS_URL,           value: "http://mcp-oss.haole.svc:7006"}
        resources:
          requests: {cpu: "1", memory: "2Gi"}
          limits:   {cpu: "2", memory: "4Gi"}
---
# 同样的 deployment 复制 3 份,把 command 改为
#   agents.document_agent.main / agents.image_agent.main / agents.av_agent.main
# image_agent 资源 4c/8G,av_agent 加 GPU
```

#### MCP servers(以 mcp-search 为例)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: mcp-search, namespace: haole}
spec:
  replicas: 2
  selector: {matchLabels: {app: mcp-search}}
  template:
    metadata: {labels: {app: mcp-search}}
    spec:
      containers:
      - name: mcp
        image: haole/mcp-search:<tag>
        command: ["python", "-m", "mcp_servers.search.server"]
        ports: [{containerPort: 7001}]
        env:
        - {name: TAVILY_API_KEY, valueFrom: {secretKeyRef: {name: tavily, key: token}}}
---
apiVersion: v1
kind: Service
metadata: {name: mcp-search, namespace: haole}
spec:
  selector: {app: mcp-search}
  ports: [{port: 7001, targetPort: 7001}]
```

> 各 MCP 副本数和资源:`oss/document_tools/audio_tools` 各 2 副本(0.5-2c / 1-4G);`image_tools/video_tools` 各 2 副本 + GPU;`browser_use / code_executor` **`replicas: 1`** 单副本(进程级单 session)。

#### NetworkPolicy(MCP 仅 worker 可达)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: mcp-internal-only, namespace: haole}
spec:
  podSelector:
    matchLabels: {role: mcp}
  policyTypes: [Ingress]
  ingress:
  - from:
    - podSelector:
        matchLabels: {role: agent-worker}
    - podSelector:
        matchLabels: {app: backend}
```

### 3.6 Env vars 完整清单

#### Worker(共用)

| 变量 | 默认 | 说明 |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379/0` | Redis broker |
| `LITELLM_URL` | `http://litellm-proxy:4000` | LiteLLM Proxy |
| `LITELLM_API_KEY` | - | LiteLLM token |
| `LITELLM_MOCK` | `true` | dev/CI 用 mock LLM,**production 必须 false** |
| `OSS_ENDPOINT` | `http://localhost:9000` | OSS / S3 endpoint |
| `OSS_ACCESS_KEY` / `OSS_SECRET_KEY` | - | OSS 凭证 |
| `OSS_BUCKET` | `haole-dev` | OSS bucket |
| `AGENT_MAX_RETRIES` | `2` | 单任务最多重试次数 |
| `AGENT_RETRY_BASE_SLEEP` | `1.0` | 重试退避基数(秒)|
| `AGENT_HEARTBEAT_INTERVAL` | `20` | 心跳间隔(秒)|
| `AGENT_REACT_MAX_STEPS` | `10` | ReAct loop 最大步数 |

#### MCP endpoints(worker 解析用)

```
MCP_SEARCH_URL          http://mcp-search:7001
MCP_IMAGE_TOOLS_URL     http://mcp-image-tools:7002
MCP_VIDEO_TOOLS_URL     http://mcp-video-tools:7003
MCP_AUDIO_TOOLS_URL     http://mcp-audio-tools:7004
MCP_DOCUMENT_TOOLS_URL  http://mcp-document-tools:7005
MCP_OSS_URL             http://mcp-oss:7006
MCP_PLATFORM_PUBLISH_URL http://mcp-platform-publish:7007
```

#### Sandbox / Code Executor

```
SANDBOX_PROVIDER         local | e2b           # production = e2b
APP_ENV                  production            # local provider 在 production 下拒绝运行
LOCAL_SANDBOX_ROOT       /tmp/haole-sandbox    # dev 用
E2B_API_KEY              <secret>              # production 必填
CODE_EXECUTOR_DEFAULT_TIMEOUT_S   60
CODE_EXECUTOR_ALLOW_PIP  false                 # 默认禁,白名单包除外
```

#### Browser Use

```
BROWSER_HEADLESS              true
BROWSER_DEFAULT_TIMEOUT_MS    15000
BROWSER_USER_AGENT            "Mozilla/5.0 (compatible; haoleAgent/1.0)"
```

#### Tavily / Search

```
TAVILY_API_KEY                <secret>
```

#### 增强能力(可选)

```
ENABLE_DYNAMIC_PLAN              false   # ADR-019 Planner 兜底
ENABLE_CRITIC_LOOP               false   # ADR-020 Critic 评审
ENABLE_STEP_PERSONA              true    # ADR-021 Step Persona
ENABLE_EPISODE_RETRIEVAL         false   # ADR-022 Qdrant 召回
ENABLE_CRITIQUE_SIGNAL_EMIT      true    # ADR-023 Critic→Reflexion 桥
COGNITIVE_PRIMARY_MODEL          claude-sonnet-4-6
COGNITIVE_FALLBACK_MODEL         gpt-5
QDRANT_URL                       http://qdrant:6333
QDRANT_API_KEY                   <secret>
QDRANT_WORKFLOW_TRACES_COLLECTION workflow_traces
EMBEDDING_MODEL                  bge-m3
SKILLS_DIR                       /app/skills
```

### 3.7 Quick Start: 派单到拿回执

```python
# 后端发起 web_search 任务的完整流程
import asyncio, json
from uuid import uuid4
import redis.asyncio as aioredis

async def main():
    r = await aioredis.from_url("redis://redis:6379/0", decode_responses=True)
    task_id = uuid4()
    payload = {
        "task_id": str(task_id),
        "step_id": "research",
        "agent_id": "agent_1",
        "task_type": "web_search",
        "user_id": "11111111-1111-1111-1111-111111111111",
        "conversation_id": "22222222-2222-2222-2222-222222222222",
        "inputs": {"_prompt": "搜索 2026 年城市漫游案例 5 条"},
        "parameters": {"source_profile": "short_video"},
        "mcp_tools": ["mcp://search/web_search"],
        "timeout_seconds": 120,
    }
    await r.xadd("agent_tasks:text", {"data": json.dumps(payload)})

    # 等回执
    stream = f"agent_results:{task_id}"
    group = f"demo-{task_id}"
    await r.xgroup_create(stream, group, id="0", mkstream=True)
    while True:
        resp = await r.xreadgroup(group, "demo", {stream: ">"}, count=1, block=10000)
        if not resp:
            continue
        for _, msgs in resp:
            for msg_id, fields in msgs:
                result = json.loads(fields["data"])
                print(result["status"], result.get("output"))
                await r.xack(stream, group, msg_id)
                if result["status"] in ("completed", "failed"):
                    await r.delete(stream)
                    return

asyncio.run(main())
```

### 3.8 Docker Compose(本地开发)

```yaml
# docker-compose.yml(片段)
services:
  redis:
    image: redis:7.2-alpine
    ports: ["6379:6379"]

  postgres:
    image: postgres:16
    environment: {POSTGRES_DB: haole, POSTGRES_PASSWORD: dev}

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    ports: ["9000:9000", "9001:9001"]

  agent-text:
    build: ./agents
    command: python -m agents.text_agent.main
    environment: &agent_env
      REDIS_URL: redis://redis:6379/0
      LITELLM_MOCK: "true"
      OSS_ENDPOINT: http://minio:9000
      OSS_ACCESS_KEY: minioadmin
      OSS_SECRET_KEY: minioadmin
      OSS_BUCKET: haole-dev
      MCP_SEARCH_URL: http://mcp-search:7001
      # ... 其他 MCP_*_URL
    depends_on: [redis, minio, mcp-search]

  agent-document: {<<: *agent_env, command: python -m agents.document_agent.main}
  agent-image:    {<<: *agent_env, command: python -m agents.image_agent.main}
  agent-av:       {<<: *agent_env, command: python -m agents.av_agent.main}

  mcp-search:
    build: ./agents
    command: python -m mcp_servers.search.server
    environment: {TAVILY_API_KEY: ""}
    ports: ["7001:7001"]

  # mcp-image-tools / mcp-video-tools / mcp-audio-tools / mcp-document-tools / mcp-oss
  # / mcp-platform-publish / mcp-browser-use / mcp-code-executor 同模板
```

---

## Part 4: 通信约定

### 鉴权

K8s NetworkPolicy + 同 namespace 隔离;Redis broker 共享;MCP HTTP 不暴露到集群外。

### 超时与重试

| 维度 | 默认值 | 配置 |
|---|---|---|
| Worker handler 总超时 | `task.timeout_seconds`(下限 10)| AgentTask 字段 |
| Worker 重试次数 | 2(共 3 次)| `AGENT_MAX_RETRIES` |
| Worker 重试退避 | `1s × 2^attempt` | `AGENT_RETRY_BASE_SLEEP` |
| Worker 心跳间隔 | 20s | `AGENT_HEARTBEAT_INTERVAL` |
| MCP HTTP client | 120s(connect 5s)| 写死 |
| LiteLLM client | 120s(connect 5s)| 写死 |
| Qdrant client | 5s(connect 2s)| `QDRANT_TIMEOUT_S` |

### Trace ID 透传

`AgentTask.trace_id`(32-hex)+ `orchestration_run_id`(UUID)+ `idempotency_key`(string)由后端派发时设置,worker 端透传到:
- 日志(structlog 自动注入)
- `agent_results:{task_id}` 回执(间接通过 status+log)
- `flywheel:signals` payload(`trace` type)

### 错误信号

| 通道 | 字段 | 含义 |
|---|---|---|
| `AgentResult.status="failed"` | `error_detail.reason` | handler 层错 |
| `AgentResult.status="failed"` | `error_detail.type="permanent_error"` | 解析 / 边界错 |
| `AgentResult.status="failed"` | `error_detail.type="max_retries_exceeded"` | 重试耗尽 |
| `agent_dlq:*` 同步入 | `type` | 与 error_detail.type 对齐 |

---

## Part 5: 监控建议

| 指标 | 阈值 | 数据源 |
|---|---|---|
| Worker 心跳缺失 | > 60s 告警 | `agent_heartbeats` 最新 ts |
| `agent_dlq:*` 增速 | > 10/min 告警 | `XLEN` 差分 |
| 单 task `agent_results:{task_id}` 长度 | > 30 异常 | `XLEN` |
| `flywheel:signals` consumer lag | > 10K 告警 | `XPENDING` |
| MCP `/health` 失败率 | > 1% 告警 | 周期 probe |
| LiteLLM 4xx/5xx | > 5% 告警 | LiteLLM dashboard |

---

## 附录:Schema 定义索引

| 文件 | Schema |
|---|---|
| [agents/_common/protocol.py](../../agents/_common/protocol.py) | `AgentTask`, `AgentResult`, `ArtifactRef`, `StepOutput` |
| [agents/_common/consumer.py](../../agents/_common/consumer.py) | Worker consumer 主循环 + retry/DLQ/heartbeat |
| [agents/_common/flywheel_emitter.py](../../agents/_common/flywheel_emitter.py) | `emit(signal_type, payload)` |
| [agents/_common/boundary.py](../../agents/_common/boundary.py) | `SUPPORTED_TASK_TYPES` 白名单 |
| [agents/_common/mcp_client.py](../../agents/_common/mcp_client.py) | `MCP_ENDPOINTS` 配置 + `call_tool` |
| [mcp_servers/_shared/http_app.py](../../mcp_servers/_shared/http_app.py) | `make_app(server_name, tools)` 公共脚手架 |
