# 个人单机 5 分钟上手

> 目标:在你的电脑(Mac / Linux / WSL2)跑起来,像普通用户一样跟 7 个 AI 角色聊天,做反诈视频。
>
> **零配置**:默认 `LITELLM_MOCK=true`,所有外部 API 都用本地 mock,**不需要任何 API Key**。
> 想用真模型时,在根目录 `.env` 里填 `OPENROUTER_API_KEY`(等)即可切换。
>
> 只想跑后端 + 自动测试 → 见 [`backend/README.md`](backend/README.md)。

---

## 0. 装 3 个东西

| 工具 | 用途 | 一行装 |
|------|------|------|
| Docker Desktop | 起 postgres / redis / minio / qdrant 容器 | https://www.docker.com/products/docker-desktop/ |
| Python 3.12+ | 跑 backend + 4 Agent + 7 MCP server | `brew install python@3.12` 或 https://www.python.org/ |
| `uv` | Python 包管理(比 pip 快 10×) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `make`(可选) | 一键命令 | macOS / Linux 自带 |

**Windows 用户**:用 WSL2(Ubuntu)更顺,直接命令一致。否则把 `make xxx` 替换成 `Makefile` 里对应的命令逐条跑。

---

## 1. 一次性准备(2 分钟)

```bash
git clone <repo> youle_mas && cd youle_mas

make setup     # 起容器 + 装 Python 依赖 + 跑库 schema
```

`make setup` 干的事:
1. `cp .env.example .env`(若不存在)
2. `docker compose -f backend/infrastructure/docker-compose.yml -f backend/infrastructure/docker-compose.mock.yml up -d` 起 5 个基础容器(postgres / redis / minio / qdrant / litellm-mock)
3. `uv sync` backend + agents 依赖
4. `alembic upgrade head` 建 21 张表

完成后:
- http://localhost:9001 — MinIO 控制台(`minioadmin` / `minioadmin`)
- http://localhost:5432 — Postgres(`youle` / `youle_dev`)
- http://localhost:4000 — LiteLLM mock

---

## 2. 起 12 个 Python 进程(1 行)

```bash
make up
```

实际跑的是:
```bash
honcho start   # 读 Procfile,并发起 backend + 4 Agent + 7 MCP
```

终端会看到 12 行带颜色前缀的日志,例如:
```
12:01:00 backend.1     | INFO     Started uvicorn on :8000
12:01:00 agent_text.1  | INFO     consume_loop started, queue=agent_tasks:text
12:01:00 mcp_search.1  | INFO     stdio mcp server ready
...
```

**全部 ready 后**:
- http://localhost:8000/docs — backend Swagger UI(API 总入口)
- 等前端入仓后:http://localhost:3000 — 用户对话界面

**Ctrl+C** 一次性停所有 Python 进程。容器还在跑,`make down` 才停容器。

---

## 3. 跑一次反诈视频(看是否真能产出视频)

新开一个终端(让 `make up` 继续在另一个终端跑着):

```bash
make demo-anti-fraud
```

这会触发一个端到端 workflow:
1. 主编排 8 子模块解析"做个 2026 年针对都市老人的电信诈骗反诈视频"
2. Agent 1 web_search → 调研 → long_writing → 脚本
3. Agent 3 batch_generate → 5 张配图
4. Agent 4 tts_generate → 配音 → bgm_select → 配乐 → video_compose → mp4
5. 3 个 HITL gate(脚本审 / 画面审 / 终审)在 demo 里默认自动通过(`YOULE_AUTO_APPROVE_HITL=true`)

预期最后看到:
```
[demo] final_artifact_ref: oss://youle-dev/anti-fraud-video/<task_id>/final.mp4
[demo] ✓ 反诈视频 happy path 跑通
```

打开 MinIO 控制台 http://localhost:9001 → bucket `youle-dev` → 找到 mp4 下载查看。

> ⚠️ mock 模式下 `mp4` 是 0 字节占位 — 验证的是流水线**通**,不是产物质量。要真产出,看 §5。

---

## 4. 跟 AI 团队真对话(等前端 push 后)

**你已经把 `youle_mas_frontend-main` 准备在本地了**,只差 push 到 GitHub。push 后:

```bash
# 取消 Procfile 里 frontend: 那行的注释
# 重新跑
make up
```

打开 http://localhost:3000:
1. 看 3 个角色(总裁助理 / HR / 财务经理)依次入群
2. 选模式(Plan / Ask / Auto)
3. 在群里说"做个反诈视频"
4. 经过澄清 + 3 个 HITL gate,拿到产物

---

## 5. 接真 API(从 mock 切真模型)

`.env` 改 4 行:

```ini
LITELLM_MOCK=false
OPENROUTER_API_KEY=sk-or-v1-xxxx       # https://openrouter.ai/keys
TAVILY_API_KEY=tvly-xxxx                # https://tavily.com/
VOLCENGINE_TTS_APP_ID=xxxx              # 火山引擎 TTS(可选,缺了用占位音频)
VOLCENGINE_TTS_TOKEN=xxxx
```

OpenRouter 一个 key 涵盖 GPT-5 / Claude / DeepSeek / Kimi / Veo 等所有项目用到的模型,5 美元起充。

重启 `make up` → 这次反诈视频会用真模型,产物是真 mp4,大概 30 秒生成完。

---

## 6. 常用命令

```bash
make help         # 列所有命令
make ps           # 看容器状态
make logs         # 跟容器日志
make test         # 跑全部 200 unit + 4 smoke 测试
make shell-db     # 进 postgres 命令行
make shell-redis  # 进 redis-cli
make down         # 停容器(数据保留)
make clean        # 停容器 + 清数据卷(全新环境)
```

---

## 7. 排错速查

| 现象 | 原因 / 解决 |
|------|----------|
| `make setup` 卡在容器 healthy | Docker Desktop 没起 / WSL 内存不够;`docker compose ps` 看哪个 unhealthy,`docker logs <container>` 看日志 |
| `make up` honcho 找不到 | `uv tool install honcho` 显式装 |
| backend 启动报 `db connection refused` | 容器没起完;`make ps` 看 postgres 是否 healthy,如不是先 `make setup-infra` |
| `alembic upgrade head` 报 schema 冲突 | `make clean && make setup` 全新建 |
| 反诈视频 demo 卡在 step | 看 honcho 的 `agent_av` / `mcp_video` 日志,通常是 mock 模式下某 step 期望真模型返回但 mock 返了占位 |
| 想看 LangGraph 中间状态 | http://localhost:8000/api/tasks/{task_id}/history — checkpoint 历史 |

---

## 8. 项目铁律(玩之前看一眼)

- **22 条铁律 + 12 条 ADR**:见根目录 [`CLAUDE.md`](CLAUDE.md)
- 主编排是单一调度者,Agent 之间不互相 @
- LLM 走 LiteLLM,工具走 MCP,不直 import openai/anthropic
- HITL 三 gate(脚本 / 画面 / 终审)在 hero 任务上必开

如果你只想"用",不写代码,跳过这条没事。

---

## 9. 下一步

- 想看架构? → `架构文档/0_总览/`
- 想加新 Skill? → `backend/skills/playbooks/anti_fraud_video.yaml` 是最好的样板
- 想发新 PR? → `.github/PULL_REQUEST_TEMPLATE.md` 已就位
- 真生产部署?→ V1-P1 才上(K8s / Grafana / Sentry 等暂不做)

**Have fun!**
