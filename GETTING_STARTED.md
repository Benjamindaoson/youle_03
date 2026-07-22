# 低成本本地启动

默认核心模式只启动两个容器和三个应用进程：

- PostgreSQL、Redis
- FastAPI、合并 Agent worker、Next.js

它使用 `LITELLM_MOCK=true`，不调用外部模型，适合验证完整的前端 → 后端 → LangGraph → Agent → HITL → 成果链路。

## Windows

在仓库根目录执行：

```powershell
.\scripts\core.ps1 setup
.\scripts\core.ps1 start
```

脚本会创建项目自己的 `.venv`、安装锁定依赖、执行 Alembic、启动服务，并打印实际 URL。后端默认从 `8001` 开始寻找空闲端口；前端默认从 `3000` 开始寻找空闲端口，因此不会终止或覆盖电脑上的其他服务。

查看状态和日志：

```powershell
.\scripts\core.ps1 status
Get-Content .runtime\backend.error.log -Wait
Get-Content .runtime\frontend.log -Wait
```

只停止本项目记录的三个应用进程：

```powershell
.\scripts\core.ps1 stop
docker compose -f compose.core.yml down
```

## macOS / Linux / WSL

```bash
cp .env.example .env
make setup
make up
```

`make up` 读取根目录 `Procfile`。按 `Ctrl+C` 停止三个应用进程，`make infra-down` 停止两个容器。

## 登录与验收

本地开发验证码为 `123456`。登录后新建 Auto 群并发送一个完整请求，例如：

```text
做一个短视频；主题：城市夜跑；风格：纪实；受众：上班族；时长：30秒；平台：小红书；开头钩子：下班后别急着回家
```

依次通过三个审核卡片。完成后，聊天区会显示成果引用，成果库会显示任务产物。Mock 模式不会生成可播放的真实视频文件，它验证的是编排、接口、状态、审核和成果落库链路，外部模型调用次数为 0。

## 接入真实 API

`scripts/core.ps1` 是零费用验收入口，会强制 `LITELLM_MOCK=true`；单独修改 `.env` 不会把核心 Demo 静默切到付费模式。核心 Demo 验收后，使用 `deploy/production/` 的独立 Worker/模型路由配置并显式设置：

```dotenv
LITELLM_MOCK=false
LITELLM_URL=https://your-litellm.example
LITELLM_API_KEY=...
STEP_PERSONA_MAX_BUDGET_TOKENS=8000
AGENT_REACT_MAX_STEPS=6
```

模型密钥只配置在服务端，绝不能使用 `NEXT_PUBLIC_*`。每个动态步骤还可通过 `_planner.budget_tokens` 设置更低 token 预算，运行时会被上述硬上限裁剪；ReAct 单步循环由 `AGENT_REACT_MAX_STEPS` 限制模型/工具轮次。生产基础设施、独立 Worker、MCP、MinIO、Qdrant 和 Kubernetes 配置见 `deploy/production/README.md`；它们不是本地核心模式的前置条件。

## 常见问题

- `\.venv\Scripts\python.exe` 不存在：你位于错误目录或还没执行 `core.ps1 setup`。
- 找不到 `frontend`：确认当前目录包含 `backend/`、`agents/`、`frontend/`，不要在 GitHub 页面名称目录中猜路径。
- PostgreSQL/Redis 端口占用：停止旧的本项目容器，或调整 `compose.core.yml` 端口和 `.env` 连接串。
- 后端启动失败：先查看 `.runtime/backend.error.log`；Windows 必须在 `backend/` 目录运行 `python -m app.run`，它为 psycopg 选择兼容的事件循环。
- 前端运行时突然出现 `/_next/static/*` 404：不要在 `next dev` 运行期间执行 `pnpm build`（两者共用 `.next`）；执行 `core.ps1 stop`、完成构建后再 `core.ps1 start`。
