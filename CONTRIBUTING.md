# 贡献指南

`haole-mas` 只维护一套正式后端、编排器、任务契约和前端。贡献的首要目标是保持这些边界清晰，而不是把来源仓库的旧实现重新复制进来。

## 开发环境

```powershell
git checkout -b feat/<short-name>
Copy-Item .env.example .env
uv sync --locked --all-packages --all-extras
Set-Location frontend
pnpm install --frozen-lockfile
```

Python 项目依赖必须安装在仓库根 `.venv`，不要写入全局 Python。前端使用 `frontend/pnpm-lock.yaml` 和 `pnpm@9.15.9`。

## 架构边界

- 后端入口只在 `backend/app`；不要新增 `src/backend`、`haole/backend` 或运行时 `create_all`。
- 主编排只使用 `agents/agents/orchestrator_agent` 的 LangGraph 路径。
- Worker 之间不直接调用；任务通过 Redis Streams 和 `AgentTask`/`AgentResult` 传递。
- Agent 不直接导入 OpenAI、Anthropic 等供应商 SDK；模型请求通过统一 Router/LiteLLM。
- 工具能力通过 MCP URI 和白名单访问。
- 可执行 Skill 以 `backend/skills/playbooks/*.yaml` 为事实来源；启动/CI 通过 `backend/scripts/bootstrap-skills.py` 幂等同步，市场元数据不得执行不可信代码。
- 业务事件通过 `event_publisher.publish_user_event` 发布；不要再创建独立广播总线。
- 数据模型变更只能追加 Alembic revision，不修改已发布 migration。
- 前端不执行 Agent 编排；生产请求失败不得静默退回 mock。
- 前端服务端消息只存放在 TanStack Query cache；Zustand 只保留会话交互状态，避免 REST 回填覆盖 SSE 增量。

## 规格与实现

较大的功能先在 `openspec/changes/` 记录目标、验收标准和接口变化。实现采用小提交，每个提交包含对应测试。修 bug 时先写能复现问题的测试，再做最小修复。

如果修改 API 或事件 Schema：

1. 更新 Pydantic/路由契约。
2. 启动后端并运行 `frontend` 的 `pnpm gen:api`。
3. 不手写重复的 Event/Skill TypeScript 联合类型。
4. 运行 `backend/scripts/check-contracts.py`。

## 必跑检查

后端和 Agent：

```powershell
.\.venv\Scripts\ruff.exe check backend agents
.\.venv\Scripts\python.exe -m compileall -q backend/app agents/agents agents/mcp_servers
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m pytest agents/tests test/test_agent_task_handlers.py -q
.\.venv\Scripts\python.exe backend/scripts/check-contracts.py
```

前端：

```powershell
Set-Location frontend
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm test:e2e
```

数据库变更还必须在空 PostgreSQL 数据库执行：

```powershell
Push-Location backend
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\alembic.exe current
Pop-Location
```

不能运行某项检查时，在 PR 中写明命令、错误和环境阻塞，不得写成已通过。

## 安全与配置

- 不提交 `.env`、令牌、短信/OSS/模型真实密钥或用户数据。
- 新变量同时更新 `.env.example` 和 README。
- `JWT_SECRET`、数据库密码和 mock key 的示例值只允许在开发环境。
- 避免在日志中输出 OTP、完整手机号、Authorization header、prompt 私密内容和对象存储签名 URL。
- 新依赖需要说明理由，并通过 `pip-audit`/`pnpm audit`。

## Pull Request

PR 应包含：范围、架构决策、Schema/migration、测试命令与结果、已知限制和后续工作。保持 Draft 直到阻断式 CI 全绿；不要在任务分支中合并默认分支，也不要删除第三方文件头或归属信息。
