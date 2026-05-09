# CLAUDE.md(项目根目录)

> **使用方式**:复制本文件到目标仓库根目录,改名 `CLAUDE.md`。Claude Code / Cursor 会自动加载。
>
> 配套阅读(出现具体问题再查):
> - **架构展开**:`docs/ARCHITECTURE.md` ← [启动配套/ARCHITECTURE.md](启动配套/ARCHITECTURE.md)
> - **治理与 ADR**:`docs/CONSTITUTION.md` ← [启动配套/CONSTITUTION.md](启动配套/CONSTITUTION.md)
> - **产品验收清单**:`docs/0_总览/youle_产品功能清单_v4.xlsx`(370 项,**功能契约**)
> - **业务细节**:`docs/3_决策记录/` 与 `docs/4_附录/` 等
>
> **版本**:v3.1(对齐功能清单 v4 — 370 项;ADR-001-rev / 013 / 014 / 015 / 016)

---

## 1. 项目是什么

「有了」= **你的专属 AI 工作团队**(第一期重点:内容引流 + 营销)。

用户对一个微信式群聊里的 AI 团队下达需求 → 总裁助理(主编排 Agent)调度 **7 个 AI 角色** → 一次到位交付完整成品。

**7 个 AI 角色**:

| 类型 | 角色 |
|------|------|
| 主编排 | 总裁助理 |
| 4 个分任务 Agent | Agent 1 文字 / Agent 2 文档 / Agent 3 图 / Agent 4 影音 |
| 2 个支持 Agent(常驻主会话)| HR(管团队)/ 财务经理(管账)|

**V1 上线 2 个 Skill**:
- 反诈视频制作(hero)
- 电商详情图制作

### 1.1 首次进入"专属 AI 工作团队"群(V1 必做)

新用户注册后**自动进入主会话群**(类似微信群),依次显示:

```
[14:00] 总裁助理 加入群聊
[14:00] HR 加入群聊
[14:00] 财务经理 加入群聊

[14:01] 总裁助理:你好,我是你的总裁助理,平时帮你协调任务、调度团队。
[14:01] HR:我管理你的 AI 团队成员,以后想加新员工或给员工进修,找我。
[14:01] 财务经理:订阅、配额、账单都归我。预算紧张时我会提醒你。

[14:02] 总裁助理:你想以哪种模式开始工作?
        [💭 讨论模式 Plan]  [❓ 询问模式 Ask]  [🚀 自动模式 Auto]
        [简单了解每种模式]
```

**不做传统 onboarding tour**——用户直接对话上手。

**3 种工作模式**(同群内可切换):Plan(讨论)/ Ask(询问)/ Auto(自动)

---

## 2. 必须遵守的 22 条铁律(违反一条即 reject)

1. **单一调度者**:Agent 之间不互相 @ / 不直连 / 不跨调
2. **Agent 编号锁定 v3.0(ADR-001-rev)**:**1=文字 / 2=文档 / 3=图 / 4=影音**;队列 `agent_tasks:text|document|image|av`
3. **跨能力步骤显式拆步**:在 Skill YAML 里加 step,不在 handler 里跨调
4. **State 用引用**:产物落 OSS,state 只存 `artifact_id + reference URL`
5. **长任务异步**:视频合成走 Celery,Agent 立即返回 `pending_external`
6. **永远选择题**:澄清 ≤ 5 轮,每字段必有 default
7. **LLM 走 LiteLLM**:禁止 `import openai/anthropic` 调模型
8. **Prompt 不内联**:从 `app/config/prompts.py` 引用
9. **Skill YAML 是契约**:行为变更 = YAML 改 + version bump
10. **对话优先按钮**:建群/改群/订阅 走总裁助理对话
11. **不为 V2 写代码**:V2 范围接口预留即可
12. **失败 3 层兜底**:重试 → 备用模型 → 用户介入
13. **MCP 是工具集成唯一标准**:工具走 MCP server,Agent 是 MCP client
14. **Hero 交付有 HITL gate**:Auto 模式视频任务 3 道 gate(脚本审/画面审/终审);**V1 终审支持"接受/微调/取消",回滚到任意 step(中断 C)推迟 V2**
15. **数据飞轮 4 类信号必沉淀**:工作流轨迹 / 偏好向量 / Reflexion / Skill 草稿
16. **V1 hero 锁定**(ADR-012 已废)**:反诈视频 + 电商详情图**,其他场景 V1.5 通过 Skill 市场补齐
17. **三模式同群内切换**(ADR-014):**不建讨论群/工作群两种独立群**;群内 work_mode 字段切 plan/ask/auto
18. **HR / 财务经理仅在主会话**(ADR-013):不进入其他群;不消费 agent_tasks 队列
19. **拟人化 V1 必做**(ADR-015):20 组表情 + 4 种工作状态 + Agent 互动消息(由主编排互动编排器统一编排);**严肃场景(金融/医疗/政务)关闭表情**
20. **Plan / Ask 模式不消耗任务配额**(v4 #121/#124):**只算 token,不算任务**;Auto 模式才扣任务配额
21. **9 类中断 V1 必做 7 类**:A(补充信息)/ B(微调当前)/ E(暂停)/ F(取消)/ G(闲聊)/ H(反馈)/ **I(用户主动切换模式,v4 新增)**;C(回滚)/ D(改方向)推迟 V2
22. **主编排 8 子模块**(对齐 v4 #50-57):意图理解 / **模式管理器** / Skill 匹配 / 输入校验 / 澄清生成 / 任务编排(含 HITL gate 实现)/ 中断处理 / **互动编排器**

详细 ADR 解释见 [CONSTITUTION.md](启动配套/CONSTITUTION.md)。

---

## 3. 代码模式黑名单(看到立即 reject)

任何 PR 出现以下模式 → 立刻 stop,要求修改:

```
# 模型调用
import openai                          → 必须 from app.router import complete
import anthropic                       → 同上
from openai import                     → 同上
client = OpenAI(                       → 同上

# HTTP / 网络
import requests                        → 必须用 httpx async
requests.get / requests.post           → 同上

# 日志
print(                                 → 必须用 structlog,带 task_id/user_id
logging.info / logging.error           → 改用 structlog

# 异常
except:\n    pass                      → 必须显式 log + 决定 retry/fail
except Exception:\n    pass            → 同上

# Agent 跨调
call_other_agent(                      → 永久 NotImplementedError(ADR-002)
agent_X.handlers.YYY(                  → 跨 Agent 直接 import handler 禁止

# Prompt 字面量
"""你是.*?\n.{50,}"""                  → 长 prompt 必须移到 app/config/prompts.py
f"你是 {role}, 请..."                  → 同上(超过 50 字)

# Secrets / 凭证
api_key = "sk-...                      → K8s Secret + env,绝不进代码
password = "                           → 同上

# SQL
db.execute(f"SELECT ... {var}")        → 必须 SQLAlchemy 参数化
db.execute("..." + user_input + "...") → 同上

# State
state.artifacts[i].full_content        → 必须存 reference,加载时按需读 OSS
state["large_text"] = "X" * 10000      → 同上

# Agent 通信
httpx.post("http://agent_X/...")       → 必须 Redis Streams + AgentTask
grpc / RPC 直连 Agent                   → 同上

# Agent ID 编号(v3.0 ADR-001-rev)
AGENT_QUEUE_MAP["agent_2"] = ":image"  → 必须 ":document"(v3.0)
AGENT_QUEUE_MAP["agent_3"] = ":av"     → 必须 ":image"(v3.0)
AGENT_QUEUE_MAP["agent_4"] = ":document" → 必须 ":av"(v3.0)
代码里的 agent_id 映射必须按 ADR-001-rev:
  agent_1 → text
  agent_2 → document
  agent_3 → image
  agent_4 → av

# 模式管理(v3.0 ADR-014,对齐 v4)
parent_conversation_id 列                → 已废弃,使用 work_mode 字段
conversation_links 表                    → 已 drop
"derive-work-group" / "back-to-discuss" API → 改用 "switch-work-mode"
mode_switch_log 表                       → v4 命名为 `mode_history`(统一)
ContextPool 表                           → v4 已删除,Brief 直接挂 conversations.brief 字段

# Skill
hardcoded skill steps in Python        → 必须 Skill YAML

# Frontend
fetch('/api/...').then(res => res.json) → 必须 TanStack Query
emoji 字符 / icon                       → 用 lucide-react

# TODO
# TODO: 之后做                          → 必须有 issue 链接 # TODO(#123): xxx
```

**Claude Code 拿到任何代码,先 grep 这些模式,命中即 stop**。

---

## 4. 每 Sprint 的 Acceptance Criteria(完成判定)

### Sprint 0:基础设施(目标 1 周)

完成 = 满足以下全部:

- ✓ `docker-compose up` 一键起 postgres/redis/minio/litellm-mock/qdrant
- ✓ `alembic upgrade head` 跑通 18 张表 schema
- ✓ `pytest tests/smoke/test_infra.py` 全绿(连得上 db / redis / minio)
- ✓ `app/router.py` 调用 mock LiteLLM 返回固定文本
- ✓ `POST /api/auth/sms/send` 在 dev 模式下打印验证码到 console
- ✓ WebSocket `/ws?token=xxx` 能 echo

### Sprint 1:MCP servers(1 周)

- ✓ `mcp_servers/search` stdio 启动,`pytest tests/mcp/` 全绿
- ✓ `mcp_servers/oss` 上传/下载/签名 URL 跑通(走 MinIO)
- ✓ Agent 1 通过 `mcp_client.call_tool("search", "web_search", ...)` 得到 mock 结果
- ✓ 7 个 MCP server 至少有 happy path test(其他可 mock)

### Sprint 2:主编排框架(1.5 周)

- ✓ **8 个子模块**(对齐 v4)各自有 1 个端到端 unit test:意图理解 / 模式管理器 / Skill 匹配 / 输入校验 / 澄清生成 / 任务编排 / 中断处理 / 互动编排器
- ✓ `app/config/prompts.py` 加载所有 prompt(从文档拷贝),含 HR_SYSTEM_PROMPT / FINANCE_SYSTEM_PROMPT
- ✓ 意图理解器 → Skill 匹配 → 输入校验 端到端跑通(用 mock LLM)
- ✓ 模式管理器:plan/ask/auto 派发 + 切换识别(中断 I 类)
- ✓ 中断处理器:7 类中断(A/B/E/F/G/H/I)分类 + handler;C/D 抛 NotImplementedError(V2)
- ✓ `pytest tests/orchestrator/` 全绿,coverage > 60%

### Sprint 3:Agent 框架 + 反诈视频 happy path(1.5 周)

- ✓ 4 个 Agent main.py 启动,消费各自队列(按 ADR-001-rev 映射:agent_2→document, agent_3→image, agent_4→av)
- ✓ Agent 1 `web_search` + `long_writing` happy path(反诈视频调研 + 脚本)
- ✓ Agent 3 `image_download` happy path(从 xlsx 下载图片)
- ✓ Agent 4 `tts_generate` + `bgm_select` happy path
- ✓ 端到端:用户消息 → 主编排 → Agent 派活 → 拿到产物(全 mock)

### Sprint 4:Skill + HITL + 飞轮 + 三模式(1 周)

- ✓ `skills/anti_fraud_video.yaml` 编译为 LangGraph,缓存到 Redis
- ✓ `skills/ecommerce_detail_image.yaml` 同上
- ✓ HITL gate 后端(任务编排器内实现):开 gate → 暂停 LangGraph → 等用户响应 → 推进
- ✓ HITL 终审支持 V1 操作:[接受] / [微调当前](中断 B)/ [取消](中断 F);**[回到第 N 步重做] 推迟 V2**(中断 C)
- ✓ `flywheel.py` 4 类信号沉淀(用本地 fake Qdrant)
- ✓ 三模式管理器:Plan / Ask / Auto 同群切换;**Plan/Ask 不扣任务配额,只扣 token**
- ✓ Brief 直接挂 conversations.brief JSONB(无 ContextPool 表)
- ✓ `mode_history` 表写入模式切换日志
- ✓ 中断 I 实现:用户说"开干"/"等等想想"/"问个问题" → 自动切模式
- ✓ HR / 财务经理 主会话 system prompt 接入

### Sprint 5:前端(2 周)

- ✓ Next.js 15 + Tailwind + shadcn 跑通,3 栏布局
- ✓ 左栏顶部:用户头像 + 知识库 + 成果库(ADR-016 简化,**取消通讯录等多余入口**)
- ✓ 左栏中部:聊天 / AI 学院 / 技能市场;素材库改为聊天里 @ 调用(不在左栏单独显示)
- ✓ WS 客户端自动重连,事件路由到 Zustand store
- ✓ **首次进入流程**:总裁助理 → HR → 财务经理 依次入群动画 + 3 段自我介绍 + 模式选择卡片
- ✓ 群聊页 + 右栏执行流流式渲染(**Auto 模式自动展开,Plan/Ask 默认折叠**)
- ✓ 群顶部模式切换 chip(Plan/Ask/Auto)+ 当前模式标识
- ✓ 群成员栏:主会话 7 个角色 / 普通群 5 个角色 + 工作状态显示(工作中/发呆中/摸鱼中)
- ✓ 表情系统:每 Agent 20 组表情,关键节点出现;**严肃场景(金融/医疗)关闭表情**
- ✓ Agent 互动消息样式:与正常消息一致(由互动编排器生成,V1 克制不每步演戏)
- ✓ 3 个 HITL 审核组件(脚本审/画面审/终审)— V1 终审仅 [接受][微调][取消],**无回滚按钮**(中断 C 是 V2)
- ✓ Playwright E2E:登录 → 主会话选模式 → 建反诈视频群 → HITL 全过 → 拿到 mp4

### Sprint 6:联调 + 上线(1 周)

- ✓ 真实 LiteLLM + 真 Tavily / volcengine / 阿里云 OSS 跑通
- ✓ K8s manifest 部署到 staging
- ✓ Grafana 大盘上线:意图理解延迟 / Agent 队列积压 / 视频任务成功率 / Agent 状态分布
- ✓ E2E 跑 10 次反诈视频任务 + 5 次电商详情图任务,全绿

**判定原则**:Sprint 不达成 acceptance,**不开始下个 Sprint**。

---

## 5. Mocking + Local-first 策略

### 启动顺序优先级

1. **本地 mock 优先**(Sprint 0-3 全 mock)
2. **Sprint 4 开始接真 API**(分 task_type 灰度)
3. **Sprint 6 才真实部署**

### Mock 实现

| 真服务 | Mock 实现 | 何时切真 |
|-------|---------|---------|
| LiteLLM Proxy | 启动 `mock-litellm` 容器,任何 model 返回固定 JSON 文本 | Sprint 4 |
| OSS | MinIO 容器(已在 docker-compose) | dev / staging 用 MinIO,prod 切阿里云 |
| 短信验证码 | dev 模式直接 console.log "code: 123456" | staging |
| MCP search | 返回固定 3 条 fake results | Sprint 5 接 Tavily |
| 图像生成 | 返回 OSS 里预置的占位 png | Sprint 4 接 GPT-Image-2 |
| Veo-3 / Seedance | 返回预置 sample mp4 | Sprint 5 末 |
| Volcengine TTS | 返回预置 sample mp3 | Sprint 4 |
| Qdrant | docker-compose 起本地 Qdrant | 一直用 |

### 切换机制

```python
# app/config/settings.py
ENV: Literal["dev", "staging", "prod"] = "dev"

# 服务工厂
def get_litellm_client():
    if ENV == "dev":
        return MockLiteLLMClient()
    return LiteLLMProxyClient(url=settings.LITELLM_URL)
```

**未配 mock 不允许接真 API**——Claude Code 看到 PR 直接接真 API(没有 mock fallback),要 reject。

---

## 6. Git / PR Workflow

### 分支规范

- `main`:protected,只接 PR
- `sprint/{N}-{name}`:每个 Sprint 一个 branch,如 `sprint/3-agent-framework`
- `feat/{ticket}-{name}`:子任务分支(从 sprint branch 切)

### Commit 粒度

- 一个文件 / 一个逻辑改动 = 一个 commit
- commit message 格式:`[Sprint N] <type>: <一句话>`
  - type: `feat | fix | docs | test | refactor | chore | adr`
  - 例:`[Sprint 3] feat: agent 1 short_video_script handler happy path`
- **每个 commit 之前自检**:
  - `ruff check .` 通过
  - `mypy app/` 通过
  - 不命中代码模式黑名单(§3)
  - 至少 1 个 happy case test

### PR 规则

- Sprint 完成 → 开 PR,等用户 review
- PR 模板包含:
  - 改了什么(对应 ADR / Skill / Sprint)
  - acceptance criteria 哪些满足了
  - 怎么验证(命令 / 截图)
  - 飞轮信号沉淀点 / HITL gate 检查
- **不允许**:`git push --force` 到 main / `git reset --hard` 没确认 / merge 不通过 CI 的 PR

---

## 7. 协作交互指令(Claude Code 何时停下来问用户)

### 必须停下来问

1. **Sprint 完成后**:列出 acceptance 验证步骤,等用户跑过再开下个 Sprint
2. **删除 / 重构 > 50 行**现有代码:解释意图先问
3. **引入 §3.1 没列的依赖**:必须问
4. **ADR 范围外的架构选择**:必须问(包括偏离 16 条铁律)
5. **API 设计偏离 docs/ARCHITECTURE.md spec**:必须问
6. **跑生产命令**(deploy / migrate prod / rm -rf):必须问 + 二次确认
7. **修 prompt**(`app/config/prompts.py`):必须更新对应回归测试 yaml,然后问
8. **改 ADR**:绝对不允许,必须先开讨论 issue

### 不需要问(放手做)

- 写新代码、加测试、修非破坏性 bug
- 添加文档注释 / docstring
- 命名 / 风格调整(符合 ruff)
- 在 Sprint 范围内推进
- 修自己刚写的代码(还没 commit)

### 沟通模板

完成一个工作单元时输出:

```
✅ 完成:<什么>
📍 涉及:<文件清单>
🔧 验证:<跑什么命令 / 看什么效果>
⚠️ 需要确认:<如果有>

下一步建议:<继续什么>(等你说"继续"再做)
```

---

## 8. V1 内部分级:P0 vs P1

V1 不是一锅炖。先跑通 P0,再做 P1。

### V1-P0(8 周内必须,对齐 v4 350 项)

- 主编排 **8 子模块**(意图理解 / 模式管理 / Skill 匹配 / 输入校验 / 澄清生成 / 任务编排 / 中断处理 / 互动编排器)
- 4 个分任务 Agent + 各 1 个 happy path handler(按 ADR-001-rev 编号)
- 2 个支持 Agent(HR / 财务经理)接入主会话
- 反诈视频 Skill 端到端 + 3 个 HITL gate(V1 不含中断 C 回滚)
- 电商详情图 Skill 端到端
- 7 个 MCP server(可只是 happy path)
- 数据飞轮 4 类信号沉淀
- 三模式同群切换(Plan/Ask/Auto + 中断 I 用户主动切换)
- Plan/Ask 不消耗任务配额,Auto 消耗
- 7 类中断 V1 必做(A/B/E/F/G/H/I)
- 拟人化 V1 必做(20 组表情 + 4 状态 + 互动消息;严肃场景关闭表情)
- 前端三栏 + HITL 审核组件 + 模式切换 chip + 7 角色群成员栏
- 首次进入流程(3 角色依次入群 + 模式选择)
- 左栏简化(知识库/成果库提顶,取消通讯录)
- Docker Compose dev 起来跑通

### V1-P1(3 个月内)

- 配额体系完整实现(免费 / 创作者 / 专业版)
- Reflexion / Skill Drafter pipeline 真跑起来
- K8s 生产部署
- 监控大盘 + 告警

### V1-P2(6 个月内)

- 离线继续运行优化
- 跨群消息搜索
- 偏好画像可视化(前端)
- BGM 素材库扩充

### V1.5 推迟范围(对齐 v4)

- **PPT 整体能力**(Skill 与 Agent 2 PPT handler 复杂度高,V1.5 上线)
- **视频生成模型**(Veo / Seedance / Kling-2,V1 反诈视频用 image-to-video 拼接,不调文生视频)
- **Agent 3 高级图像编辑**(局部重绘 / 扩图 / 抠图 / 画质增强)
- **PDF 高级功能**(PDF 生成 / 加水印 / 扫描 OCR 全套)
- **Agent 1 长文写作**(公众号长文 / 报告)
- **跨 Agent 调用走队列**(V1 PPT 不上线,V1.5 才需要)
- **平台发布 API 集成**(抖音 / 视频号 / 小红书发布)
- **语音消息**(转文字)

### V2 推迟范围

- 中断 C(修改参数,触发依赖图回滚)
- 中断 D(改方向,fork 新任务)
- Skill 创作流(用户自动总结 Skill)
- Agent 进修(语料 + 微调)
- 创作者分润机制
- 多人协作群
- [做同款] / [加入此团队] 一键复刻按钮
- HR 引导成为创作者 / Agent 进修

**判断**:Claude Code 写代码时,先看是否在 P0 范围内,P1/P2 留接口。

---

## 9. 跨语言 Schema 同步

后端(Python / Pydantic)+ 前端(TypeScript)+ MCP server(可能是 TypeScript)的类型必须对齐。

### 方案

- **后端是源**:Pydantic 模型在 `backend/app/schemas/`
- **生成 OpenAPI**:FastAPI 自动 `/openapi.json`
- **前端生成**:`pnpm gen:api` 跑 `openapi-typescript` 生成 `frontend/lib/api-types.ts`
- **MCP server schema**:用 `mcp.types` Python SDK 自动生成 JSON Schema(MCP 协议自带)

### 关键共享类型

| 类型 | Python 路径 | TS 路径 |
|------|-----------|--------|
| `AgentTask` | `app.schemas.agent.AgentTask` | `lib/api-types.ts` 自动生成 |
| `Conversation` | `app.schemas.conversation.Conversation` | 同上 |
| `Message` | `app.schemas.message.Message` | 同上 |
| `WSEvent` 联合 | `app.schemas.ws.WSEvent` | `lib/ws-events.ts`(手写,因为 OpenAPI 不覆盖 WS) |
| `HITLGate` | `app.schemas.hitl.HITLGate` | 自动生成 |

### CI 强制

PR 修改 `schemas/` 必须重跑 `pnpm gen:api` 并 commit 生成的 ts 文件。否则 CI fail。

---

## 10. 起步路径(Sprint 总览)

| Sprint | 主题 | 周数 | acceptance 见 §4 |
|--------|------|-----|------|
| 0 | 基础设施 | 1 | §4.0 |
| 1 | MCP servers | 1 | §4.1 |
| 2 | 主编排 8 子模块 | 1.5 | §4.2 |
| 3 | Agent 框架 + 短视频 happy path | 1.5 | §4.3 |
| 4 | Skill + HITL + 飞轮 | 1 | §4.4 |
| 5 | 前端 | 2 | §4.5 |
| 6 | 联调 + 上线 | 1 | §4.6 |

**总 8 周到 V1-P0**。

---

## 11. 收到任务前必答的 9 个问题

每个新任务 / PR / 子工作单元开始前,自问 :

1. 这个改动违反 §2 的 **22 条铁律**哪一条吗?(违反 → 改方案)
2. 触发 §3 代码模式黑名单吗?(触发 → 重写)
3. 属于 **V1-P0 / P1 / P2 / V1.5 / V2** 范围?(V1.5/V2 → 留接口不实现)
4. 改 Skill YAML / MCP server / Python 代码?(优先 YAML > MCP > Python)
5. 产生了哪 4 类飞轮信号?(没有 → 加上 hook)
6. Hero 任务有 HITL gate 吗?(没有 → 加上;**注意 V1 不做回滚按钮 = 中断 C**)
7. 需要先 stop 问用户(§7)吗?
8. **(v4 新)** 涉及配额吗?Plan/Ask 必须 **不扣任务配额**,只扣 token
9. **(v4 新)** 涉及 Agent 角色显示?**主会话 7 角色**,**普通群 5 角色**(无 HR / 财务经理)

---

## 12. 配套文档

不在本文,详细看:

- **架构展开** → [docs/ARCHITECTURE.md](启动配套/ARCHITECTURE.md)(技术选型 / 仓库结构 / 数据库 / 前端后端架构)
- **治理与 ADR** → [docs/CONSTITUTION.md](启动配套/CONSTITUTION.md)(16 条原则详解 / 12 条 ADR / 不能做什么)
- **业务知识** → `docs/`(产品文档 / Skill YAML / MCP / 飞轮 / 商业模型 / Prompt 全集 / 模型路由)

**Claude Code 默认只读本文**——具体技术问题去查 ARCHITECTURE,具体决策为何这样去查 CONSTITUTION,业务知识去查 `docs/`。

---

## 13. 一句话

> **慢一点没事,做错代价大**——MCP / HITL / Agent 编号 / task_type 一旦上线就是产品 DNA,事后改是大手术。
>
> **不确定就问,不要猜**——5 分钟问用户胜过 5 小时返工。
