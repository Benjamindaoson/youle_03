## Context

`youle_03` 是唯一主干，当前有 474 个文件、完整 Python 后端/Agent/MCP/Alembic 和 61 个 backend/agents 测试文件，但 README 所述前端目录实际不存在。`oye-mas` 的群成员、@Agent、Skill 详情已经被主干吸收；`youle01` 提供产品 UI；`youle-agno` 提供经过测试的 EventBus/SSE/OTP 增量，但其 Agno 编排、根 `src/` 模型和启动 `create_all` 与主干冲突。

实现必须保留单一 LangGraph 调度者、Redis Streams AgentTask/AgentResult、LiteLLM、MCP 和已有 Alembic 历史。所有新行为先写失败测试；数据库变更只追加 revision。Docker 当前安装但 daemon 未运行，需在最终验证报告中区分代码失败与环境阻塞。

## Goals / Non-Goals

**Goals:**

- 建立唯一、真实可构建的根 `frontend/`，覆盖登录、群聊、私聊、任务、HITL、Skill、素材与成果。
- 建立业务层无传输协议感知的 `publish_user_event`，让 SSE 与 WebSocket 消费同一事件。
- 让事件支持 Redis 跨进程、本地降级、有限队列、事件 ID、PostgreSQL 回放和 `Last-Event-ID`。
- 在现有 Skill/UserSkillVisibility 上表达安装和启停状态，并保持 YAML 为唯一执行契约。
- 保留主干 OTP/JWT/User 并补齐原子一次性消费与测试。
- 让 backend、agents、frontend、contract、security CI 都是阻断式检查。
- 提供无真实 API Key 的 mock 端到端验证和可复现报告。

**Non-Goals:**

- 不迁入 Agno、第二套主编排、第二套任务系统、第二套 User/Conversation/Message 模型。
- 不实现 Skill 创作者上传、审核、分润或执行第三方任意代码。
- 不引入 Kafka、Temporal、Socket.IO、GraphQL 或新的客户端状态库。
- 不擅自为四个源仓选择开源许可证，也不自动合并 Pull Request。
- 不把真实模型 smoke test 设为普通 PR 的阻断检查。

## Decisions

### 1. 主干和目录边界

正式目录固定为 `backend/`、`agents/`、`frontend/`。`youle01/backend`、`oye-mas/youle/backend`、`youle-agno/src` 都只作参考。备选的“直接复制四仓”会保留重复路由和模型；“从零重写”会丢失主干 61 个测试文件和已验证架构，因此均排除。

### 2. 前端底座

使用 `oye-mas/youle/frontend` 作为工程底座，因为它已经按主干 REST 模型实现登录、群聊、HITL、市场、素材/成果和 Playwright；从 `youle01` 迁入落地页以及群聊/私聊中不重复且质量更高的产品交互。所有数据请求集中到 `frontend/lib/api.ts`，服务端状态由查询/API 管理，Zustand 只保存会话选择、临时输入、连接和 HITL UI 状态。生产不回退 mock；`NEXT_PUBLIC_MOCK_MODE=true` 才启用 mock。

### 3. 统一事件模型

新增 Pydantic `UserEvent`：`id`、`type`、`user_id`、可选 `conversation_id/task_id/agent_id`、`payload`、`created_at`。事件类型覆盖 agent message、task、HITL、artifact、skill、error 和既有 UI 事件。OpenAPI 是前端 TypeScript 类型源。

业务代码只调用：

```python
await event_publisher.publish_user_event(
    user_id=user_id,
    event_type=EventType.TASK_COMPLETED,
    payload={"task_id": str(task_id)},
    conversation_id=conversation_id,
    task_id=task_id,
)
```

兼容期 `ws_manager.publish()` 委托给该接口，避免一次性改动所有生产者。

### 4. 事件投递与回放

发布顺序为：构造稳定事件 ID → 尝试写 PostgreSQL `user_events` → Redis `youle:events:{user_id}` → 每个 backend 进程本地 fan-out。Redis 不可用时直接本地投递；持久化失败记录结构化错误但不阻断实时投递。每个订阅队列固定上限，满时丢最旧事件保留最新状态。

SSE 路由为 `GET /api/conversations/{conversation_id}/events`：Bearer JWT 鉴权并校验 `Conversation.user_id`；先按 `Last-Event-ID` 从 PostgreSQL 回放，再消费实时队列；定时发送 heartbeat comment；客户端断开时取消等待并 unsubscribe。WebSocket 端点使用相同本地订阅，不再维护第二条 Redis channel。

### 5. Skill 生命周期

复用 `UserSkillVisibility`，将 `relationship` 的正式值统一为 `installed_enabled`、`installed_disabled`；平台内置 Skill 对用户视为 installed/enabled，但仍可显式禁用。Skill 详情从 YAML 安全解析版本、输入、步骤、需要的 MCP 和 Agent 类型，仅展示摘要，不执行上传代码。保留旧 `subscribe` 端点为兼容别名，新增明确 install/enable/disable 端点。

### 6. OTP

继续使用 Redis TTL 和主干短信发送。新增小型 auth service，以 Redis 原子 compare-and-delete（Lua 或事务）消费验证码，避免并发重复登录；验证码生成、发送失败清理、错误、过期、refresh 都有测试。不迁入 Agno 邀请码、邮箱身份表或第二套 auth challenge 表。

### 7. CI 和验证

拆分 workflow 但复用项目现有命令。backend 跑 Ruff、compileall、Alembic、unit/smoke；agents 跑 Ruff、pytest、import/schema/黑名单；frontend 固定 frozen install、lint、typecheck、test、build，目录不存在即失败；contract 生成 OpenAPI 并检查 TS、Event、AgentTask/Result、Skill；security 跑 gitleaks、pip-audit、pnpm audit 和高风险配置检查。E2E 默认 `LITELLM_MOCK=true`。

## Risks / Trade-offs

- [来源前端与主干 API 仍有字段漂移] → 先建立 API client/契约测试，再迁页面；禁止组件各自拼 URL。
- [Redis Pub/Sub 不保存历史] → PostgreSQL `user_events` 提供有限回放；Redis 只负责低延迟广播。
- [持久化和实时发布不是分布式事务] → 稳定事件 ID + 前端幂等去重；持久化失败可观测但不阻断实时体验。
- [兼容 `subscribe` 名称会暂时保留旧语义] → 仅作为 install/enable 别名，文档标记弃用，不建立第二套状态。
- [完整前端迁入差异较大] → 先复制可构建底座并跑原有 E2E，再逐页改真实 API；不迁 legacy 页面和重复 store。
- [Docker daemon 不可用] → 先完成无 Docker 单测/静态验证；最终再次尝试 Docker，并把未验证项明确标记为阻塞。
- [四仓无根 LICENSE] → 不添加猜测许可证；PR 明确要求仓库所有者选择项目许可证。

## Migration Plan

1. 记录主干基线并提交审计/OpenSpec 文档。
2. 强化 CI，先让现有 backend/agents 检查可重复运行。
3. TDD 添加统一事件模型、EventBus、持久化 migration 和 SSE；保留 WS 兼容。
4. TDD 强化 OTP 和 Skill 生命周期。
5. 迁入单一 frontend，先通过 frozen install/build，再接真实 auth/conversation/message/SSE/Skill API。
6. 补 Agent/前端/contract/E2E 测试和 mock 全链路。
7. 更新 README、CONTRIBUTING、NOTICE 和迁移/验证报告。
8. 全量验证、分阶段提交、推送 Draft PR；任何失败保持可追溯，不自动合并。

回滚按阶段 commit 进行；数据库只追加向下 migration，前端可独立回退，旧 WebSocket 兼容在 SSE 稳定前保留。

## Open Questions

- 项目所有者尚未提供四仓许可证选择；当前只能保留来源署名并报告缺失。
- Docker Desktop daemon 当前未启动；最终容器/E2E 是否可在本机验证取决于该外部状态。

