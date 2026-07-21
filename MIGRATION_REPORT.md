# youle-mas 整合报告

日期：2026-07-21
整合分支：`codex/youle-mas-consolidation`
唯一主干：`Benjamindaoson/youle_03@14815ee`

## 结论

四个仓库没有被机械拼接。最终工程只保留 `backend/`、`agents/`、`frontend/` 三个正式应用根目录，以 `youle_03` 的 FastAPI、SQLAlchemy/Alembic、Redis Streams、LangGraph、Agent Worker、MCP 和 Skill YAML 为事实来源。其他仓库只迁移了不重复且能接入该边界的产品、事件和安全增量。

## 各来源迁移内容

### youle_03

保留并扩展：

- FastAPI 路由、User/Conversation/Message/Task/Skill/Artifact/HITL 模型。
- PostgreSQL、Alembic、Redis、LiteLLM Router、对象存储和配额服务。
- 唯一 LangGraph 主编排器、四个 Redis Worker 和七个 MCP 服务。
- `AgentTask`/`AgentResult`、Skill YAML、任务编译、HITL 和记忆模块。
- 根工作流、Makefile、Procfile 和基础设施 Compose。

整合前的 Ruff、测试收集、Skill 编译、头像/配额测试等基线缺陷先用独立提交修复，再开始功能迁移。

### youle01

选择性迁移：

- `/website` 产品落地页的信息结构和视觉方向，替换了来源中的占位文案并接入正式登录。
- 群聊、员工私聊和团队化展示中不重复的产品表达。

未迁移：

- 来源后端、conductor、SQLite/本地 trace、直接模型 SDK 调用。
- `lib/store.ts`、`lib/chat-store.ts` 等重复状态层。
- 旧 Messenger/V1/legacy 工作台和占位页面。

原因：这些实现会制造第二套后端、编排器、消息模型或客户端事实源。

### oye-mas

迁移并重构：

- Next.js 15 正式前端工程底座：登录、会话、群聊、私聊、成员、`@Agent`、任务、HITL、素材、成果、学院、市场和设置。
- Skill 市场页面与详情展示。
- 原有 Playwright 场景，修订为显式 mock 浏览器测试；真实长视频场景保留为 opt-in skip。

重构点：

- 删除默认 mock fallback，只有 `NEXT_PUBLIC_MOCK_MODE=true` 才进入 mock。
- 集中 typed API client、JWT 持久化和结构化错误。
- 群聊与私聊共用消息 store；新增真实消息历史 API。
- WebSocket 兼容保留，但正式会话实时更新改为统一 SSE/UserEvent。
- Skill 从“订阅/取消”改为内置、未安装、已安装启用、已安装停用生命周期。
- 清理页面重复 `AppShell`，新增认证 hydration 门禁，支持受保护页面刷新。

未迁移来源中的旧 `youle/backend` 和 `youle/agents`，因为它们是主干的较早副本。

### youle-agno

迁移的是设计与行为，不是 Agno 架构：

- 每用户 EventBus 队列、多订阅者 fan-out、Redis Pub/Sub、本地 fallback、队列上限与淘汰最旧事件、JSON 安全序列化、start/stop。
- Bearer SSE、会话归属、heartbeat、稳定事件 ID、`Last-Event-ID` 和 PostgreSQL replay。
- OTP 的过期、一次性原子消费、发送失败清理和生产短信 adapter 思路。

未迁移：

- Agno Team/SkillRunner、第二套 `src/backend`、第二套 User/OTP 路由、进程内 stream registry。
- 运行时 `create_all`、Agno 任务模型和第三套前端。

## 删除或拒绝的重复架构

- 没有引入 `src/backend/`、`youle/backend/`、`legacy_backend/`。
- 没有引入 Agno 主编排、youle01 conductor 或第二套任务总线。
- 没有保留第二套前端 store、消息模型、默认 mock API 或手写 EventType 联合类型。
- 没有让 Agent 跨模块直接调用，也没有新增 OpenAI/Anthropic 直连。
- 没有创建新的默认 SQLite 数据库或启动时建表路径。

`backend/scripts/check-contracts.py` 和 CI 会阻止上述架构回流。

## 数据库变化

只追加两个 Alembic revision：

1. `20260721_0005_user_events.py`
   - 新增 append-only `user_events`。
   - 稳定 UUID 事件 ID、用户/会话/任务索引、事件类型、JSON payload 和创建时间。
   - 用于 SSE 断线回放。
2. `20260721_0006_skill_lifecycle.py`
   - 规范 `user_skill_visibility.relationship` 为安装/启停关系。
   - 增加约束与迁移兼容逻辑，不修改旧 revision。

Alembic history 静态链为 `0001 → … → 0006 (head)`。本机 Docker Desktop daemon 不可用，因此本地空 PostgreSQL 的实际 `upgrade head/current` 仍未验证；Draft PR 的 GitHub Actions 已在 PostgreSQL 16/Redis 7.2 service 上成功执行 `alembic upgrade head`、Skill bootstrap 和后端测试。

## API 与事件变化

- 新增 `GET /api/conversations/{id}/messages`，按时间返回群聊/私聊统一历史并检查归属。
- 新增 `GET /api/conversations/{id}/events`：JWT、403 ownership、heartbeat、replay、live delivery、disconnect cleanup。
- Skill API 增加搜索、详情安全元数据、`install`、`enable`、`disable`；旧 subscribe 路由为兼容 alias。
- OTP 内部改为 Redis Lua compare-and-delete；发送失败只删除自己写入的验证码，staging/prod 禁止开发通用码并要求完整短信凭据。
- 后端启动与 CI 会把 canonical YAML Skill 幂等 upsert 到数据库，避免空库 migration 后市场为空。
- 新增 canonical `EventType`/`UserEvent`、`EventPublisher`、EventBus 和 UserEventRepository。
- WebSocket 与 SSE 消费同一 EventBus；业务层不再向第二条 Redis 事件通道重复发布。
- OpenAPI 生成 `frontend/lib/api-types.ts`，CI 检查事件和 Skill 契约漂移。

## 前端变化

- 正式应用位于根 `frontend/`，使用 Next.js 15、React 19、TanStack Query、Zustand、Vitest 和 Playwright。
- typed client 统一 Authorization、错误、会话、消息、私聊、Skill 和首次主会话创建；服务端消息只使用 TanStack Query cache，SSE/REST 不再维护两份真相。
- 登录、会话列表、主群、普通群、私聊、任务/HITL、素材/成果、Skill 市场连接正式 API。
- SSE client 支持流式 frame、delta 聚合、稳定 ID 去重、指数退避、Last-Event-ID、可见连接错误、HITL close 和成果 query invalidation。
- 新增 Skill 详情页，展示版本、校验状态、所需 Agent/MCP/权限和脱敏工作流摘要。
- 新增公开产品页；生产不会自动进入 mock。

## 测试与 CI

新增或强化的测试覆盖：EventBus、UserEvent repository、SSE 鉴权/归属/heartbeat/replay/live cleanup、OTP、Skill 生命周期、消息历史、typed API、共享消息 state、SSE client、Skill route，以及无密钥跨模块 E2E。

无密钥 E2E 串联：dev OTP/JWT → group model/member → Skill match → Task/AgentTask → Redis dispatch → mock AgentResult → EventBus/UserEvent → SSE/前端生成契约。浏览器场景验证产品页、登录、首次主会话、消息提交、Skill 筛选和 mock 模式连接行为。

CI 分为：

- `backend-ci`：Ruff、compileall、mypy、空库 Alembic、pytest，带 PostgreSQL/Redis service。
- `agents-ci`：Ruff、compileall、mypy、imports、Agent pytest、无密钥 handler 契约。
- `frontend-ci`：frozen install、lint、typecheck、Vitest、build、Playwright。
- `contract-ci`：Agent/Skill/MCP/Event/OpenAPI/前端类型一致性。
- `security`：gitleaks、自定义 secrets、pip-audit、pnpm audit。

最终审计将 Next.js 固定到 15.5.21、Vitest 固定到 3.2.7，并通过 pnpm overrides 修复 Vite、PostCSS、brace-expansion 与 js-yaml 的已知漏洞；`pnpm audit --audit-level high` 为零 high/critical。剩余一条 Babel low 公告在 7.x 尚无已发布修复版本。

精确命令和最终计数见 `docs/migration/FINAL_VALIDATION_REPORT.md`。

## 仍未完成或未验证

- 本机 Docker daemon 不可用：未在本机启动 PostgreSQL、Redis、MinIO、Qdrant、LiteLLM mock、全体 Worker/MCP，也未本地实际执行空库 migration。
- 真实模型、阿里云短信、云 OSS、TTS/视频和发布渠道没有公共凭据，未验证。
- Playwright 的真实反诈视频长链路继续 opt-in；普通 PR 使用确定性无密钥 E2E。
- 项目所有者尚未为四个来源仓库提供根许可证；本次只补齐已识别的第三方 notices，未擅自添加项目 LICENSE。

## 风险与下一阶段

1. 在可用 Docker Desktop/Linux 主机运行 Compose 全栈、health/readiness、Worker heartbeat、MCP 和真实 SSE。
2. 用隔离测试账号验证阿里云短信和真实模型 smoke，保持不进入普通 PR 强制 CI。
3. 为 Pydantic v2 旧 `Config` 警告和真实长视频 Playwright 场景建立后续任务。
4. 由仓库所有者确定项目许可证后添加根 `LICENSE`。
