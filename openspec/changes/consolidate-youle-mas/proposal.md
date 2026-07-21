## Why

`youle_03` 已具备质量最高的 LangGraph、PostgreSQL/Alembic、Redis Streams、Agent Worker、MCP 和 Skill 契约，但正式前端缺失，实时事件仍只有独立 WebSocket 通道，OTP、Skill 市场和跨语言契约的测试与 CI 也不完整。四个仓库继续独立演进会扩大模型、路由、编排和依赖冲突，因此需要在不破坏主干的前提下完成一次可验证的择优整合。

## What Changes

- 将仓库工程名和文档统一为 `youle-mas`，只保留根 `backend/`、`agents/`、`frontend/` 三个正式运行模块。
- 保留 `youle_03` 唯一后端、LangGraph 主编排、Redis 任务总线、Agent Worker、MCP、JWT、短信 OTP 和 Alembic 历史。
- 新增统一事件发布接口，底层同时支持 Redis Pub/Sub、SSE、WebSocket 和 PostgreSQL 短期回放；SSE 支持 Bearer 鉴权、用户/会话归属、heartbeat、事件 ID、`Last-Event-ID` 和断线重连。
- 建立根 `frontend/` Next.js 应用，交付登录、会话、群聊、Agent 私聊、任务状态、HITL、Skill 市场、素材/成果和错误/重连状态；生产路径只调用真实主干 API，mock 必须显式开启。
- 在现有 Skill/YAML 和用户可见性模型上补齐内置、安装、启用、禁用、版本、权限、MCP 与 Agent 类型状态，不执行市场中的不可信代码。
- 保留现有 @Agent 和群成员管线，补齐统一消息/事件契约、AgentTask/AgentResult 契约和 mock LLM 端到端覆盖。
- 强化 OTP 原子一次性消费、过期和错误行为测试，不新增第二套 User 或登录路由。
- 将 CI 拆成阻断式 backend、agents、frontend、contract、security 检查，并生成迁移、基线、最终验证和第三方归属文档。
- **BREAKING**：README 中不存在的嵌套前端路径被根 `frontend/` 取代；前端生产环境不再默认回退纯 mock。

## Capabilities

### New Capabilities

- `unified-event-delivery`: 统一事件模型、发布入口、SSE/WS/Redis 分发、持久化回放和重连行为。
- `canonical-frontend`: 唯一 Next.js 前端、真实 API/SSE 接入、群聊/私聊/HITL/任务/素材/成果页面和显式 mock 模式。
- `skill-marketplace-lifecycle`: Skill 搜索、详情、安装、启用、禁用以及版本、权限、MCP/Agent 要求展示。
- `auth-otp-hardening`: 保留主干 JWT/短信登录并保证 OTP 限流、过期、错误码和一次性消费。
- `multi-agent-contracts`: 群内 @Agent、私聊、AgentTask/AgentResult、统一消息和事件类型的后端/前端契约。
- `blocking-delivery-pipeline`: backend/agents/frontend/contract/security 阻断式 CI、mock E2E、迁移与验证报告。

### Modified Capabilities

无现有 OpenSpec capability；这是仓库首次初始化 OpenSpec。

## Impact

- 代码：`backend/app/api`、`backend/app/services`、`backend/app/models`、`backend/app/schemas`、`backend/alembic`、`agents`、新增根 `frontend/`。
- API：新增 SSE 事件流和 Skill 生命周期端点；保留现有 REST、WebSocket、JWT 和短信登录兼容性。
- 数据：只通过新的 Alembic revision 增加事件回放和 Skill 安装/启用状态所需字段或表。
- 依赖：沿用 Python 3.12、uv、FastAPI、PostgreSQL、Redis、LangGraph、Next.js、pnpm；不引入 Agno、Kafka、Socket.IO 或第二套状态库。
- 运维：根 `.github/workflows/`、Docker Compose、OpenAPI/TypeScript 生成、secret/dependency audit。
- 归属：保留 Hermes/Nous Research 文件头并新增 `THIRD_PARTY_NOTICES.md`；四个源仓缺少根许可证的事实必须公开记录。
