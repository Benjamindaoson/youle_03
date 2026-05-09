# CONSTITUTION.md

> **位置**:目标仓库 `docs/CONSTITUTION.md`
> **面向**:有人想偏离原则 / 决策有冲突时
> **关系**:CLAUDE.md(操作指令)→ ARCHITECTURE.md(技术细节)→ **CONSTITUTION.md(为什么这么决策 + 何时可以变 + 冲突如何裁决)**
>
> **版本**:v3.0(2026-05-05,对齐 ADR-001-rev / ADR-013 / ADR-014 / ADR-015 / ADR-016)
>
> **v3.0 核心变更**:
> - 🔄 ADR-001 → ADR-001-rev:Agent 编号反向(2=文档/3=图/4=影音)
> - 🔄 ADR-008 废弃 → ADR-014:三模式同群切换
> - 🔄 ADR-012 废弃:V1 hero = 反诈视频 + 电商详情图(回归)
> - ✨ ADR-013 / 015 / 016 新增

---

## 1. 这份文档存在的目的

**不是教你做事**(那是 CLAUDE.md),**是说明为什么必须这样做**,以及**遇到冲突时怎么裁决**。

任何想"绕过"或"修改" 16 条原则 / 12 条 ADR 的提议,先回到这份文件读一遍 → 仍认为该改 → 走治理流程。

---

## 2. 16 条铁律详解

### 2.1 单一调度者(原则 1)

主编排 Agent 是系统**唯一调度方**。Agent 1-4 之间:

- 不互相 @
- 不直接对话
- 不直连 HTTP/RPC
- 不跨调 handler

**为什么**:

- 主编排是"全局视图"——只有它知道任务整体进度、能正确分配中断、能记账(成本/耗时/质量)
- 避免环形依赖、死锁
- 可观测性:所有 step 状态都在 LangGraph state 里,前端右栏才能正确流式展示
- 故障隔离:某 Agent 挂了不会通过跨调链传染

**违反场景**:有人想让 Agent 4 做 PPT 时直接调 Agent 1 写大纲。

**正确做法**:在 Skill YAML 显式拆为 `ppt_outline (agent_1) → ppt_images (agent_2) → ppt_assemble (agent_4)` 三个 step。

### 2.2 Agent 编号锁定(原则 2 / ADR-001-rev,v3.0 反向锁定)

```
Agent 1 = 文字       = agent_tasks:text
Agent 2 = 文档专员   = agent_tasks:document
Agent 3 = 设计师     = agent_tasks:image
Agent 4 = 影音师     = agent_tasks:av
```

**为什么这个映射(v3.0 终版)**:

- 与产品方最终版「有了」产品描述一致
- 数字递进对应"内容创作链路"(文字 → 文档 → 图 → 影音,从轻到重)
- 反诈视频和电商详情图场景的 Agent 对应已修正(产品方拍板)

**历史变更**:

- v1.x 实现指南曾用 Agent 2=文档 / Agent 3=图 / Agent 4=视频
- v2.0 ADR-001 改为 Agent 2=图 / Agent 3=影音 / Agent 4=文档
- v3.0 ADR-001-rev 又改回 Agent 2=文档 / Agent 3=图 / Agent 4=影音(产品方最终版)

**v3.0 锁定后不再变更**。

### 2.3 跨能力步骤显式拆步(原则 3 / ADR-002)

Agent **不能调** `call_other_agent`。代码里 `call_other_agent` 函数永久 `NotImplementedError`,作为防御性编程。

**正确范式**:

```yaml
# ❌ 错误
- step_id: ppt_create
  agent: agent_4
  prompt: |
    生成大纲(自己跨调 Agent 1)
    生成配图(自己跨调 Agent 2)
    组装 PPT

# ✅ 正确
- step_id: ppt_outline
  agent: agent_1
- step_id: ppt_images
  agent: agent_2
  depends_on: [ppt_outline]
- step_id: ppt_assemble
  agent: agent_4
  depends_on: [ppt_outline, ppt_images]
  inputs:
    outline: "{{ppt_outline.output}}"
    images: "{{ppt_images.output}}"
```

### 2.4 State 用引用(原则 4)

LangGraph state 里所有产物只存:

```python
class Artifact:
    artifact_id: UUID
    type: Literal["text", "image", "video", "structured", ...]
    reference: str               # oss://bucket/path
    metadata: dict
```

**绝不存**:
- `full_content: str`(几 MB 文本)
- `image_bytes: bytes`(几 MB 图)
- `transcript_full: str`(几 KB)

**为什么**:

- LangGraph PostgreSQL checkpointer 每次 update 都序列化 state——存全文导致每秒 GB 级写入
- Agent 跨进程传 state 时序列化爆炸
- 调试时打印 state 看不清重点

**例外**:< 1KB 的小文本(如 brief 字段、用户偏好标量)可直接存。

### 2.5 长任务异步(原则 5)

视频合成 5-10 分钟,不能阻塞 Agent 进程。

**实现**:

```python
async def video_compose_handler(task, model):
    workflow_id = celery_app.send_task("video_compose_workflow", args=[payload]).id
    return AgentResult(status="pending_external", external_workflow_id=workflow_id)
```

Celery 完成后调用 `notify_langgraph_complete(callback_queue, ...)`,主编排 LangGraph 监听该队列恢复任务。

**判断标准**:任何 handler 预期 > 60 秒的,必须走 Celery。

### 2.6 永远选择题(原则 6)

澄清不让用户填空。4 种形式:

1. 单字段单选(3-4 按钮)
2. 多字段合并(2-3 字段一次问完)
3. 图片对比(3 张样图)
4. 内容版本对比(实时调 Agent 1 生成 3 版本)

**约束**:
- 每字段必有 default(超时 60 秒自动用 default)
- 不超过 5 轮(超过用 default 兜底)
- 偏好 confidence ≥ 1.0 自动套用,不再问

**违反例**:让用户写一段话描述风格 — ❌
**正确例**:[简约] [自然] [科技感] [自定义] — ✓

### 2.7 LLM 走 LiteLLM(原则 7 / ADR-007)

**禁止**:`import openai` / `import anthropic` 等 SDK 直接调模型。

**统一入口**:`from app.router import complete`

```python
response = await router.complete(
    task_type="short_video_script",          # 决定路由
    messages=[...],
    routing_hints={"primary": "deepseek-v4-pro"},
    response_format={"type": "json_object"}
)
```

**为什么**:

- 主备模型自动切换(健康度感知)
- 统一成本审计(LiteLLM dashboard)
- 统一限流
- 不需要每个调用点处理 4 种模型 SDK 差异

**例外**:Embedding 模型(BGE-M3 自托管)走自己的 HTTP API,**不**走 LiteLLM。

### 2.8 Prompt 不内联(原则 8)

**禁止**:

```python
response = await router.complete(
    messages=[{"role": "system", "content": "你是一个反诈视频写作专家..."}]   # 字面量
)
```

**正确**:

```python
from app.config.prompts import SHORT_VIDEO_SCRIPT_PROMPT

response = await router.complete(
    messages=[{"role": "system", "content": SHORT_VIDEO_SCRIPT_PROMPT}]
)
```

**为什么**:

- Prompt 治理统一(版本号 + 灰度)
- A/B test 框架可以批量替换 prompt
- 修 prompt 走 PR review,不在业务代码里偷偷改
- Prompt 回归测试集集中维护

### 2.9 Skill YAML 是契约(原则 9)

Skill 行为变更:

- ✓ 改 YAML + version bump(`v1.0 → v1.1`)
- ✗ 改 Python 代码(handler 是通用的,不针对特定 Skill)

**为什么**:

- 创作者能写 Skill(V1.5)而不需要改代码
- Skill 编译结果按 `(skill_id, version)` 缓存到 Redis,version 变才重新编译
- 灰度新版 Skill:同时上 v1.1 和 v1.0,A/B test

### 2.10 对话优先按钮(原则 10)

**走总裁助理对话**:

- 创建群、改群、跨群协调
- 订阅 Skill、查找历史
- 系统级答疑、偏好管理

**走按钮**:

- 进入已有会话
- 上传素材、下载产物
- 修改个人信息、私聊 Agent

**判断标准**:涉及"组建/配置/创造"走对话;"操作具体物件"走按钮。

### 2.11 不为 V2 写代码(原则 11)

V1 不实现:中断 C/D 完整版(C 简化版在 V1)、Skill 创作市场(V1.5)、Agent 进修、创作者分润、多人协作群、[做同款] 按钮、语音消息(V1.5)。

**接口预留即可**(数据库表 / API endpoint / 配置项),不要实际逻辑。

**为什么**:

- 8 周到 V1-P0 时间紧
- V2 功能没经过 PMF 验证,做了浪费
- 接口预留保证 V2 升级不需要破坏性改动

### 2.12 失败 3 层兜底(原则 12)

任何 LLM / 工具调用必须:

1. **重试 1-3 次**(指数退避,临时错误)
2. **切备用模型**(LiteLLM 自动)
3. **返回用户友好错误 + 建议下一步**

**绝不允许**:

- `except: pass`
- 静默失败(返回 None)
- 抛异常导致整个任务崩

---

### 2.13 MCP 是工具集成唯一标准(原则 13 / ADR-009)

详见 `docs/3_决策记录/MCP 集成方案.md`。

**核心规则**:

- 工具(Tavily / Playwright / FFmpeg / PIL / python-pptx 等)→ MCP server
- 模型(GPT-Image-2 / Veo-3 / Volcengine TTS)→ LiteLLM
- Agent handler 通过 `mcp_client.call_tool(server, tool, arguments)` 调用
- **禁止**直接 `import tavily / from playwright import ...`(handler 里)

**例外**:`mcp_servers/` 目录里的 server 实现可以直接 import 工具 SDK——它们是 MCP server 的 backend。

### 2.14 Hero 交付有 HITL gate(原则 14 / ADR-010)

视频任务必须 3 道 gate:

1. **脚本审核**(version_select):用户选 A/B/C 或要求重写
2. **配图审核**(quality_review):用户挑选 / 替换 / 重生成
3. **视频终审**(final_approval):接受 / 调整 / 回滚(中断 C)

电商详情图任务至少 1 道 gate:

- **配图审核**:第 4 步出图后用户可重生成单张

**V1 必须支持中断 C**(原 V2 推迟,已提前):

- 用户在终审选"回到第 N 步重做"
- 主编排:计算 affected_steps → 旧产物加版本号保留 → LangGraph 回滚 → 从 N 步重启

**为什么**:

- 视频生成模型成功率 70-85%,无 HITL 等于赌博
- 重做整个 8 分钟比"回滚到第 N 步"贵 3-5 倍
- HITL 是用户感受到"AI 团队"在替我打工的关键时刻

### 2.15 数据飞轮 4 类信号必沉淀(原则 15 / ADR-011)

每个任务完成必须产生 4 类信号:

| # | 信号 | 存储 | 用途 |
|---|------|------|------|
| 1 | 工作流完整轨迹 | Qdrant + OSS | RAG 增强主编排意图理解 |
| 2 | 用户偏好向量 | Postgres pgvector(256 维)| 候选选项动态排序 |
| 3 | 失败 → Reflexion | Postgres prompt_improvement_candidates | 改进 prompt(人审)|
| 4 | 高满意度 → Skill 草稿 | Postgres skill_drafts | 创作者飞轮(V1.5)|

**CI 强制**:任何修改 task 完成路径的 PR 必须保留 4 类信号沉淀,否则失败。

**为什么**:

- 没飞轮的 AI 应用产品 3 年内被 foundation model 升级吃掉的概率 > 70%(SV CTO 评估)
- 4 类信号都是低成本沉淀,不影响主流程
- 飞轮一旦转动起来,产品价值持续增长

### 2.16 垂直优先(原则 16,v3.0:ADR-012 已废)

V1 hero SKU = **反诈视频 + 电商详情图**(产品方最终版拍板,2026-05-05)

> ⚠️ v2.0 时代曾有 ADR-012 "V1 hero 锁定短视频",已废弃。短视频降级为 V1.5 通过 Skill 市场补齐。

V1 必做的 2 个 Skill:
- **反诈视频制作**(社区宣传 / 抖音投放)
- **电商详情图制作**(SMB 商家)

V1.5 通过 Skill 市场补齐:短视频制作、海报、长文、PPT 等。

**为什么**:

- 垂直产品比横向 agent 平台容易融资 / PMF
- 短视频赛道月活 9 亿+,付费意愿强
- 反诈视频是政府采购(原 V1 计划),没有自然增长引擎
- 横向 agent 平台是红海(Manus、Coze、OpenAI Operator 等)

---

## 3. ADR 索引(v3.0,生效中 12 条 + 已废 3 条)

| ID | 标题 | 状态 |
|----|------|-----|
| **ADR-001-rev** | **Agent 编号反向(v3.0):1=文字/2=文档/3=图/4=影音** | **生效** |
| ~~ADR-001~~ | ~~Agent 编号 v2.0(2=图/3=影音/4=文档)~~ | 已废 |
| ADR-002 | Agent 不主动跨调其他 Agent | 生效 |
| ADR-003 | 主编排实现指南统一 | 生效 |
| ADR-004 | 原理篇 / 工程篇拆分 | 生效 |
| ADR-005-rev | 音频归 Agent 4 影音师(v3.0)| 生效 |
| ADR-006 | Brief 防抖批量更新策略 | 生效 |
| ADR-007 | 模型路由分两层(L1/L2)| 生效 |
| ~~ADR-008~~ | ~~讨论群/工作群两种独立群~~ | 已废,由 ADR-014 取代 |
| ADR-009 | MCP 协议作为工具集成唯一标准 | 生效 |
| ADR-010 | Hero 交付物必有 HITL gate | 生效 |
| ADR-011 | 数据飞轮 4 类信号沉淀必做 | 生效 |
| ~~ADR-012~~ | ~~V1 hero 锁定短视频~~ | 已废,V1 hero 回归反诈+电商详情图 |
| **ADR-013** | **2 个支持 Agent(HR + 财务经理)** | **生效** |
| **ADR-014** | **三模式同群内切换(Plan/Ask/Auto)** | **生效** |
| **ADR-015** | **Agent 拟人化 V1 必做** | **生效** |
| **ADR-016** | **左栏导航简化** | **生效** |

详细见 `docs/3_决策记录/开放问题与决议.md`。

---

## 4. 不能做什么(7 类硬禁止)

### 4.1 架构禁忌

- ❌ `call_other_agent` 跨调
- ❌ Agent 走 HTTP/RPC 直连
- ❌ 主编排自己生成内容
- ❌ Skill 全文进 LLM
- ❌ State 存全文
- ❌ Agent handler 里直接调工具 SDK(必须走 MCP client)
- ❌ 新增工具不暴露为 MCP server

### 4.2 模型 / Prompt 禁忌

- ❌ `import openai` / `import anthropic` 等 SDK 调模型
- ❌ Prompt 字面量内联代码
- ❌ Agent 自己决定模型(必须走 routing_hints)
- ❌ 跳过 Pydantic JSON Schema 校验
- ❌ 改 prompt 不更新回归测试 yaml

### 4.3 用户体验禁忌

- ❌ 让用户填空澄清
- ❌ 加按钮替代对话(违反原则 10)
- ❌ emoji(用 lucide-react)
- ❌ 暴露 Agent 协作内部过程(用户只看到 Agent 出场,不看到调度)
- ❌ 一群多任务
- ❌ Hero 任务无 HITL gate
- ❌ V1 不支持中断 C

### 4.4 数据 / 状态禁忌

- ❌ 跨群共享 messages(每群独立)
- ❌ 省 LangGraph PostgreSQL checkpointer
- ❌ 把 OSS 凭证下发到客户端
- ❌ 数据库明文存 token / API key
- ❌ 跳过配额检查
- ❌ 任务完成不写飞轮 4 类信号
- ❌ 训练数据没有用户授权

### 4.5 范围禁忌

V1 不实现:

- 中断 D(改方向,fork graph)
- Skill 创作市场(V1.5)
- Agent 进修(V2)
- 创作者分润机制(V2)
- 多人协作群(V2)
- 多个讨论群合并(V2)
- [做同款] / [加入此团队] 一键复刻按钮(V2)
- 语音消息(V1.5)
- 海报模板 / 长文创作 / PPT(V1.5)
- 改 Agent 编号映射
- 改 task_type 命名
- 放弃 MCP 用回直连

### 4.6 商业禁忌

- ❌ 不做付费版直接上线("以后再付费"是融资骗自己)
- ❌ 不算单位经济直接放免费额度
- ❌ CAC > LTV/3 的渠道继续投
- ❌ 看创作者飞轮"涨用户"忽略主动 GTM

### 4.7 工程禁忌

- ❌ 省 MCP 集成测试
- ❌ 省 HITL Playwright 测试
- ❌ 省数据飞轮信号沉淀的 PR check
- ❌ 单容器跑多 Agent
- ❌ Agent 跑 GPU 密集任务(应走 Celery GPU 节点)
- ❌ 跨 namespace 直连 prod 数据库
- ❌ 把 .env 提交进 git
- ❌ 跳过 Alembic 迁移
- ❌ 用 print 打日志(用 structlog)
- ❌ except Exception: pass

---

## 5. 决策矩阵(冲突时如何裁决)

### 5.1 文档冲突

```
CLAUDE.md 与 ARCHITECTURE.md 冲突 → 以 CLAUDE.md 为准(操作指令更新更频繁)
ARCHITECTURE.md 与 docs/2_工程实现 冲突 → 以 ARCHITECTURE.md 为准(更顶层)
ADR 与 任何文档 冲突 → 以 ADR 为准(治理决策最高)
```

### 5.2 原则冲突

```
铁律 (原则 16 条) 与 任何"代码风格 / 个人偏好" 冲突 → 以铁律为准
铁律之间冲突(罕见) → 走治理流程开 issue
```

### 5.3 V1 范围冲突

```
"产品想要 X" 但 X 在 V2 范围 → 拒绝,接口预留
"工程觉得 V2 的 Y 应该提到 V1" → 评估:必要性 + 工时 + ADR-011 飞轮影响
  → 必须修订 ADR(走治理流程)
```

### 5.4 ADR 之间冲突

罕见。如发生(如 ADR-002 不跨调 vs ADR-009 MCP 工具复用):

- 写新 ADR(ADR-NNN-修订版)标记 supersedes 旧版
- 旧 ADR 状态改"已废弃"
- 不直接改旧 ADR

---

## 6. 治理流程

### 6.1 新增 ADR

1. 在 `docs/3_决策记录/开放问题与决议.md` 末尾追加"草案 ADR-NNN"
2. 工程 + 产品双签
3. 状态改"已采纳",更新相关文档(CLAUDE.md / ARCHITECTURE.md / 业务文档)
4. 落地状态打勾

### 6.2 修订 ADR

1. **不改动已采纳的 ADR 内容**(保留历史)
2. 新增 ADR-NNN-修订版,标记 supersedes 旧版
3. 旧 ADR 状态改"已废弃"
4. 同步更新所有引用旧 ADR 的文档

### 6.3 prompt 变更

每个 prompt 加版本号 + 校验和:

```python
ORCHESTRATOR_INTENT_PROMPT = """..."""
ORCHESTRATOR_INTENT_PROMPT_VERSION = "v1.0.0"
```

新版 prompt 上线流程:

1. 写新版,标 v1.0.1
2. LiteLLM 路由 `prompt_version_split: {v1.0.0: 90%, v1.0.1: 10%}`
3. 监控关键指标 24 小时
4. 全量 / 回滚

### 6.4 Skill 变更

1. Skill YAML 改 + version bump(v1.0 → v1.1)
2. 同时上 v1.0 和 v1.1,A/B test
3. 7 天观察用户满意度
4. 全量 / 回滚

### 6.5 商业 / 单位经济变更

1. 更新 `docs/3_决策记录/商业模型与单位经济.md`
2. 同步 CLAUDE.md §4
3. 必要时新增 ADR

---

## 7. V1 / V1.5 / V2 范围

### V1(8 周到 P0,3 个月到完整)

V1-P0:
- 主编排 8 子模块
- 4 个 Agent + 各 1 happy-path handler
- **短视频 Skill**(hero,3 道 HITL gate + 中断 C)
- 7 个 MCP server(可只 happy path)
- 数据飞轮 4 类信号
- 前端三栏 + HITL 组件
- Docker Compose dev

V1-P1(3 个月内):
- 电商详情图 Skill
- 配额体系完整
- Reflexion / Skill Drafter pipeline 真跑
- K8s 生产部署
- 监控大盘 + 告警

V1-P2(6 个月内):
- 离线继续运行
- 跨群消息搜索
- 偏好画像可视化
- BGM 素材库扩充

### V1.5(6-9 月)

- Skill 创作市场(创作者飞轮开放)
- 偏好画像可视化
- 平台发布集成(抖音 / 视频号 / 小红书 API)
- 海报模板 / 长文 / PPT Skill 上线

### V2(9-18 月)

- 中断 D(改方向,fork graph)
- Agent 进修(语料 + LoRA 微调)
- 创作者分润
- 多人协作群
- 海外市场(英文 TikTok)
- 自研短视频模型

---

## 8. 任何修改 V1 范围的提议必经流程

```
1. 在 docs/3_决策记录/开放问题与决议.md 提"草案"
2. 评估:
   - 必要性(用户调研支持?)
   - 工时(本 Sprint 还是后续 Sprint?)
   - ADR-011 飞轮影响
   - 单位经济影响
3. 工程 + 产品 + 增长 三方签字
4. 修订相关 ADR(必要时)
5. 同步 CLAUDE.md / ARCHITECTURE.md
```

**禁止**:在不改文档的情况下"先做了再说"。

---

## 9. 一句话

> **铁律是为了让所有人节省决策时间——不是为了限制你**。
>
> 如果你觉得某条铁律阻碍了对的事,**先问自己**:是这条铁律错了,还是你想偏离的方向错了?
>
> 90% 的时候是后者。剩下 10%,走治理流程。
