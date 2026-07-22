# haole MAS 迁移矩阵

审计日期：2026-07-21  
目标分支：`codex/haole-mas-consolidation`
唯一主干：`haole_03@14815ee`
参考版本：`haole01@d5f84ab`、`oye-mas@6ff181a`、`haole-agno@43f86e2`

## 决策摘要

- 正式后端只保留 `backend/`，正式 Agent 只保留 `agents/`，不会引入 `src/backend/`、`haole/backend/` 或第二套编排器。
- `haole_03` 的 FastAPI、PostgreSQL/Alembic、Redis Streams、LangGraph、Agent Worker、MCP 和 Skill YAML 是运行基线。
- `oye-mas` 的群成员、@Agent 和 Skill 详情后端增量已经存在于主干；不重复迁移，只补产品状态、安装/启停契约和前端覆盖。
- 正式前端落在根目录 `frontend/`。以与主干 API 最接近、已有登录/群聊/HITL/市场/E2E 的 `oye-mas` 前端为工程底座，迁入 `haole01` 的产品页面与群聊/私聊交互中质量更高且不重复的部分；不保留 legacy 前端。
- `haole-agno` 只提供 EventBus、SSE、OTP 策略和测试思路。保留主干 JWT、短信验证码、WebSocket、Redis、User 模型和 LangGraph，不迁入 Agno、第二套 `src/` 后端或 `create_all` 启动建表。
- 四个仓库都未提供根许可证文件。不会替仓库所有者擅自选择许可证；Hermes 派生文件的 MIT 署名和来源必须保留，并写入 `THIRD_PARTY_NOTICES.md`。

## 模块迁移矩阵

| 来源仓库 | 原始路径 | 功能 | 是否迁移 | 目标路径 | 决策理由 | 测试情况 |
| --- | --- | --- | --- | --- | --- | --- |
| `haole_03` | `backend/app/main.py` | FastAPI 入口、health/readiness、路由装配 | 保留 | `backend/app/main.py` | 唯一后端入口；仅接入统一事件生命周期和 SSE 路由 | 基线待执行；已有 smoke |
| `haole_03` | `backend/app/models/` | User、Conversation、Message、Task、Skill、Artifact、HITL 等正式模型 | 保留并扩展 | `backend/app/models/` | 主干模型和 Alembic 已成体系；禁止第二套实体 | 已有 44 个 backend 测试文件，基线待执行 |
| `haole_03` | `backend/alembic/versions/` | 数据库迁移 | 保留并追加 | 同路径 | 不修改或删除既有 migration；新 Event/Skill 状态只追加 migration | 空库升级待基线验证 |
| `haole_03` | `backend/app/redis_client.py` | Redis 连接 | 保留 | 同路径 | 任务、缓存、EventBus 共用正式 Redis 客户端 | smoke 待执行 |
| `haole_03` | `backend/app/api/auth.py` | 短信 OTP、JWT、refresh、me | 保留并小幅增强 | 同路径及 `backend/app/services/auth/` | 已有 TTL、一次性删除、限流和主 User 模型；只补原子消费/策略/测试，不复制另一套登录 | 当前无专门 auth 测试，必须补齐 |
| `haole_03` | `backend/app/ws/manager.py`、`backend/app/api/ws.py` | WebSocket 与 Redis Pub/Sub | 保留并统一发布入口 | `backend/app/services/event_bus.py`、`backend/app/api/ws.py` | 业务层改用统一 publisher，WS 与 SSE 共用事件模型 | 当前无 WS/EventBus 单测，必须补齐 |
| `haole_03` | `backend/app/schemas/ws.py` | UI 事件类型 | 统一扩展 | `backend/app/schemas/events.py` | 作为 SSE、WS、Redis、前端 TS 的单一契约源 | 新增契约测试和 TS 生成检查 |
| `haole_03` | `backend/app/api/messages.py`、`backend/app/services/send_message_handlers.py` | 消息管线、@Agent、群任务分发 | 保留 | 同路径 | 主干已有单一编排器和 @Agent 短路径 | `test_mention_routing.py`、`test_conversation_members.py` 已存在 |
| `haole_03` | `agents/agents/orchestrator_agent/` | LangGraph 主编排 | 保留 | 同路径 | 唯一调度者；禁止引入 Agno 或第二套编排器 | 现有 backend/agents 测试，基线待执行 |
| `haole_03` | `agents/agents/*_agent/` | 四类 Agent Worker | 保留 | 同路径 | Redis Streams + AgentTask/AgentResult 契约符合目标 | agents 有 17 个测试文件，但 CI 尚未运行 pytest |
| `haole_03` | `agents/agents/_common/protocol.py`、`backend/app/schemas/agent.py` | AgentTask、AgentResult | 保留并做契约校验 | 同路径 | 不新建第二套任务协议；检查两端字段漂移 | 新增 schema parity 测试 |
| `haole_03` | `agents/mcp_servers/` | MCP 工具服务 | 保留 | 同路径 | 正式工具边界；来源仓库实现不替换 | 已有 MCP/backend 测试，基线待执行 |
| `haole_03` | `backend/skills/playbooks/*.yaml` | Skill YAML 契约 | 保留 | 同路径 | 正式可执行 Skill 来源 | 已有 loader/compiler 测试；新增 CI 全量 YAML 校验 |
| `haole_03` | `backend/app/api/skills.py`、`backend/app/models/skill.py` | Skill 列表、详情、订阅 | 扩展 | 同路径 | 在现有模型上增加 installed/enabled/version/permissions/MCP/agent 类型，不执行不可信代码 | 新增安装、启用、禁用、搜索测试 |
| `haole01` | `frontend/components/group-chat.tsx` | 群聊产品交互 | 选择性迁移 | `frontend/components/chat/` | 复用有价值的展示和交互；数据、任务和编排全部改接主干 API/EventBus | 源仓无前端测试，迁移后补 Vitest/Playwright |
| `haole01` | `frontend/components/employee-chat.tsx` | 员工私聊 | 选择性迁移 | `frontend/app/private/[agentId]/`、`frontend/components/chat/` | 与统一消息模型合并，不保留第二套聊天状态 | 源仓无测试，迁移后补私聊测试 |
| `haole01` | `frontend/lib/chat-store.ts`、`frontend/lib/store.ts` | 客户端聊天状态 | 不直接迁移 | `frontend/stores/` | 两套 store 重复且混入 mock 编排；只提取必要 UI 状态 | 用统一 store 测试替代 |
| `haole01` | `frontend/app/website/` | 产品落地页 | 迁移 | `frontend/app/website/` | 主干缺少产品页面，且该模块与业务状态低耦合 | build + 页面 smoke |
| `haole01` | `backend/` | V0/V1 FastAPI、SQLite trace、直接 Anthropic SDK | 不迁移 | — | 与主干后端、编排、数据库、LLM Router 全部重复且违反 LLM/MCP 边界 | 仅作 UI API 语义参考 |
| `oye-mas` | `haole/backend/app/api/conversations.py` | 群成员列表 | 已吸收，无需重复迁移 | `backend/app/api/conversations.py` | 主干已有相同端点和测试 | `test_conversation_members.py` 已存在 |
| `oye-mas` | `haole/backend/app/api/messages.py` | @Agent 解析和短路径 | 已吸收，无需重复迁移 | `backend/app/api/messages.py` | 主干已有 hints 过滤和单 mention 路由 | `test_mention_routing.py` 已存在 |
| `oye-mas` | `haole/backend/app/api/skills.py` | Skill 市场详情 | 已吸收并继续扩展 | `backend/app/api/skills.py` | 主干已有详情端点；补安装/启停状态即可 | 现有 loader 测试 + 新市场 API 测试 |
| `oye-mas` | `haole/frontend/` | 登录、群聊、HITL、市场、素材/成果、Playwright | 迁移为工程底座 | `frontend/` | 与主干 API/实体最接近，且覆盖目标页面；移除 emoji、mock 默认路径和过时 WS 假设 | 源有 4 个 E2E；迁移后补单测、SSE 与 API 错误测试 |
| `oye-mas` | `haole/backend/`、`haole/agents/` | 较早的主干副本 | 不迁移 | — | 质量和功能落后于 `haole_03`，复制会制造重复根目录 | 只用于确认功能已吸收 |
| `haole-agno` | `src/backend/app/services/event_bus.py` | 每用户队列、Redis Pub/Sub、fallback、队列上限、生命周期 | 迁移设计与测试 | `backend/app/services/event_bus.py` | 与主干 WS Redis 机制合并，形成单一发布入口 | 迁移 `test_event_bus.py` 行为并增加 Redis fallback 测试 |
| `haole-agno` | `src/api/streams.py`、`src/infra/stream_registry.py` | SSE 鉴权、归属、heartbeat、Last-Event-ID、重连 | 迁移核心能力 | `backend/app/api/streams.py`、事件存储 | 不迁入单进程 registry 限制；使用统一用户/会话事件流和持久化 replay | 新增 auth/ownership/heartbeat/replay/cancel 测试 |
| `haole-agno` | `src/backend/app/schemas/sse_envelope.py` | SSE envelope | 迁移并简化 | `backend/app/schemas/events.py` | 统一事件模型后生成前端 TypeScript 类型 | 新增 Pydantic/TS 契约测试 |
| `haole-agno` | `src/backend/app/services/auth/otp.py`、`policy.py`、`delivery.py` | OTP 哈希、策略、渠道抽象 | 选择性迁移 | `backend/app/services/auth/` | 保留主干短信/JWT/User，只提取通用策略和原子校验；不迁入邀请/邮箱整套身份模型 | 新增错误码、过期、一次性消费、发送失败测试 |
| `haole-agno` | `src/backend/app/models/ui_event.py` 及相关 migration | 持久化 UI 事件回放 | 迁移等价实现 | `backend/app/models/event.py` + 新 Alembic migration | `Last-Event-ID` 不能只靠进程内 ring；PG 作为短断线 replay 真相源 | 空库 migration + replay 测试 |
| `haole-agno` | `src/frontend/` | SSE 消费、重连和较新的页面实现 | 仅作实现参考 | `frontend/` | 正式 UI 来源仍以 haole01/oye 产品线为准，避免再引入第三套前端 | 参考其 4 个 E2E 场景补覆盖 |
| `haole-agno` | `src/agents/`、`src/teams/`、`src/skills/engine.py` | Agno 编排和进程内 SkillRunner | 不迁移 | — | 会形成第二套主编排、任务系统和直接 LLM SDK 路径 | 仅参考 Event/SSE 事件命名 |
| `haole-agno` | `src/infra/db.py` 的 `create_all` | 启动时建表 | 不迁移 | — | 正式项目只允许 Alembic | 不适用 |
| `haole_03` | `.github/workflows/ci.yml` | 当前 CI | 拆分并强化 | `.github/workflows/` | frontend 可缺失/可 warning、agents 无 pytest、契约和安全检查不足 | 改为 backend/agents/frontend/contract/security 阻断式 job |
| 四仓 | LICENSE/NOTICE | 许可证与归属 | 记录缺失，不伪造许可证 | `THIRD_PARTY_NOTICES.md` | 四仓均未发现根 LICENSE/COPYING/NOTICE；必须提示所有者补充 | 文档检查 |
| Hermes/Nous Research | `backend/app/utils/*`、`agents/agents/_common/think_scrubber.py`、`backend/skills/md_skills/hermes/` | MIT 派生代码 | 保留署名 | 原路径 + `THIRD_PARTY_NOTICES.md` | 已有文件头和来源说明，不得删除 | 现有 Hermes port 测试 |

## 冲突清单

| 类型 | 冲突 | 决策 |
| --- | --- | --- |
| 后端根目录 | `backend/`、`haole/backend/`、`src/backend/`、Agno 根 `src/` | 只保留 `backend/` |
| 前端根目录 | 主干缺失；来源有 `frontend/`、`haole/frontend/`、`src/frontend/` | 最终只保留根 `frontend/` |
| 编排器 | LangGraph 主编排、haole01 conductor、Agno Team/SkillRunner | 只保留 LangGraph 主编排 |
| 任务系统 | Redis Streams AgentTask、Agno asyncio Task、haole01 本地流程 | 只保留 Redis Streams + AgentTask/AgentResult |
| LLM | LiteLLM Router、直接 Anthropic/OpenAI/DashScope | 生产代码只走 LiteLLM Router |
| 事件传输 | 主干 WebSocket `haole.ws`、Agno SSE `haole:sse:*`、进程内 registry | 统一 publisher；底层同时支持 SSE、WS、Redis 与 PG replay |
| OTP/API | `/sms/send` + `/login` 与 `/otp/send` + `/otp/verify` | 保留主干兼容路由；内部统一 OTP 服务，不增加第二套 User |
| Skill 状态 | 订阅/可见性、安装/启用、Agno manifest | 在主干 Skill/UserSkillVisibility 上统一 installed/enabled 元数据 |
| 环境变量 | 主干无前缀、Agno `haole_*`、haole01 `NEXT_PUBLIC_AGENT_SERVER_URL` | 后端沿用主干名；前端统一 `NEXT_PUBLIC_API_URL`，mock 只由显式变量开启 |
| 依赖 | Next 15/16、Zustand 4/5、LangGraph 0.2/1.1、tenacity 8/9 | 后端遵循主干约束；前端按锁文件选单一版本并通过 build/typecheck 验证 |
| 数据模型 | 主干正式模型、Agno 根 `src/domain`/`src/infra/db.py` 模型 | 只扩展主干 SQLAlchemy 模型，并追加 Alembic migration |
| 文档漂移 | README 声称 `frontend/haole_mas_frontend-main/` 存在，实际缺失 | 最终 README 只写实际目录和已验证命令 |

## 当前测试盘点

- `haole_03`：44 个 backend 测试文件、17 个 agents 测试文件、6 个仓库级脚本/测试；当前 CI 不执行 agents pytest。
- `haole01`：21 个 backend 测试文件；frontend 没有单测或 E2E。
- `oye-mas`：29 个 backend 测试文件、4 个 frontend E2E；无独立 agents 测试。
- `haole-agno`：根 Agno 原型 4 个测试文件；演进版 `src/backend` 有 81 个测试文件、`src/frontend` 有 4 个 E2E。
- 上述只是文件盘点，不代表通过；实际基线与最终结果分别记录在 `BASELINE_REPORT.md` 和 `FINAL_VALIDATION_REPORT.md`。
