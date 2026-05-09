# 「有了」技术架构文档

**版本**:V2.0(基于 7 角色团队 + 三种工作模式 + Agent 拟人化)
**日期**:2026-05-04
**面向**:工程团队(后端 / 前端 / AI 工程师 / DevOps / 技术负责人)
**目的**:工程团队的起点文档,读完后理解整个系统全貌,知道自己负责的模块怎么对接其他模块

---

# 第 1 章 系统概览

## 1.1 产品定位与系统职责

### 产品定位

「有了」是面向中小企业和个体创作者的多智能体 AI 工作平台。第一期重点针对"内容引流"和"营销"场景,产品的外观和交互 80% 像微信。

**核心**:群内的多智能体协作 = 一支 AI 团队为你交付专业结果。

**用户路径**:用户加入"专属 AI 工作团队"群,在群聊中和 AI 团队协作。通过自然语言下达需求,系统自动理解、澄清、编排、执行,最终交付完整成品(视频/图/文档/文章)。

### 系统职责

技术系统的核心职责是把"用户的模糊需求"精准转化为"结构化任务",再编排多个 Agent 协同执行,交付完整成品。

具体分为 6 个核心能力:

1. **意图理解**:把自然语言转成结构化的意图 JSON
2. **意图澄清**:通过选择题(永远不让用户填空)收集缺失字段
3. **三种模式管理**:Plan(讨论)/ Ask(询问)/ Auto(自动)的派发与切换
4. **任务编排**:Auto 模式下基于 Skill 工作流派活给 Agent
5. **Agent 协作**:4 个分任务 Agent 通过消息队列协同;2 个支持 Agent 常驻主会话
6. **状态管理**:任务可中断、可暂停、可离线运行、可恢复

### 系统不做的事

- 不直接调用大模型让用户写 prompt(用户只说自然语言)
- 不让 Agent 之间直接派活(主编排是唯一调度者)
- 不让 Skill 的全文进 LLM 上下文(分层 + 按需加载)
- 不在 Plan/Ask 模式消耗任务配额(只算 token)

---

## 1.2 整体架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                              前端层                                   │
│      Next.js 15 Web App (三栏布局)│  移动端响应式                    │
│      Tailwind + shadcn/ui + Zustand                                  │
└──────────────────────┬─────────────────────────┬─────────────────────┘
                       │                         │
                  REST API                  WebSocket
                       │                         │
┌──────────────────────▼─────────────────────────▼─────────────────────┐
│                            网关层(FastAPI)                          │
│   鉴权 │ 限流 │ 路由 │ WebSocket 端点 │ 文件上传                      │
└─┬──────┬──────┬──────────┬─────────────────┬───────────────────────┘
  │      │      │          │                 │
┌─▼──┐ ┌─▼──┐ ┌─▼────┐ ┌──▼──────────┐ ┌────▼─────┐
│业务│ │主编│ │Skill │ │ContextPool  │ │ 数据访问 │
│服务│ │排  │ │服务  │ │   服务      │ │   层     │
│    │ │Agent│ │      │ │             │ │          │
└─┬──┘ └─┬──┘ └─┬────┘ └────┬────────┘ └────┬─────┘
  │      │      │           │                │
  │      └──────┼───────────┼────────────────┤
  │             │           │                │
  │      ┌──────▼───────────▼────────────────┘
  │      │   LangGraph 编排引擎(主编排进程内)
  │      │   - 8 个子模块(含模式管理 + 互动编排)
  │      │   - State 持久化
  │      │   - Checkpoint 管理
  │      └──────┬─────────────────────────────────┐
  │             │                                  │
  │     Redis Streams                              │
  │       消息队列                                 │
  │             │                                  │
  │      ┌──────┴──────┬──────────┬─────────┬─────┐│
  │      │             │          │         │     ││
  │   ┌──▼───┐  ┌──────▼──┐  ┌────▼───┐ ┌──▼──┐  ││
  │   │Agent1│  │Agent 2  │  │Agent 3 │ │Agent│  ││
  │   │文字  │  │文档     │  │图      │ │ 4   │  ││
  │   │研究员│  │文档专员 │  │设计师  │ │视频 │  ││
  │   │文案师│  │         │  │        │ │影音 │  ││
  │   │      │  │         │  │        │ │师   │  ││
  │   └──┬───┘  └──┬──────┘  └────┬───┘ └──┬──┘  ││
  │      │         │              │        │     ││
  │      │         │              │        │     ││
  │   ┌──▼─────────▼──────────────▼────────▼────┐││
  │   │  支持 Agent(常驻主会话,不接队列任务)    │││
  │   │  ┌────────┐         ┌───────────┐       │││
  │   │  │  HR    │         │ 财务经理  │       │││
  │   │  └────────┘         └───────────┘       │││
  │   └────────────────────────────────────────┘  ││
  │                                                ││
  │      ┌────────────────────────────────────────┐│
  │      │      模型路由层(LiteLLM + 自定义路由)││
  │      │      健康度监控 │ 故障转移 │ 成本控制   ││
  │      └─┬─────┬──────┬──────┬──────┬──────┬───┘│
  │        │     │      │      │      │      │     │
  │     DeepSeek Sonnet Haiku  GPT-5 Image2  火山TTS│
  │        │     │      │      │      │      │     │
┌─▼────────▼─────▼──────▼──────▼──────▼──────▼─────┐
│                      基础设施层                   │
│  PostgreSQL 16+pgvector │ Redis 7.x │ OSS │ Celery│
└──────────────────────────────────────────────────┘
```

**层次说明**:

- **前端层**:三栏布局,REST API + WebSocket 与后端通信
- **网关层**:FastAPI 统一入口,鉴权、限流、路由
- **业务服务层**:Conversation、ContextPool、Skill 等业务服务
- **主编排 Agent**:LangGraph 进程内,系统的大脑,8 个子模块
- **消息队列**:Redis Streams 解耦主编排和 4 个分任务 Agent
- **4 个分任务 Agent**:独立微服务,接收队列任务执行
- **2 个支持 Agent**:常驻主会话(HR + 财务经理),不接队列任务
- **模型路由层**:统一管理对 LLM 的调用,自动故障转移
- **基础设施层**:数据库、缓存、对象存储、长任务执行

---

## 1.3 关键技术决策清单

| 决策 | 选型 | 关键理由 |
|---|---|---|
| 编排引擎 | LangGraph | 状态管理 + checkpoint + streaming + 中断处理成熟 |
| 长任务执行 | Celery + Redis | V1 简单够用,V2 视频任务量大时升级 Temporal |
| Agent 通信 | Redis Streams | 低延迟 + 持久化 + consumer group |
| 模型路由 | LiteLLM + 自定义路由表 | 统一 100+ 模型接口 + 动态选型 |
| 主力意图理解模型 | DeepSeek-V4-Flash | 中文强 + 便宜 + 国内调用快 |
| 备用模型 | Claude Haiku 4.5 | 海外稳定性兜底 |
| 数据库 | PostgreSQL 16 + pgvector | ACID + 向量检索一站式 |
| 缓存 | Redis 7.x | 实时状态 + 限流 + 分布式锁 |
| 对象存储 | OSS / S3 | 产物文件存储 |
| 实时推送 | WebSocket | 流式输出 + 执行流 |
| 后端框架 | FastAPI | 异步 + 性能 + 生态 |
| 前端框架 | Next.js 15 + Tailwind + shadcn/ui + Zustand | App Router + 现代组件库 |
| 部署 | 单 Region + Docker | V1 阶段简单,V2 再做多 Region |

**核心架构决策**:

- **Agent 职责对应**:Agent 1 文字 / **Agent 2 文档** / **Agent 3 图** / **Agent 4 视频**
- **2 个支持 Agent**:HR(管理 AI 团队)+ 财务经理(管订阅配额)
- **三种工作模式**:Plan / Ask / Auto 是同群内的工作方式,可中途切换
- **总裁助理唯一性**:每个用户只有一个主编排 Agent 实例
- **Agent 之间不直接派活**:所有派活由主编排根据 Skill 工作流决定
- **用户视角的"互动"由主编排编排**:让 Agent 看似互相对话,实际是主编排调度
- **Skill 不全文进 LLM 上下文**:分层加载(元数据 + 步骤详情)
- **Prompt 渲染是程序化操作**:Jinja2 模板,不需要 LLM
- **意图澄清永远是选择题**:4 种形式

---

## 1.4 文档使用指南(谁读哪章)

| 角色 | 必读章节 | 选读章节 |
|---|---|---|
| 后端工程师 | 1, 2, 3, 6, 9, 10, 11, 13, 15 | 4, 5, 7, 8 |
| 前端工程师 | 1, 2, 3, 9 (尤其 9.4 WebSocket), 12 | 4, 6 |
| AI 工程师 | 1, 4, 5, 7, 8, 11 | 2, 9 |
| DevOps | 1, 3, 9, 10, 13, 14 | 11 |
| 技术负责人 | 全部 | - |
| 新人 | 1, 2, 3, 15(然后按角色读) | - |

---

# 第 2 章 核心概念与数据模型

## 2.1 核心实体定义

系统有 7 个核心实体,所有功能都围绕它们展开。

### User(用户)

**含义**:产品的使用者。

**关键字段**:id、phone/email、subscription_tier、preferences

**关键约束**:每个 User 必有一个主会话(Conversation 中 mode=main_session)。

**状态**:active / suspended / deleted

---

### Conversation(会话/群)

**含义**:用户在产品中的对话单元。

**关键字段**:
- id、user_id、name、mode、avatar_style
- current_work_mode(当前工作模式:plan / ask / auto)
- skill_id(执行 Skill 时挂上)
- status

**4 种 conversation mode**:
- `main_session`:主会话(每个用户唯一,即"专属 AI 工作团队"群)
- `work_group`:工作群(用户为特定场景建的群)
- `private_chat`:与单个 Agent 的私聊
- `(预留)`:V2 可能扩展

**关联实体**:User、Skill、Message、Artifact、Brief

**关键约束**:
- 同一用户的主会话只有一个
- 工作群一次只跑一个 active 任务

**状态**:active / paused / archived / deleted

---

### Brief(需求文档)

**含义**:Plan 模式产出的结构化需求文档。

**关键字段**:
- id、conversation_id、user_id
- intent(用户的核心意图,JSON)
- fields(已收集的字段值)
- completeness(完成度 0.0-1.0)
- decision_log(决策日志)

**Brief 结构**:
```
{
  "完成度": 0.85,
  "字段": {"产品": "...", "受众": "...", "风格": "..."},
  "决策日志": [{"时间": "...", "字段": "...", "内容": "..."}]
}
```

**关键约束**:
- 一个 Conversation 在一个时间点只有一个 active 的 Brief
- Plan → Auto 模式切换时,Brief 字段直接填入 Skill 的 inputs

---

### Skill(技能/工作流)

**含义**:完整的多步骤工作流定义,Auto 模式下使用。

**关键字段**:
- id、name、description、version、creator
- domain_tags、trigger_keywords、anti_signals
- inputs_schema(输入字段定义)
- workflow_steps(每步:agent + depends_on + prompt_template + output_format + quality_check)

**关键约束**:
- 用户不直接配置 Skill
- Skill 渲染成 prompt 是 Jinja2 模板替换(纯程序操作)
- Skill 元数据(~200 tokens)进主编排上下文,详情按需加载

**V1 上线 2 个 Skill**:反诈视频制作 + 电商详情图制作

---

### Agent(智能体)

**含义**:执行具体任务的 AI 工作单元。系统有 7 个 Agent,分 3 类:

**主编排 Agent(总裁助理)**:
- LangGraph 进程内的 Node 群,不是独立微服务
- 每个用户只有一个,跟着用户走
- 内部分 8 个子模块

**4 个分任务 Agent**(独立微服务):
- Agent 1 — 研究员/文案师(文字 + 工具调用)
- Agent 2 — 文档专员(PPT、Excel、Word、PDF)
- Agent 3 — 设计师(图像生成、编辑、风格管理)
- Agent 4 — 影音师(视频与音频)

**2 个支持 Agent**(独立服务,常驻主会话):
- HR — 管理用户的 AI 团队(推荐 Agent、加 Skill、引导进修)
- 财务经理 — 管订阅、配额、成本

**关键约束**:
- 4 个分任务 Agent 通过消息队列接收任务,不互相派活
- 2 个支持 Agent 不接队列任务,只在主会话中通过对话响应用户

---

### Task(任务)

**含义**:Auto 模式下,用户在工作群中发起的一次完整工作流执行。

**关键字段**:
- id、conversation_id、user_id、skill_id
- state(LangGraph 持久化的状态机)
- status、collected_fields、artifacts、completed_steps、interrupt_history

**关键约束**:
- 一个 Conversation 一次只能有一个 active 的 Task
- Plan / Ask 模式不创建 Task(只算 token 消耗)
- Task 可中断、可暂停、可离线运行

**状态**:pending / executing / paused / cancelled / completed / failed

---

### Artifact(产物)

**含义**:Agent 生成的产物,包括最终交付物和中间产物。

**关键字段**:
- id、conversation_id、task_id
- source_agent_id(哪个 Agent 产出)
- type、reference(OSS URL)、metadata

**产物类型**:
- text(文本,如脚本、文章)
- image(图片)
- video(视频)
- audio(音频)
- document(PPT、Excel、Word、PDF)
- structured(xlsx 数据表)

**关键约束**:实际内容存 OSS,数据库只存引用

---

## 2.2 实体关系图

```
                              ┌─────┐
                              │User │
                              └──┬──┘
                                 │ 1:N
                ┌────────────────┼─────────────────┐
                │                │                 │
                ▼                ▼                 ▼
        ┌──────────────┐  ┌──────────────┐ ┌──────────────┐
        │Conversation  │  │UserPref      │ │Subscription  │
        │              │  │              │ │              │
        │·main_session │  │ default_mode │ │              │
        │·work_group   │  │ style        │ │              │
        │·private_chat │  │ ...          │ │              │
        └─────┬────────┘  └──────────────┘ └──────────────┘
              │
              │ 1:N(消息和产物)
              │
              ├────────► Message(独立存储)
              │
              ├────────► Artifact(挂在 conversation 下)
              │
              ├────────► Brief(Plan 模式产出,1:1)
              │
              └────────► Task(Auto 模式启动,1:1)
                              │
                              │
                              ▼
                          Skill(引用)
```

**关键关系**:

1. User : Conversation = 1 : N
2. Conversation : Brief = 1 : 1(每个对话有 0 或 1 个 brief)
3. Conversation : Task = 1 : N(历史任务多个,active 只有 1 个)
4. Task : Artifact = 1 : N
5. Skill : Task = 1 : N(一个 Skill 被多次调用)

---

## 2.3 数据库 schema 总览

V1 阶段共 16 张主要表,按域划分:

### 用户域
- `users`:用户基本信息
- `user_preferences`:用户偏好画像
- `user_subscriptions`:订阅状态

### 会话域
- `conversations`:会话/群
- `messages`:消息

### 上下文域
- `briefs`:Plan 模式产出的需求文档
- `mode_history`:工作模式切换历史

### 任务域
- `tasks`:Auto 模式的任务
- `task_states`:LangGraph state 持久化(JSONB)
- `artifacts`:产物
- `artifact_versions`:产物版本

### Skill 域
- `skills`:Skill 定义
- `skill_versions`:Skill 版本
- `skill_embeddings`:Skill 向量索引
- `skill_executions`:Skill 执行记录
- `user_skill_visibility`:用户可见的 Skill 列表

### 路由域
- `model_registry`:可用模型列表
- `routing_rules`:路由规则
- `model_health_metrics`:模型健康度指标

### 知识域
- `materials`:素材库
- `knowledge_prompts`:知识库 Prompt

### 系统域
- `events`:事件流
- `audit_logs`:审计日志

---

## 2.4 状态机

### Conversation 状态流转

```
       创建
        │
        ▼
    [active] ────► [paused] ────► [active]
        │             │
        │             │ (24h 超时 or 用户取消)
        │             ▼
        │         [cancelled]
        │
        ▼
    [archived]
        │
        ▼
    [deleted]
```

### 工作模式状态流转(同群内可切换)

```
        进入群
         │
         ▼
     [选择模式]
     /    |    \
    /     |     \
   ▼      ▼      ▼
[plan] [ask] [auto]
   │      │      │
   │      │      │
   └──┬───┘      │
      │          │
      │ 用户切换  │
      ├──────────┘
      │
      ▼
   切换到任意模式
```

模式切换规则:
- Plan → Auto:用户说"开干",Brief 字段填入 Skill,启动 Task
- Auto → Plan:用户说"等等想想",Task 标记 paused,回到 Plan
- 任意模式 → Ask:用户问问题,临时切换,答完回到原模式
- Plan ↔ Auto 之间切换不重置 Brief

### Task 状态流转(Auto 模式)

```
        创建
         │
         ▼
     [pending]
         │ (输入校验通过)
         ▼
     [executing] ◄─────────────┐
         │                      │
         │ ┌────────────────────┘
         │ │ (中断 A/B,继续执行)
         ▼ │
   ┌─[paused]
   │     │
   │     │ (用户继续)
   │     ▼
   │  [executing]
   │
   ├──► [cancelled]
   ├──► [failed]
   └──► [completed]
```

---

# 第 3 章 服务架构

## 3.1 服务清单与职责

V1 阶段共 10 个服务模块:

### 网关服务(api-gateway)
**职责**:鉴权、限流、路由、WebSocket 端点
**部署**:1-2 个实例,2 核 4G

### 业务服务(business-service)
**职责**:Conversation、Message、Artifact、Material/Knowledge、User、Subscription
**部署**:2-3 个实例,2 核 4G

### Skill 服务(skill-service)
**职责**:Skill 元数据、三层检索、Skill 编译为 LangGraph、执行记录
**部署**:1-2 个实例,2 核 4G

### Brief 服务(brief-service)
**职责**:Brief 创建、更新、完成度评估;Plan 模式核心服务
**部署**:1-2 个实例,2 核 4G

### 主编排进程(orchestrator)
**职责**:LangGraph 进程,8 个子模块,Task State 管理
**部署**:水平扩展,4 核 8G

### 4 个分任务 Agent 服务
- agent-text(Agent 1):2 核 4G,2 实例
- agent-document(Agent 2):2 核 4G,2 实例
- agent-image(Agent 3):4 核 8G,3 实例
- agent-video(Agent 4):4 核 8G,2 实例

### 2 个支持 Agent 服务
- agent-hr(HR):2 核 4G,1-2 实例
- agent-finance(财务经理):2 核 4G,1-2 实例

### Celery Worker
**职责**:长任务异步执行(主要是 Agent 4 的视频合成)
**部署**:2-4 个实例,4 核 8G

---

## 3.2 服务间依赖关系

```
                                ┌──────────┐
                                │  Client  │
                                └─┬────┬───┘
                                  │    │
                            REST  │    │ WebSocket
                                  │    │
                            ┌─────▼────▼─────┐
                            │  api-gateway   │
                            └─┬──────┬──────┬┘
                              │      │      │
              ┌───────────────┘      │      └──────────┐
              │                       │                 │
              ▼                       ▼                 ▼
      ┌──────────────┐      ┌──────────────┐    ┌─────────────┐
      │business      │      │orchestrator  │    │skill/brief  │
      │service       │◄────►│              │◄──►│ services    │
      │              │      │  LangGraph   │    │             │
      └──────┬───────┘      └──────┬───────┘    └─────────────┘
             │                     │                   
             │                     │                   
             │              ┌──────▼─────────┐         
             │              │ Redis Streams  │         
             │              │  消息队列      │         
             │              └──────┬─────────┘         
             │                     │                   
             │      ┌────────┬─────┼─────────┬─────────┐
             │      │        │     │         │         │
             │      ▼        ▼     ▼         ▼         ▼
             │ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌────────┐
             │ │agent │ │agent │ │agent │ │agent │ │ celery │
             │ │text  │ │ doc  │ │image │ │video │ │ worker │
             │ └──────┘ └──────┘ └──────┘ └──────┘ └────────┘
             │
             │              ┌──────────┐ ┌─────────────┐
             └─────────────►│ agent-hr │ │agent-finance│
                            │常驻主会话│ │常驻主会话   │
                            └──────────┘ └─────────────┘
                                   │             │
                                   ▼             ▼
                            (业务 API + 数据库直接读取)
```

**关键依赖关系**:

- **同步依赖**:api-gateway → business / orchestrator / skill / brief
- **异步依赖**:orchestrator → Redis Streams → 4 个分任务 Agent
- **特殊依赖**:HR/财务经理 直接读业务数据库(不走队列),通过 API 直接响应主会话消息

---

## 3.3 部署拓扑

(部署架构与 V1 文档相同,详见前文)

---

# 第 4 章 主编排 Agent

## 4.1 定位与边界

### 定位

主编排 Agent(用户视角叫"总裁助理")是系统的大脑和唯一调度者。

**关键特征**:
- 不是独立微服务,是 LangGraph 进程内的 Node 群
- 每个用户唯一,跟着用户走
- 不直接产出内容
- 是唯一派活方
- 永远在场

### 必须做(职责)

- 理解用户意图
- 匹配 Skill(Auto 模式)
- 维护 Brief(Plan 模式)
- 派发到对应模式 handler
- 发起意图澄清(永远选择题)
- 分配任务给 4 个分任务 Agent
- 处理 8 类用户中断
- **编排 Agent 之间的"互动消息"**(让用户感觉像真公司工作群)
- 维护任务状态

### 不能做(边界)

- 不直接产出内容
- 不让 Agent 之间互相派活
- 不在不通过路由层的情况下调用 LLM
- 不把 Skill YAML 全文加载到 LLM 上下文
- 不在群里"主动说话"(只在被需要时出场)

---

## 4.2 内部子模块

主编排 Agent 内部分 8 个子模块:

| 子模块 | 职责 | 是否调 LLM | 上下文 | 延迟 |
|---|---|---|---|---|
| 1. 意图理解器 | 解析用户消息 → 意图 JSON | DeepSeek-V4-Flash | 1500 | 300ms |
| 2. 模式管理器 | 派发到 Plan/Ask/Auto 流程 | 不调 | 0 | 1ms |
| 3. Skill 匹配器 | 根据意图匹配 Skill(Auto 用) | 99% 不调 | 0/1500 | 5-30ms / 600ms |
| 4. 输入校验器 | 检查字段是否齐全(Auto 用) | 不调 | 0 | 1ms |
| 5. 澄清生成器 | 生成选择题 | 大部分不调 | 0/1000 | 1ms / 3-5s |
| 6. 任务编排器 | 渲染 prompt + 派活(Auto 用) | 不调 | 0 | 50-200ms |
| 7. 中断处理器 | 8 类中断分类与处理 | DeepSeek-V4-Flash | 1500 | 300ms |
| 8. **互动编排器** | 编排 Agent 之间的对话消息 | DeepSeek-V4-Flash | 1000 | 200ms |

**互动编排器(新增)**:这是支持"用户视角 Agent 互动"的关键。在派活时,主编排会让 Agent 在群里发"看似互相对话"的消息,实际由主编排统一编排。

**单任务总成本**:$0.001-0.003(15-20 次调用)
**单次响应**:< 1.5 秒

---

## 4.3 关键流程

### Auto 模式标准流程

```
用户发消息(假设 Auto 模式)
    ↓
[意图理解器] 解析 → 意图 JSON
    ↓
[Skill 匹配器] 三层检索 → 选定 Skill
    ↓
[输入校验器] 检查必填字段
    ├─ 有缺失 → [澄清生成器] → 选择题给用户
    │              │
    │              └─ 用户回答后回到[输入校验器]
    │
    └─ 全齐 → [任务编排器]
                  │
                  ▼
            Skill 编译为 LangGraph
                  │
                  ▼
            [互动编排器] 生成出场消息
            (例:"研究员开始调研...")
                  │
                  ▼
            按 depends_on 启动每个步骤的 Node
                  │
                  ▼
            渲染 prompt → AgentTask → 队列
                  │
                  ▼
            Agent 1-4 之一执行
                  │
                  ▼
            收到结果 → [互动编排器] 生成交接消息
            (例:"@文案师 调研完成,你来写脚本")
                  │
                  ▼
            触发下游 Node
                  │
                  ▼
            所有 Node 完成 → 任务结束
```

### Plan 模式流程

```
用户在 Plan 模式发消息
    ↓
[意图理解器] 解析意图
    ↓
[模式管理器] 检查当前模式 = plan
    ↓
判断需要哪种支持:
    ├─ 需要研究 → 调 Agent 1(联网搜索)
    ├─ 需要参考图 → 调 Agent 3(快速生成参考图)
    ├─ 决定方向 → 总裁助理回复
    └─ 用户说"开干" → 切到 Auto 模式
    ↓
异步:Brief 服务更新 Brief
    ↓
检查 Brief 完成度
    └─ ≥ 0.8 → 主编排主动建议"按这个开干?"
```

### Ask 模式流程

```
用户在 Ask 模式发消息
    ↓
[意图理解器] 判断是问题
    ↓
[模式管理器] 派发到 Ask handler
    ↓
判断答问题需要谁:
    ├─ 信息查询 → 调 Agent 1
    ├─ 系统问题(配额/订阅) → 财务经理
    ├─ Agent 推荐(我该用谁) → HR
    └─ 通用问题 → 总裁助理直接答
    ↓
返回答案,不创建 Task
```

### 中断处理流程

```
任务执行中,用户在群里发消息
    ↓
[中断处理器] 调 LLM 分类中断类型
    ↓
按类型派发:
    ├─ A 补充信息 → graph.update_state + 继续
    ├─ B 微调当前 → 取消当前节点 + 重启
    ├─ C 修改参数 → V2(依赖图回滚)
    ├─ D 改方向   → V2(fork 新 graph)
    ├─ E 暂停     → task.status = paused
    ├─ F 取消     → task.status = cancelled
    ├─ G 闲聊     → 不动 graph,直接回复
    ├─ H 反馈     → 写事件流
    └─ I 切换模式 → 切到 Plan/Ask/Auto
```

新增 I 类中断:用户主动切换模式(如 Auto 中说"等等我想想"切到 Plan)。

---

## 4.4 上下文管理策略

### 4 个解决策略

**策略 1:Skill 拆两层**
- 元数据层(进上下文):200-500 tokens
- 详情层(按需加载):每步的完整定义

**策略 2:8 个子模块独立上下文**
- 每个子模块的上下文独立,不共享
- 互动编排器单独 1000 tokens 上下文

**策略 3:Skill 检索三层架构**
- 第 1 层:关键词(SQL,0 tokens)
- 第 2 层:向量(pgvector,0 tokens)
- 第 3 层:LLM 兜底(1500 tokens)

**策略 4:State 用引用,不用全文**
- 产物用 artifact_id 引用,实际内容存 OSS

### 实际效果

每次 LLM 调用都控制在 1500 tokens 以下,响应 < 1 秒。

---

## 4.5 性能与成本

| 子模块 | P50 | P95 | 成本/次 |
|---|---|---|---|
| 意图理解 | 300ms | 600ms | $0.0002 |
| 模式管理 | 1ms | 5ms | $0 |
| Skill 匹配(平均) | 30ms | 80ms | $0 |
| 输入校验 | 1ms | 3ms | $0 |
| 澄清生成 | 1ms | 3-5s | $0 / $0.0005 |
| 任务编排 | 50ms | 200ms | $0 |
| 中断处理 | 300ms | 600ms | $0.0002 |
| 互动编排 | 200ms | 400ms | $0.0001 |

**主编排单任务总成本**:约 $0.001-0.003(15-20 次调用)

---

# 第 5 章 4 个分任务 Agent + 2 个支持 Agent

## 5.1 4 个分任务 Agent 通用框架

每个分任务 Agent 是独立的微服务,通过 Redis Streams 接收任务、返回结果。

### 通用架构

```
Agent 服务进程(Docker 容器)
├── 任务消费者(从 Redis Streams 读)
├── 任务路由器(按 task_type 分发)
├── Handler 池(每种 task_type 一个)
├── 工具集(各自不同)
├── 模型路由调用
├── 失败处理器
└── 结果发送器(写 Redis 结果队列)
```

### 通用消息格式

**主编排 → Agent(AgentTask)**:task_id、step_id、agent_id、task_type、prompt、inputs、parameters、routing_hints、output_format、callback

**Agent → 主编排(AgentResult)**:task_id、step_id、status、output、error

### 通用处理流程

1. 边界检查:task_type 是否支持,不支持立即返错
2. 路由 handler:按 task_type 找对应处理器
3. 选模型:调用模型路由层
4. 执行 handler
5. 质量校验
6. 上传 OSS
7. 写 artifact 表
8. 发结果

---

## 5.2 4 个分任务 Agent 的能力边界

### Agent 1:研究员/文案师(文字 + 工具调用)

**核心能力**:
- 文字生成:短文、长文(V1.5)、结构化、摘要、改写、润色、翻译(V1.5)
- 研究与信息收集:联网搜索(Tavily)、网页抓取(Playwright)、数据收集与整合
- 阅读理解与分析:文档理解、信息提取、推理、多文档对比

**工具集**:Tavily Search API、Playwright、httpx、pandas、知识库 @ 提示词

**V1 阶段 task_type**:short_writing、summarization、extraction、analysis、web_search、web_scrape、data_organize

**V1.5 阶段新增**:long_writing、structured_writing、translation、polish

**边界(返错的情况)**:不画图(给 Agent 3)、不做视频(给 Agent 4)、不组装文档(给 Agent 2)

### Agent 2:文档专员(办公文档)

**核心能力**:
- PPT、Excel、Word、PDF 操作(生成/修改/提取/格式化)
- 长图垂直拼接(电商详情图最后一步)
- 图片插入到文档

**工具集**:python-pptx、openpyxl、python-docx、PyPDF2、pdfplumber、pandas、matplotlib、Pillow、Tesseract OCR

**V1 阶段 task_type**:xlsx_create、xlsx_read、xlsx_format、docx_create、docx_modify、pdf_extract、image_concat_long(电商长图拼接)

**V1.5 阶段新增**:pptx_create(跨调 Agent 1+3)、pptx_modify、xlsx_chart、pdf_create、pdf_watermark、pdf_ocr 等

**特殊能力**:**跨 Agent 调用**——做 PPT 时通过队列调 Agent 1 写大纲、调 Agent 3 生配图(V1.5)

**边界**:不写纯文字内容(给 Agent 1)、不做图(给 Agent 3)、不做视频(给 Agent 4)

### Agent 3:设计师(图)

**核心能力**:
- 图像生成:文生图、图生图、批量生成(风格一致)、多图合成
- 图像理解:描述、风格分析、质量评估、OCR
- 图像编辑:局部重绘、扩图(V1.5)、抠图(V1.5)、画质增强(V1.5)、图片下载
- 风格管理:从参考图提取(V1.5)、风格迁移(V1.5)

**工具集**:Pillow、OpenCV、httpx(图片下载),调用 GPT Image 2 / Seedream 3 / Sonnet Vision / GPT-5 Vision

**关键能力:批量生成的风格一致性**——用第 1 张作为视觉锚点,后续保持风格统一(电商详情图核心)

**V1 阶段 task_type**:image_generate(真实)、batch_generate、image_describe、image_quality_check、image_download、image_compose、image_ocr

**V1.5 阶段新增**:image_edit、image_inpaint、image_outpaint、image_classify、image_enhance、background_remove、style_extract、style_transfer

**边界**:不写文字、不做视频、不组装文档

### Agent 4:影音师(视频与音频)

**核心能力**:
- 视频生成:文生视频(V1.5)、图生视频(V1.5)、视频合成(V1)
- 视频编辑:剪辑、字幕、BGM、转场(V1.5)
- 音频处理:TTS(火山主/阿里备)、Whisper 识别、BGM 选择、字幕对齐

**工具集**:FFmpeg、MoviePy、Whisper、火山引擎 TTS、BGM 素材库

**特殊能力**:**长任务异步执行**——视频合成 5-10 分钟通过 Celery 异步,立即返回 pending_external

**V1 阶段 task_type**:video_compose(长任务)、tts_generate、audio_to_text、bgm_select、subtitle_generate、subtitle_add、bgm_add

**V1.5 阶段新增**:text_to_video、image_to_video、video_describe、video_extract_frames、audio_extract、video_cut、transition_apply

**边界**:不写脚本、不画静态图、不组装文档

---

## 5.3 2 个支持 Agent

### HR Agent(管理 AI 团队)

**职责**:
- 给用户推荐合适的 Agent("我应该用什么 Agent 处理这件事")
- 引导用户加 Skill 到自己的库
- 引导 Agent 进修(V2,用户给 Agent 喂专属语料)
- 引导用户成为 Skill 创作者(V2)
- 解释 Agent 的能力边界

**部署**:独立微服务(agent-hr)
**资源**:2 核 4G
**模型**:DeepSeek-V4-Flash 主 + Haiku 备
**响应方式**:不接队列任务,只在主会话中通过 @HR 或问题分类到 HR 时响应

**与其他 Agent 的区别**:
- 不接 Redis Streams 任务队列
- 不参与 Skill 工作流执行
- 直接通过 API 收到主编排转发的消息
- 直接读业务数据库(查 user 的 skill 列表、agent 进修记录等)

### 财务经理 Agent(管订阅、配额、成本)

**职责**:
- 回答用户问"还剩多少配额"
- 主动提醒"本月已用 80%"
- 处理升级、续费请求
- 月度账单总结
- 解释计费规则

**部署**:独立微服务(agent-finance)
**资源**:2 核 4G
**模型**:DeepSeek-V4-Flash(轻量任务)
**响应方式**:同 HR

**关键数据来源**:
- user_subscriptions 表
- events 表(成本事件)
- 缓存的实时配额

---

## 5.4 协作规则

所有 Agent 必须遵守的工程原则:

1. **4 个分任务 Agent 之间不互相 @**——只通过队列
2. **跨 Agent 调用走相同的队列**(Agent 2 调 Agent 1 时,通过 agent_tasks:text)
3. **2 个支持 Agent 不参与 Skill 工作流**——只响应主会话
4. **超出能力必须返错**,不硬撑
5. **所有产物上传 OSS**
6. **元数据完整**
7. **失败有 3 层兜底**
8. **长任务用 Celery**
9. **流式输出**
10. **统一的 AgentTask / AgentResult 格式**

---

## 5.5 用户视角的 Agent 互动(关键设计)

**核心矛盾**:用户希望 Agent 之间像真实工作群一样有对话,但工程上 Agent 不应该直接通信。

**解决方案**:**用户视角的"互动"由主编排的"互动编排器"统一编排**。

### 工作机制

主编排在派活时,**自动让相应 Agent 在群里发"互动消息"**:

```
[研究员] 开始调研... 8 个案例都整理好了。
        @文案师 看你的脚本了。

[文案师] 收到 @研究员,马上开始写。
        @设计师 等会儿脚本里有 5 张图的描述,
        到时候麻烦你处理。

[设计师] 好,我先准备风格库。
```

**实现方式**:
- 主编排的"互动编排器"子模块在每个 Agent 派活前后,生成对应的群消息
- 这些消息看起来是 Agent 之间互相 @,实际是主编排统一编排
- Agent 本身不知道其他 Agent 的存在,不会"主动 @"

### 设计原则

- **保持克制**:不是每一步都演戏,只在关键交接点出"互动消息"
- **场景适配**:严肃场景(金融、医疗)互动消息更克制,日常场景可以多一些
- **效率优先**:互动消息不能拖慢任务执行,异步生成

### 工程层一致性

虽然用户感知层有"互动",**工程层架构原则不变**:
- Agent 之间不直接通信
- 主编排是唯一调度者
- 跨 Agent 调用走队列

---

## 5.6 长任务处理

(同前文,Agent 4 视频合成走 Celery)

---

# 第 6 章 三种工作模式

## 6.1 三种模式的本质差异

| 维度 | Plan(讨论) | Ask(询问) | Auto(自动) |
|---|---|---|---|
| 用户场景 | 想方向、看参考、试错 | 问问题、查信息、答疑 | 目标明确、执行交付 |
| 是否走 Skill 工作流 | 否 | 否 | 是 |
| 主调用 Agent | 总裁助理 + Agent 1/3 | 总裁助理 + 任意 Agent | 总裁助理 + 4 个分任务 Agent |
| 是否消耗任务配额 | 否 | 否 | 是 |
| 输出 | Brief + 参考图 | 答案 | 完整成品 |
| 群形态 | 同一个群 | 同一个群 | 同一个群 |

**关键设计**:三种模式是同群内的工作方式,**不需要建不同的群**。用户通过点击模式切换或自然语言切换。

## 6.2 模式切换流程

### 切换触发

**用户主动**:
- 点击模式切换按钮
- 自然语言("等等我想想" → Plan;"开干吧" → Auto;"我想问个问题" → Ask)

**主编排建议**:
- Plan 中 Brief 完成度 ≥ 0.8 → 建议切到 Auto
- Auto 中遇到方向性问题 → 建议切到 Plan
- 任意模式中用户问问题 → 临时进入 Ask 答完回原模式

### 状态保持

- Plan ↔ Auto 切换:Brief 字段保留,Skill inputs 自动填充
- 任意 → Ask 临时切换:不影响主任务状态
- Auto 暂停后切到 Plan:Task 状态保持 paused,可恢复

## 6.3 主会话特殊性

主会话(即"专属 AI 工作团队"群)的模式行为有些特殊:

- 默认模式:Ask(用户主要在主会话问问题、做元操作)
- 不能切换到 Auto(主会话不执行 Skill 工作流)
- HR 和财务经理常驻

**理由**:主会话是元操作中心,具体的 Skill 执行应该在工作群里。

---

# 第 7 章 Skill 系统

## 7.1 Skill 定义结构

(同 V1 文档,详见第 7 章)

关键修订:Skill 工作流步骤中的 Agent 字段对应改为:
- agent_1(文字)
- agent_2(文档)
- agent_3(图)
- agent_4(视频)

## 7.2 三层检索

(同 V1 文档,99% 不调 LLM)

## 7.3 Skill 生命周期

(同 V1 文档)

## 7.4 创作者飞轮(V2)

V2 阶段由 HR Agent 引导用户成为 Skill 创作者。

---

# 第 8 章 模型路由层

## 8.1 路由决策机制

(同 V1 文档)

## 8.2 V1 阶段路由表(Agent 职责修正版)

```yaml
# 主编排相关
- task_type: intent_understanding
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: brief_update
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: agent_interaction_message  # 新增:互动消息生成
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: interrupt_classification
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

# Agent 1 文字
- task_type: short_writing
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: web_search
  primary: claude-sonnet-4-6
  fallback_1: gpt-5

# Agent 2 文档(大部分不调 LLM)
- task_type: image_concat_long
  primary: pillow_internal  # PIL 程序
  
- task_type: xlsx_create
  primary: claude-sonnet-4-6  # 数据整理时
  fallback_1: deepseek-v4-flash

# Agent 3 图(职责修正,从原 Agent 2)
- task_type: image_generate
  scenario: realistic
  primary: gpt-image-2
  fallback_1: seedream-3

- task_type: batch_generate
  scenario: ecommerce
  primary: seedream-3
  fallback_1: gpt-image-2

- task_type: image_describe
  primary: claude-sonnet-vision
  fallback_1: gpt-5-vision

- task_type: image_quality_check
  primary: gpt-5-vision
  fallback_1: claude-sonnet-vision

# Agent 4 视频(职责修正,从原 Agent 3)
- task_type: video_compose
  primary: ffmpeg_internal
  routing_hints:
    long_task: true

- task_type: tts_generate
  primary: volcengine-tts
  fallback_1: aliyun-tts

- task_type: audio_to_text
  primary: whisper-v3
  fallback_1: aliyun-asr

# HR / 财务经理(轻量,主会话响应)
- task_type: hr_consultation
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5

- task_type: finance_consultation
  primary: deepseek-v4-flash
  fallback_1: claude-haiku-4-5
```

## 8.3 健康度监控

(同 V1 文档)

## 8.4 故障转移

(同 V1 文档)

## 8.5 成本控制

(同 V1 文档,新增对支持 Agent 的成本追踪)

---

# 第 9 章 通信架构

## 9.1 三种通信模式

| 模式 | 场景 | 特性 |
|---|---|---|
| 同步 REST API | 客户端 ↔ 后端业务服务 | 请求-响应 |
| 消息队列(Redis Streams) | 主编排 ↔ 4 个分任务 Agent | 异步,解耦,持久化 |
| 直接 API 调用 | 主编排 → HR / 财务经理 | 同步,绕过队列 |
| WebSocket | 后端 → 前端实时推送 | 低延迟,长连接 |

## 9.2 消息格式约定

(AgentTask 和 AgentResult 同 V1 文档)

## 9.3 队列设计

```
任务队列(主编排 → 分任务 Agent):
- agent_tasks:text         (Agent 1)
- agent_tasks:document     (Agent 2,新)
- agent_tasks:image        (Agent 3,新)
- agent_tasks:video        (Agent 4,新)

结果队列:
- agent_results:{task_id}_{step_id}
- agent_results:cross_{uuid}    (跨 Agent 调用专用)

支持 Agent 不接队列(直接 API 响应)

事件流:
- system_events
- streaming_events:{task_id}
- agent_interaction_events:{conversation_id}  (新:Agent 互动消息流)
```

## 9.4 WebSocket 事件(新增几个)

| 事件 | 触发时机 | payload |
|---|---|---|
| message_received | 用户消息保存 | message 对象 |
| agent_message_streaming | Agent 流式输出 | task_id + chunk |
| agent_interaction | Agent 互动消息 | conversation_id + message |
| agent_emotion | Agent 表情触发(新) | agent_id + emotion |
| agent_status_change | Agent 状态变化(新) | agent_id + status(摸鱼/工作/发呆) |
| step_started | 步骤开始 | step_id + agent_id |
| step_completed | 步骤完成 | step_id + artifact |
| task_completed | 任务完成 | task_id + 最终产物 |
| clarification_required | 需要澄清 | 选择题对象 |
| brief_updated | Brief 更新 | conversation_id + brief |
| mode_changed | 模式切换 | conversation_id + new_mode |

---

# 第 10 章 数据存储

(同 V1 文档,无重大变化)

# 第 11 章 失败处理

(同 V1 文档)

# 第 12 章 安全与合规

(同 V1 文档)

# 第 13 章 部署与运维

资源配置(更新):

| 服务 | 实例数 | 单实例规格 | 月成本 |
|---|---|---|---|
| 网关+业务+Skill+Brief | 3 | 2 核 4G | ¥1500 |
| orchestrator | 3 | 4 核 8G | ¥3000 |
| agent-text | 2 | 2 核 4G | ¥1000 |
| agent-document | 2 | 2 核 4G | ¥1000 |
| agent-image | 3 | 4 核 8G | ¥3000 |
| agent-video | 2 | 4 核 8G | ¥2000 |
| **agent-hr** | 1 | 2 核 4G | ¥500 |
| **agent-finance** | 1 | 2 核 4G | ¥500 |
| celery-worker | 2 | 4 核 8G | ¥2000 |
| RDS PostgreSQL | 1 主 1 从 | 4 核 16G | ¥3000 |
| Redis | 集群 | 4G | ¥1500 |
| OSS | - | 1TB | ¥200 |
| SLB + CDN + 带宽 | - | - | ¥4300 |
| **基础设施合计** | | | **¥23500** |
| LLM API 费用 | | | **¥10000-50000** |
| **总月成本** | | | **¥33500-73500** |

(其他章节同 V1 文档)

# 第 14 章 监控与告警

(新增监控指标)

- HR / 财务经理的会话量
- 模式切换频率(用户在 Plan/Ask/Auto 之间的切换)
- Brief 完成度分布(看 Plan 模式的健康度)
- Agent 互动消息生成成本

# 第 15 章 V1 实施路线图

## 15.1 模块开发顺序(更新)

V1 阶段总周期 6-8 周。按依赖关系分 6 个阶段:

```
阶段 1(第 1-2 周):基础设施 + 数据模型
阶段 2(第 2-3 周):主编排 8 个子模块 + 三种模式管理
阶段 3(第 3-4 周):4 个分任务 Agent + 模型路由
阶段 4(第 4 周):2 个支持 Agent(HR + 财务经理)
阶段 5(第 4-5 周):2 个核心 Skill + 互动编排
阶段 6(第 5 周):前端 UI(含表情系统、状态显示)
阶段 7(第 6 周):内测 + 反馈优化
```

## 15.2 工程团队分工(8 人)

(同 V1 文档,无重大变化)

## 15.3 关键里程碑

```
M1 (第 2 周末):基础设施完成
M2 (第 3 周末):主编排 + 模式管理可工作
M3 (第 4 周末):4 个分任务 Agent + 第一个 Skill 跑通
M4 (第 5 周末):支持 Agent + 互动编排 + 前端联调
M5 (第 6 周末):内测开始
M6 (第 8 周末):V1 公开发布
```

---

# 附录 A 术语表

| 术语 | 含义 |
|---|---|
| 总裁助理 | 主编排 Agent 的用户视角名(替代之前的"特别助理") |
| 4 个分任务 Agent | Agent 1 文字 / Agent 2 文档 / Agent 3 图 / Agent 4 视频 |
| 2 个支持 Agent | HR + 财务经理(常驻主会话) |
| 三种工作模式 | Plan(讨论)/ Ask(询问)/ Auto(自动) |
| 互动编排器 | 主编排子模块,生成 Agent 之间的"互动消息" |
| Brief | Plan 模式产出的需求文档 |
| 主会话 | 用户唯一的"专属 AI 工作团队"群 |
| Conversation | 会话/群,用户与 AI 交互的单元 |
| LangGraph | 多 Agent 编排框架 |
| LiteLLM | 统一 LLM 调用库 |
| PromptTemplate | Prompt 模板,Jinja2 渲染 |
| Skill | 技能/工作流,完整的多步骤任务定义 |
| Task | Auto 模式下的一次完整执行 |
| 表情系统 | 20 组表情包,关键节点出现 |
| 工作状态 | Agent 头像下方的状态显示 |

---

# 附录 B 相关专项文档清单

| 文档 | 内容 |
|---|---|
| 主编排 Agent 实现指南 | 8 个子模块的代码级实现 |
| 4 个分任务 Agent 实现指南 | 每个 Agent 的 handler、模型路由 |
| HR / 财务经理 Agent 实现指南 | 2 个支持 Agent 的实现 |
| 三种工作模式实现技术文档 | Plan/Ask/Auto 的派发与切换 |
| 互动编排器实现指南 | Agent 互动消息的生成 |
| 表情系统与状态显示实现指南 | 拟人化前端 + 后端实现 |
| 产品功能清单 | V1 必做的所有功能项 |
| 完整产品文档 | 给老板汇报的版本 |
| 技术选型与模型 API 选型 | 第三方对接清单 |

---

# 附录 C 技术决策记录(ADR)

### ADR-001:用 LangGraph 而非自研编排引擎(同前)

### ADR-002:Agent 之间不直接派活(同前)

### ADR-003:意图理解主力用 DeepSeek-V4-Flash(同前)

### ADR-004(更新):三种模式同群内切换,不是建不同群

**决策日期**:2026-05-04
**决策**:Plan / Ask / Auto 三种工作模式是同群内的工作方式,可中途切换
**背景**:之前讨论过"讨论群 + 工作群"两个群分离,后改为"三种模式同群"
**理由**:
- 同群连续性更好,用户不需要在群之间切换
- 模式切换比建群更轻量
- 减少产品 SKU 复杂度

### ADR-005(更新):Agent 2/3/4 职责对应

**决策日期**:2026-05-04
**决策**:Agent 2 = 文档 / Agent 3 = 图 / Agent 4 = 视频
**理由**:
- 文档处理大部分不调 LLM,作为 Agent 2 负载最轻
- 图相关任务多(电商详情图、反诈视频配图都用),作为 Agent 3 优先级高
- 视频是最重的(长任务、Celery),作为 Agent 4 独立资源

### ADR-006(新):Agent 之间互动由主编排编排

**决策日期**:2026-05-04
**决策**:用户视角看到 Agent 之间互动对话,工程层仍由主编排统一编排
**背景**:产品要求"接近真实公司工作群",但工程原则要求 Agent 不直接通信
**理由**:
- 用户感知层和工程实现层可以分开
- 主编排是唯一调度者(架构原则)
- 互动编排器作为新子模块,生成"互动消息"
- 保持克制,只在关键交接点演戏

### ADR-007(新):新增 2 个支持 Agent(HR + 财务经理)

**决策日期**:2026-05-04
**决策**:在 4 个分任务 Agent 之外,新增 HR 和财务经理两个支持 Agent
**理由**:
- 把"个人主页"、"AI 学院"等管理功能角色化为可对话的 AI
- 增强"AI 公司"的产品感
- 常驻主会话,用户随时可叫
- 不参与 Skill 工作流,不接队列任务,简化架构

---

**文档版本历史**

| 版本 | 日期 | 主要变更 |
|---|---|---|
| V1.0 | 2026-05-04 | 首版 |
| V2.0 | 2026-05-04 | Agent 2/3/4 职责修正;新增三种工作模式;新增 HR/财务经理;新增互动编排器;新增表情系统/状态显示 |

---

**文档结束**
