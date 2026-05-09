# ARCHITECTURE.md

> **位置**:目标仓库 `docs/ARCHITECTURE.md`
> **面向**:工程师在写代码前 / 写代码中查具体技术决策
> **关系**:CLAUDE.md(操作指令)→ ARCHITECTURE.md(技术细节)→ docs/3_决策记录(为什么这么决策)
>
> **版本**:v3.0(2026-05-05,对齐 ADR-001-rev / ADR-013 / ADR-014 / ADR-015 / ADR-016)
>
> **v3.0 关键变更**:
> - 🔄 Agent 编号反向(ADR-001-rev):**Agent 2=文档 / Agent 3=图 / Agent 4=影音**
> - ✨ 7 个 AI 角色(总裁助理 + 4 分任务 + HR + 财务经理)
> - ✨ 三模式同群切换(Plan / Ask / Auto)
> - ✨ Agent 拟人化(表情 + 状态 + 互动)
> - ✨ 左栏简化(知识库 / 成果库提顶)

---

## 1. 仓库结构骨架

```
youle/
├── CLAUDE.md                     # Claude Code 必读,操作指令
├── README.md                     # 团队 onboarding 入口
│
├── docs/
│   ├── ARCHITECTURE.md           # 本文件
│   ├── CONSTITUTION.md           # 16 原则 + ADR
│   └── (业务文档,可链接到原始 docs)
│
├── backend/                      # FastAPI 主服务(主编排 + 总裁助理)
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                  # REST 端点
│   │   │   ├── auth.py
│   │   │   ├── conversations.py
│   │   │   ├── tasks.py
│   │   │   ├── upload.py
│   │   │   ├── ws.py
│   │   │   ├── hitl.py           # HITL gate 接收 / 解析
│   │   │   └── flywheel.py       # 飞轮信号查询
│   │   ├── orchestrator/         # 主编排 8 子模块
│   │   │   ├── intent.py
│   │   │   ├── skill_match.py
│   │   │   ├── input_validator.py
│   │   │   ├── clarification.py
│   │   │   ├── task_compiler.py
│   │   │   ├── interrupt.py      # 含中断 C 回滚算法
│   │   │   ├── mode_manager.py
│   │   │   └── hitl_gate.py      # 子模块 8
│   │   ├── services/
│   │   │   ├── conversation.py
│   │   │   ├── context_pool.py
│   │   │   ├── brief_builder.py
│   │   │   ├── oss.py
│   │   │   ├── quota.py
│   │   │   ├── hitl.py
│   │   │   └── flywheel.py
│   │   ├── models/               # SQLAlchemy ORM
│   │   ├── schemas/              # Pydantic(OpenAPI 源)
│   │   ├── config/
│   │   │   ├── prompts.py        # 所有 system prompt 常量
│   │   │   ├── templates.py      # 用户面文案模板
│   │   │   └── settings.py
│   │   ├── router.py             # LiteLLM 客户端封装
│   │   ├── mcp_client.py         # MCP 客户端
│   │   ├── ws/                   # WebSocket 连接管理 + Redis Pub/Sub
│   │   └── celery_app.py
│   ├── alembic/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── prompts/              # prompt 回归集 yaml
│   │   ├── mcp/                  # MCP 集成测试
│   │   └── smoke/                # Sprint 0 健康检查
│   └── pyproject.toml
│
├── agents/                       # 4 个独立 Agent 微服务
│   ├── _common/
│   │   ├── consumer.py           # Redis Streams 消费循环
│   │   ├── protocol.py           # AgentTask / AgentResult
│   │   ├── boundary.py           # 边界检查
│   │   ├── cross_call.py         # NotImplementedError stub
│   │   ├── mcp_client.py
│   │   └── flywheel_emitter.py
│   ├── text/                     # Agent 1(文字)
│   │   ├── handlers/
│   │   │   ├── short_writing.py
│   │   │   ├── long_writing.py
│   │   │   ├── web_search.py
│   │   │   ├── version_compare.py
│   │   │   └── ...
│   │   └── main.py
│   ├── document/                 # Agent 2(文档,v3.0 ADR-001-rev)
│   │   ├── handlers/
│   │   │   ├── pptx_assemble.py
│   │   │   ├── image_concat_long.py
│   │   │   ├── pdf_extract.py
│   │   │   └── ...
│   │   └── main.py
│   ├── image/                    # Agent 3(图,v3.0)
│   │   ├── handlers/
│   │   │   ├── batch_generate.py
│   │   │   ├── image_generate.py
│   │   │   ├── image_download.py
│   │   │   ├── image_quality_check.py
│   │   │   └── ...
│   │   └── main.py
│   └── av/                       # Agent 4(影音,v3.0 ADR-005-rev)
│       ├── handlers/
│       │   ├── video_compose.py  # 提交 Celery
│       │   ├── tts_generate.py
│       │   ├── bgm_select.py
│       │   ├── subtitle_align.py
│       │   └── ...
│       ├── celery_tasks/
│       │   └── video_workflow.py
│       └── main.py
│
├── mcp_servers/                  # MCP servers 集合(ADR-009)
│   ├── search/                   # web_search / web_fetch
│   ├── image_tools/              # bg_remove / enhance / concat / quality
│   ├── video_tools/              # compose / extract / subtitle
│   ├── audio_tools/              # tts / asr / bgm
│   ├── document_tools/           # pptx / xlsx / docx / pdf
│   ├── oss/                      # upload / download / sign_url
│   └── platform_publish/         # V1.5
│
├── frontend/                     # Next.js 15
│   ├── app/                      # App Router
│   │   ├── layout.tsx            # 三栏布局
│   │   ├── (chat)/[conversationId]/page.tsx
│   │   ├── materials/
│   │   ├── academy/
│   │   ├── market/
│   │   ├── results/
│   │   └── settings/
│   ├── components/
│   │   ├── chat/
│   │   ├── execution/            # 右栏执行流
│   │   ├── hitl/                 # HITL 审核组件
│   │   │   ├── ScriptApproval.tsx
│   │   │   ├── ImageSelection.tsx
│   │   │   └── VideoFinalReview.tsx
│   │   ├── group/
│   │   └── ui/                   # shadcn/ui
│   ├── stores/                   # Zustand 切片
│   │   ├── conversation.ts
│   │   ├── task.ts
│   │   ├── ws.ts
│   │   ├── hitl.ts
│   │   └── user.ts
│   ├── lib/
│   │   ├── api.ts                # REST 客户端 + TanStack Query
│   │   ├── api-types.ts          # 自动生成,从 OpenAPI
│   │   ├── ws.ts                 # WS 客户端
│   │   └── ws-events.ts          # 手写 WSEvent 联合类型
│   └── package.json
│
├── skills/                       # Skill YAML 库
│   ├── anti_fraud_video.yaml              # V1 hero(v3.0)
│   ├── ecommerce_detail_image.yaml        # V1 副
│   └── ppt_create.yaml                    # V1.5
│
├── flywheel/                     # 数据飞轮 pipeline
│   ├── ingestion/                # 信号采集
│   ├── reflexion/                # 失败 → prompt 改进
│   ├── skill_drafter/            # 高满意度 → Skill 草稿
│   └── preference_embedder/      # 偏好向量更新
│
├── infrastructure/
│   ├── docker-compose.yml        # dev
│   ├── docker-compose.mock.yml   # mock 服务(LiteLLM mock 等)
│   ├── k8s/                      # prod manifests
│   └── litellm/
│       ├── litellm_config_l1.yaml
│       └── litellm_config_l2.yaml
│
└── scripts/
    ├── gen-api-types.sh          # 生成前端 ts 类型
    └── seed-bgm-library.py       # BGM 素材库种子数据
```

---

## 2. 完整技术选型(13 分类)

> 所有版本号是**最低版本下限**,可向上但不向下。

### 2.1 运行时与基础语言

| 项 | 选型 | 版本 |
|----|------|-----|
| Python | CPython | 3.12+ |
| Node | Node.js | 20 LTS+ |
| TypeScript | 强制启用 | 5.4+ |
| 包管理(后端)| **uv** | 最新 |
| 包管理(前端)| **pnpm** | 9+ |
| 镜像基础 | python:3.12-slim + node:20-alpine | |

### 2.2 后端框架

| 项 | 选型 | 版本 | 用途 |
|----|------|-----|------|
| Web | **FastAPI** | 0.115+ | |
| ASGI | uvicorn | 0.32+ | --workers 多进程 |
| 校验 | **Pydantic v2** | 2.9+ | |
| Settings | Pydantic Settings | 2.6+ | |
| ORM | **SQLAlchemy 2.0 async** | 2.0+ | |
| DB 驱动 | asyncpg | 0.30+ | |
| 迁移 | Alembic | 1.13+ | |
| 鉴权 | FastAPI Users | 12.x | JWT + 短信 |
| Redis | redis-py async | 5.x | streams + pubsub + lua |
| HTTP | **httpx** | 0.27+ | 全异步 |
| 任务队列 | Celery | 5.4+ | broker=Redis |
| 编排引擎 | **LangGraph** | 0.2+ | + langgraph-checkpoint-postgres |
| LLM 网关 | **LiteLLM Proxy** | 1.50+ | 独立容器 |
| MCP | mcp Python SDK + @modelcontextprotocol/sdk | latest | ADR-009 |
| 日志 | **structlog** | 24+ | JSON 带 task_id |
| 错误追踪 | Sentry SDK | 2.x | prod |
| Tracing | OpenTelemetry | 1.27+ | Jaeger backend(V1.5)|
| 代码质量 | **ruff** + **mypy --strict** | 0.7+ / 1.13+ | |

### 2.3 数据 / 存储 / 中间件

| 项 | 选型 | 用途 |
|----|------|------|
| 关系库 | PostgreSQL 16 + pgvector 0.7+ | 主库,18 张表 |
| 向量库(独立)| **Qdrant 1.13+** | 工作流轨迹 RAG(ADR-011)|
| 缓存 / 队列 | Redis 7.2+ | |
| 对象存储 prod | 阿里云 OSS | |
| 对象存储 dev | MinIO | |
| OSS 客户端 | oss2 / boto3 | |
| 中文分词 | jieba 0.42+ | Skill 关键词检索 |
| Embedding(检索)| **BGE-M3 自托管** | 1024 维 |
| Embedding(偏好)| **bge-base-zh-v1.5** | 256 维 |
| 短信 | 阿里云短信 | |
| OCR | Tesseract + 阿里云 OCR | MCP server 包装 |

### 2.4 前端

| 项 | 选型 | 备注 |
|----|------|------|
| 框架 | Next.js 15 App Router | RSC + Server Actions |
| UI | shadcn/ui + Radix | |
| 样式 | Tailwind v4 | |
| 图标 | lucide-react | **无 emoji** |
| 状态 | Zustand 4+ | |
| 数据 | TanStack Query v5 | |
| 表单 | react-hook-form + zod | |
| 视频 | shaka-player + 原生 video | HITL 视频预览 |
| 日期 | dayjs | |
| Markdown | react-markdown + remark-gfm | |
| 代码高亮 | shiki | |
| WS | 原生 + 自封装重连 | 不用 socket.io |
| PWA | next-pwa | |
| Lint | ESLint 9 + Prettier 3(或 Biome) | |
| 单测 | Vitest 2 | |
| E2E | Playwright 1.48 | |
| 包管理 | pnpm workspace | |

### 2.5 智能体系统(MCP-first)

工具不再写死在 Agent handler 里,而是以 **MCP server** 形式独立部署。

V1 必上线 7 个 MCP server:

| Server | 实现 | tools |
|--------|------|------|
| `mcp-search` | Python | web_search / web_fetch |
| `mcp-image-tools` | Python | bg_remove / enhance / concat_long / quality_check |
| `mcp-video-tools` | Python(GPU)| compose / extract_frames / subtitle_align |
| `mcp-audio-tools` | Python | tts / asr / bgm_match |
| `mcp-document-tools` | Python | pptx / xlsx / docx / pdf |
| `mcp-oss` | Python | upload / download / sign_url |
| `mcp-platform-publish`(V1.5)| TypeScript | douyin / xhs / wechat |

**Agent handler 调用范式**:

```python
from agents._common.mcp_client import mcp_client

# 不允许:from tavily import TavilyClient
# 允许:
results = await mcp_client.call_tool(
    server="search",
    tool="web_search",
    arguments={"query": "...", "max_results": 5}
)
```

**例外**:生成式模型(GPT-Image-2 / Veo-3 / Volcengine TTS)走 LiteLLM,**不**走 MCP。

详见 `docs/3_决策记录/MCP 集成方案.md`。

### 2.6 模型路由(L1 编排层)

| 角色 | 模型 |
|------|------|
| 主力 | `deepseek-v4-flash` |
| 备 1 | `claude-haiku-4-5` |
| 备 2 | `gpt-5-mini` |

调用点:意图理解、Skill 匹配兜底、中断分类、Brief 维护、HITL 用户决定解析、回滚目标计算、MCP tool 决策。

### 2.7 模型路由(L2 执行层)

按 task_type 选模型,完整表见 `docs/4_附录/模型路由表.md`。短视频核心:

| task_type | 主力 | 备 |
|-----------|------|-----|
| short_video_script | deepseek-v4-pro | kimi-k2 / claude-sonnet-4-6 |
| short_video_hook | claude-sonnet-4-6 | gpt-5 |
| image_generate(真实)| gpt-image-2 | seedream-3 |
| image_generate(卡通)| nano-banana-2 | seedream-3 |
| image_to_video | seedance-2 | kling-2 / veo-3 |
| text_to_video | veo-3 | seedance-2 |
| tts_generate | volcengine-tts | aliyun-tts |
| audio_to_text | whisper-v3 自托管 | aliyun-asr |
| bgm_select | (素材库,无 LLM)| - |

### 2.8 部署 / DevOps

| 项 | 选型 |
|----|------|
| 容器 | Docker + buildx |
| dev | Docker Compose v2 |
| prod | K8s 1.30+(阿里云 ACK)|
| GitOps | ArgoCD |
| Helm | 3.16+ |
| Secret | K8s Sealed Secrets |
| 网关 | Nginx Ingress Controller |
| CDN | 阿里云 CDN(视频 mp4 关键)|
| 容器仓库 | 阿里云 ACR |
| Celery dashboard | Flower 2+ |
| LLM dashboard | LiteLLM 自带 |

### 2.9 CI / CD

| 项 | 选型 |
|----|------|
| CI | GitHub Actions |
| CD | ArgoCD(main → staging 自动)|
| 镜像扫描 | Trivy |
| 灰度 | K8s rolling + ArgoCD |
| Lint(Python) | ruff check |
| Type(Python) | mypy --strict |
| 测试覆盖率 | 后端 70% / 前端 60% |
| 特殊 CI 检查 | MCP integration / HITL Playwright / 飞轮信号 PR check / Prompt 回归 |

### 2.10 监控 / 可观测

| 维度 | 选型 |
|-----|------|
| 指标 | Prometheus + Grafana |
| 日志 | Loki + Promtail |
| Tracing | Jaeger(V1.5)|
| 错误追踪 | Sentry |
| Uptime | 阿里云云监控 |

### 2.11 测试

| 维度 | 选型 |
|-----|------|
| 后端单测 | pytest + pytest-asyncio + pytest-cov |
| 集成 | pytest + httpx.AsyncClient + testcontainers |
| Prompt 回归 | 自定义 pytest fixtures + yaml |
| 负载 | locust |
| E2E | Playwright |
| 前端单测 | Vitest + @testing-library/react |
| Mock | respx + fakeredis + pytest-mcp |

### 2.12 安全 / 合规

| 项 | 选型 |
|----|------|
| HTTPS | cert-manager + Let's Encrypt |
| CORS | 严格白名单 |
| 鉴权 | JWT in Authorization header |
| 内容安全 | 阿里云内容安全 |
| 速率限制 | slowapi(IP 分组,默认 120 RPM;`/sms/send`、`/login` 再叠加更严配额) |
| 备案 | 算法备案 + 生成式 AI 服务备案 |

### 2.13 不引入这些(挡再讨论)

| 没用 | 理由 |
|------|-----|
| Temporal | V1 Celery 够 |
| Kafka | Redis Streams 够 |
| ElasticSearch | Qdrant + pgvector + pg_trgm 够 |
| Socket.io | FastAPI WS + Redis Pub/Sub |
| GraphQL | REST 够 |
| Istio | K8s 原生 Service 够 |
| Vault | Sealed Secrets 够 |
| React Native | V1 PWA |

---

## 3. 主编排 9 子模块概览(v3.0)

| # | 子模块 | 调 LLM | 主要职责 | 模型 |
|---|--------|-------|---------|------|
| 1 | 意图理解器 | ✅ | 自然语言 → 意图 JSON(含模式切换识别)| L1 |
| 2 | Skill 匹配器 | 99% 不调 | L1 关键词 / L2 向量 / L3 LLM | L1 兜底 |
| 3 | 输入校验器 | ❌ | 字段是否齐全 | - |
| 4 | 澄清生成器 | 大部分不调 | 4 种澄清形式 | L1 |
| 5 | 任务编排器 | ❌ | Jinja2 渲染 + AgentTask 打包 | - |
| 6 | 中断处理器 | ✅ | 8 类中断分类(含 V1 中断 C 回滚)| L1 |
| **7** | **三模式管理器** | ✅(brief)| **Plan / Ask / Auto 同群切换** + brief 维护 | L1 |
| 8 | HITL 网关管理器 | 半 | 在关键节点暂停等待用户 | L1 |
| **9** | **Agent 互动编排器**(v3.0)| ✅ | 派活时编排 Agent 间交接对话 | L1 |

详细实现:`docs/2_工程实现/主编排 Agent 实现指南.md`

---

## 4. 4 个分任务 Agent 边界(v3.0 ADR-001-rev)

| Agent | 角色 | 队列 | 主要 task_type | 长任务 |
|-------|-----|------|--------------|------|
| 1 | 研究员/文案师 | `agent_tasks:text` | short/long/structured_writing / web_search | 否 |
| **2** | **文档专员** | `agent_tasks:document` | pptx_assemble / xlsx_assemble / pdf_extract / image_concat_long | 否 |
| **3** | **设计师** | `agent_tasks:image` | image_generate / batch_generate / image_download / quality_check | 否 |
| **4** | **影音师** | `agent_tasks:av` | text_to_video / image_to_video / video_compose / tts / bgm_select | **是**(Celery)|

**+ 2 个支持 Agent**(常驻主会话,ADR-013):

| 角色 | 实现 | 触发 |
|------|-----|------|
| HR | 主编排在主会话用 HR_SYSTEM_PROMPT 渲染 | intent_type=team_management |
| 财务经理 | 主编排在主会话用 FINANCE_SYSTEM_PROMPT 渲染 + 调 QuotaService | intent_type=quota_query |

**协作规则**:
- 不互相调用(ADR-002)
- 跨能力步骤在 Skill YAML 显式拆步
- 跨语言通信走 Redis Streams + AgentTask / AgentResult

详细 handler 实现:`docs/2_工程实现/4 个分任务 Agent 实现指南.md`

---

## 5. 数据库 schema(18 张表概览)

### 用户与权限
- `users`(基本信息 + plan)
- `user_preferences`(含 `preference_vec VECTOR(256)`,信号 2)

### 会话与上下文(v3.0 ADR-014)
- `context_pools`(每群一个 pool)
- `conversations`(mode = main_session / **group** / private_chat;**新增 `work_mode` 列** = plan / ask / auto)
- ~~`conversation_links`~~(已废,v3.0 不再有讨论群衍生工作群关系)
- `mode_switch_log`(模式切换审计,可选)

### 消息
- `messages`

### Skill
- `skills`
- `skill_embeddings`(pgvector,Skill L2 检索)
- `user_skill_visibility`

### 任务执行
- `tasks`
- `task_steps`
- `artifacts`(支持版本号,中断 C 旧产物保留)

### 配额
- `quota_usage`

### BGM 素材
- `bgm_library`

### v2.0 新增 5 张
- `hitl_gates`(HITL gate 历史)
- `workflow_traces`(信号 1,Qdrant 镜像)
- `prompt_improvement_candidates`(信号 3,Reflexion)
- `skill_drafts`(信号 4,创作者飞轮 V1.5)
- `user_preferences.preference_vec` 列(信号 2)

完整 DDL:`docs/5_工程基建/V1 工程基建清单.md §4`

---

## 6. 前端架构

### 6.1 关键页面

- `/`:主会话(总裁助理)
- `/[conversationId]`:群聊(三栏)
- `/private/[agentId]`:私聊单 Agent
- `/materials`:素材库 + 知识库
- `/academy`:AI 学院
- `/market`:技能市场
- `/results`:成果库
- `/settings`:设置

### 6.2 Zustand store 切片

| store | 职责 |
|-------|-----|
| `conversation` | 会话列表 + 当前会话 |
| `task` | 任务进度 / steps / streaming |
| `ws` | WebSocket 连接 + 重连 + last_event_id |
| **`hitl`** | HITL gate 队列 / 用户决定 |
| `user` | 当前用户 / 偏好 |

### 6.3 关键交互组件

- 三栏布局(左导航 / 中聊天 / 右执行流)
- 群成员栏(顶部,总裁助理永远第 1 位)
- 澄清气泡(浅绿底,4 种形式)
- 产物预览卡片([下载] [追问] [改一下])
- 右栏执行流(流式追加,3 种状态图标)
- @ 调用(@人 / @文件 / @提示词)
- **HITL 审核组件 3 个**(ScriptApproval / ImageSelection / VideoFinalReview)

### 6.4 视觉规范

- 唯一强调色:微信绿 #07C160
- 讨论群浅蓝头像(#E3F2FD) + 蓝色"讨论"徽章
- 工作群浅绿头像(#E8F5E9) + 微信绿"工作"徽章
- 头像统一"我的世界"像素风/NFT 风格
- 线条 SVG 图标,**无 emoji**

### 6.5 WS 事件类型

```typescript
type WSEvent =
  | { type: 'conversation_created'; conversation: Conversation }
  | { type: 'message_added'; message: Message }
  | { type: 'step_started'; task_id: string; step_id: string; agent_id: string }
  | { type: 'step_completed'; task_id: string; step_id: string; artifact: ArtifactPreview }
  | { type: 'step_streaming'; task_id: string; step_id: string; chunk: string }
  | { type: 'task_completed'; task_id: string; primary_artifact: Artifact }
  | { type: 'task_failed'; task_id: string; error: ErrorDetail }
  | { type: 'clarification_required'; task_id: string; clarification: Clarification }
  | { type: 'mode_choice_required'; conversation_id: string; options: ModeOption[] }
  | { type: 'work_group_proposed'; discuss_id: string; skill_id: string }
  | { type: 'brief_updated'; pool_id: string; brief: Brief }
  | { type: 'hitl_gate_opened'; task_id: string; gate: HITLGate; preview_artifact: Artifact }
  | { type: 'hitl_gate_closed'; task_id: string; resolution: 'approved'|'modified'|'rolled_back' }
  | { type: 'rollback_started'; task_id: string; from_step: string; to_step: string }
  | { type: 'quota_warning'; quota_type: string; remaining: number };
```

---

## 7. 关键 API 端点

```
# 鉴权
POST /api/auth/sms/send
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
GET  /api/auth/me

# 会话(v3.0 ADR-014)
GET  /api/conversations
POST /api/conversations              Body: {mode, work_mode, skill_id?, name?}
GET  /api/conversations/:id
POST /api/conversations/:id/switch-work-mode   ← v3.0 替代 derive-work-group/back-to-discuss
                                                Body: {target: plan|ask|auto, triggered_by: user|orchestrator}

# 上下文池
GET  /api/context-pools/:id
PATCH /api/context-pools/:id/brief

# 任务
GET  /api/tasks/:id
POST /api/tasks/:id/answer-clarification
POST /api/tasks/:id/interrupt

# HITL(v2.0)
GET  /api/tasks/:id/hitl_gates
POST /api/tasks/:id/hitl_gates/:gate_id/approve
POST /api/tasks/:id/hitl_gates/:gate_id/modify
POST /api/tasks/:id/hitl_gates/:gate_id/rollback

# 飞轮(v2.0)
GET  /api/users/:id/preference_vector
GET  /api/users/:id/skill_drafts
POST /api/skill_drafts/:id/publish

# 上传
POST /api/upload/sign
POST /api/upload/confirm

# WebSocket
WS   /ws?token=xxx&last_event_id=xxx
```

---

## 8. 部署架构

### 8.1 dev(Docker Compose 一键)

```
postgres + redis + minio + qdrant + litellm-mock
    ↓
backend(uvicorn)
    ↓
agents × 4(独立容器)
    ↓
mcp_servers × 7(独立容器)
    ↓
celery_worker_video(GPU 节点 / CPU dev 也行)
    ↓
frontend(next dev)
```

### 8.2 prod(K8s)

| 服务 | 副本 | 资源 |
|------|-----|------|
| backend | 4 | 1c / 2G |
| litellm-proxy | 2 | 0.5c / 1G |
| agent-text | 4 | 2c / 4G |
| agent-image | 4 | 4c / 8G |
| agent-av | 2 | 4c / 8G + GPU |
| agent-document | 2 | 2c / 4G |
| celery-video | 4 | 4c / 8G + GPU |
| mcp-search/oss/document/audio | 各 2 | 0.5-2c / 1-4G |
| mcp-image-tools | 2 | 1c / 2G + GPU |
| mcp-video-tools | 2 | 4c / 8G + GPU |
| qdrant | 3(StatefulSet)| 2c / 8G + SSD |
| bge-m3-service | 2 | 4c / 8G + GPU |
| frontend(SSR)| 2 | 1c / 2G |

V1 总资源:约 30 vCPU / 80 GB 内存 + 4 个 GPU 节点。

---

## 9. 跨语言 Schema 同步

**后端是源**:Pydantic 模型 in `backend/app/schemas/`

**前端生成**:`pnpm gen:api` 跑 `openapi-typescript` 生成 `frontend/lib/api-types.ts`

**MCP server schema**:用 `mcp.types` Python SDK 自动生成 JSON Schema

CI 强制:PR 修改 `schemas/` 必须重跑 `pnpm gen:api` 并 commit。

---

## 10. 详细 Sprint 路径

每 Sprint 的 acceptance 见 CLAUDE.md §4。本文给出详细 deliverable:

### Sprint 0(1 周):基础设施

- 仓库目录骨架(参考本文 §1)
- `infrastructure/docker-compose.yml`
- `backend/alembic` + 18 张表 migration
- `backend/app/config/{settings,prompts,templates}.py`
- `backend/app/router.py`(LiteLLM 客户端)
- `backend/app/mcp_client.py`(MCP 客户端)
- `backend/app/api/auth.py`
- `backend/app/ws/`

### Sprint 1(1 周):MCP servers

- `mcp_servers/search/`(Tavily + Playwright)
- `mcp_servers/oss/`(MinIO 兼容)
- `mcp_servers/document_tools/`(pdf 基础)
- 集成测试 fixtures

### Sprint 2(1.5 周):主编排框架

- 8 子模块骨架
- `services/{conversation,context_pool,brief_builder,quota,oss,hitl,flywheel}.py`
- 端到端意图理解 → Skill 匹配 → 输入校验 跑通

### Sprint 3(1.5 周):Agent 框架 + 短视频 happy path

- `agents/_common/`
- 4 个 Agent main.py
- 各 1 个 happy-path handler
- 短视频任务端到端跑通(全 mock)

### Sprint 4(1 周):Skill + HITL + 飞轮

- `skills/anti_fraud_video.yaml`(v3.0 V1 hero)
- `skills/ecommerce_detail_image.yaml`
- Skill 编译器
- HITL 网关后端 + 中断 C 回滚
- `flywheel/` 4 类信号 pipeline

### Sprint 5(2 周):前端

- Next.js 15 骨架
- Zustand store 5 个切片
- WS 客户端
- 三栏布局 + 群聊页 + 右栏执行流
- HITL 审核组件 3 个
- 模式选择 UI

### Sprint 6(1 周):联调 + 上线

- CI(含 MCP 集成 + HITL Playwright + 飞轮 PR check)
- K8s manifests
- 监控大盘
- E2E 跑 10 次任务

**总计 8 周 → V1-P0**

---

## 11. 性能与成本目标

| 指标 | V1 目标 |
|-----|--------|
| 主编排单调用延迟 | < 1s |
| 主编排单任务总成本 | $0.001-0.003 |
| 短视频单条总成本(模型 + 工具)| **¥6-8**(优化后)|
| 详情图单张总成本 | ¥2-3 |
| 视频任务 P95 端到端时间 | < 8 分钟 |
| HITL gate 用户响应 P50 | < 2 分钟 |
| 飞轮信号沉淀率 | 100% |
| 系统可用性 | 99.5% |

---

## 12. 相关详细文档(深入查)

| 主题 | 文档路径 |
|------|---------|
| 主编排详细实现 | `docs/2_工程实现/主编排 Agent 实现指南.md` |
| 4 Agent 详细实现 | `docs/2_工程实现/4 个分任务 Agent 实现指南.md` |
| 三种模式技术细节 | `docs/2_工程实现/三种模式技术实现.md` |
| MCP 集成方案 | `docs/3_决策记录/MCP 集成方案.md` |
| 数据飞轮设计 | `docs/3_决策记录/数据飞轮设计.md` |
| 商业模型 | `docs/3_决策记录/商业模型与单位经济.md` |
| Skill YAML 模板 | `docs/3_决策记录/Skill YAML 模板.md` |
| 系统 Prompt 全集 | `docs/4_附录/系统 Prompt 全集.md` |
| 模型路由表 | `docs/4_附录/模型路由表.md` |
| V1 工程基建清单 | `docs/5_工程基建/V1 工程基建清单.md` |
| 产品文档 | `docs/0_总览/产品功能与交互文档.md` |
| ADR 全集 | `docs/CONSTITUTION.md` 与 `docs/3_决策记录/开放问题与决议.md` |
