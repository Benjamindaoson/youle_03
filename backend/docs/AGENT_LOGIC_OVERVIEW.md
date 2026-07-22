# 项目中智能体相关逻辑总览

本文档用于梳理 `youle` 项目里与“智能体”相关的核心代码、运行链路和职责边界，方便快速定位主编排、各 Agent、工具调用和增强能力。

## 1. 总体架构

这个项目不是“单个智能体 + 一堆工具”的结构，而是分成 4 层：

1. 用户消息入口和任务决策层
2. 主编排层
3. 4 个独立 Agent 执行层
4. MCP 工具层和模型调用层

当前项目只保留 LangGraph 主编排链路。

## 2. 关键目录

| 目录 | 作用 |
| --- | --- |
| `backend/app/api/` | 用户请求入口，决定是否进入智能体流程 |
| `agents/orchestrator_agent/` | 主编排逻辑，包括 Skill 匹配、输入校验、LangGraph Runner |
| `backend/app/services/` | 派发、私聊、支持型 Agent、配额与飞轮等服务 |
| `agents/` | 4 个独立 Agent 进程及其 handlers |
| `agents/_common/` | Agent 公共协议、队列消费、MCP/LLM 客户端 |
| `mcp_servers/` | 工具服务，如搜索、图像、音频、视频、文档、OSS |
| `skills/*.yaml` | 多 Agent 工作流定义 |
| `flywheel/` | 反思、偏好、技能草拟等增强能力 |

## 3. 当前主链路

### 3.1 用户消息进入系统

入口文件：

- [`backend/app/api/messages.py`](../backend/app/api/messages.py)

主要职责：

1. 写入用户消息
2. 解析 `@agent` mention
3. 判断是否走私聊短路径
4. 做意图识别
5. 匹配 Skill
6. 做输入校验和澄清
7. 创建任务并交给 Runner 启动

这一步是“是否进入智能体编排”的总入口。

### 3.2 Runner 入口

入口文件：

- [`agents/orchestrator_agent/runner_factory.py`](../agents/orchestrator_agent/runner_factory.py)

关键点：

- `make_runner(session)` 固定返回 `LangGraphTaskRunner`
- 调用层仍通过工厂拿 runner，这样 API 层不依赖具体实现文件路径

也就是说，生产主链路的“大脑”就是 LangGraph Runner。

### 3.3 LangGraph 主编排

核心文件：

- [`agents/orchestrator_agent/langgraph_runner/runner.py`](../agents/orchestrator_agent/langgraph_runner/runner.py)
- [`agents/orchestrator_agent/langgraph_runner/compiler.py`](../agents/orchestrator_agent/langgraph_runner/compiler.py)
- [`agents/orchestrator_agent/langgraph_runner/state.py`](../agents/orchestrator_agent/langgraph_runner/state.py)
- [`agents/orchestrator_agent/langgraph_runner/result_waiter.py`](../agents/orchestrator_agent/langgraph_runner/result_waiter.py)

职责拆分如下：

`compiler.py`

- 把 `skills/*.yaml` 编译成 LangGraph `StateGraph`
- 为每个 workflow step 生成节点
- 节点内部负责：
  - 渲染 `prompt_template`
  - 组装 `AgentTask`
  - 派发到 Redis Stream
  - 等待 `AgentResult`
  - 写回 `step_results`
  - 必要时触发 HITL 中断

`runner.py`

- 启动图执行
- 处理 HITL resume
- 处理 rollback/time-travel
- 将 LangGraph 状态镜像回数据库
- 推送 WebSocket 事件
- 在跨 Agent 交接时生成互动消息

`state.py`

- 定义整个任务的 LangGraph 状态结构
- 只保存引用，不保存大文件二进制
- 保存 `step_results`、`hitl_decisions`、`rollback_count`、`final_status` 等信息

`result_waiter.py`

- 从 `agent_results:{task_id}` 读取回执
- 只取当前 step 对应的结果
- 作为 LangGraph 节点等待 Agent 回执的桥梁

## 4. 智能体工作流的定义方式

工作流定义在 `skills/*.yaml` 中，例如：

- [`skills/short_video.yaml`](../skills/short_video.yaml)
- [`skills/ecommerce_detail_image.yaml`](../skills/ecommerce_detail_image.yaml)
- [`skills/short_video.yaml`](../skills/short_video.yaml)

每个 step 会描述：

- `step_id`
- `agent`
- `task_type`
- `depends_on`
- `prompt_template`
- `inputs`
- `parameters`
- `routing_hints`
- `hitl_gate`

这意味着项目里的“多智能体逻辑”并不是硬编码在一个大函数里，而是：

1. Skill YAML 定义流程
2. `compiler.py` 编译流程
3. Agent 执行各自步骤

## 5. 主编排到 Agent 的消息流

整体链路如下：

```text
用户消息
  -> backend/app/api/messages.py
  -> runner_factory.py
  -> LangGraphTaskRunner.start()
  -> langgraph_runner/compiler.py 中的 step node
  -> dispatcher 把 AgentTask 写入 Redis Stream
  -> 对应 Agent 进程消费
  -> handler 执行
  -> AgentResult 写回 agent_results:{task_id}
  -> LangGraph result_waiter 等到结果
  -> runner.py 镜像回 DB 并继续推进下游 step
```

派发文件：

- [`backend/app/services/dispatcher.py`](../backend/app/services/dispatcher.py)

它负责把 `AgentTask` 推到对应队列：

- `agent_1 -> agent_tasks:text`
- `agent_2 -> agent_tasks:document`
- `agent_3 -> agent_tasks:image`
- `agent_4 -> agent_tasks:av`

## 6. Agent 公共运行框架

核心文件：

- [`agents/_common/protocol.py`](../agents/_common/protocol.py)
- [`agents/_common/consumer.py`](../agents/_common/consumer.py)
- [`backend/app/schemas/agent.py`](../backend/app/schemas/agent.py)

### 6.1 协议层

`protocol.py` 和 `schemas/agent.py` 定义了主编排与 Agent 之间的统一协议：

- `AgentTask`
- `AgentResult`
- `ArtifactRef`

这是整个系统里“主编排”和“执行 Agent”之间的边界契约。

### 6.2 Consumer 层

`agents/_common/consumer.py` 是 4 个 Agent 共用的任务消费框架，职责包括：

- 从 Redis Stream 读取任务
- 解析 `AgentTask`
- 校验边界
- 按 `task_type` 路由到 handler
- 超时控制
- 重试
- DLQ
- 写回 `AgentResult`
- 发心跳

所以每个 Agent 的 `main.py` 都很薄，真正的运行框架在这里。

## 7. 四个执行 Agent

### 7.1 Agent 1：文字 Agent

入口：

- [`agents/text_agent/main.py`](../agents/text_agent/main.py)

主要 handlers：

- `short_writing`
- `long_writing`
- `web_search`
- `version_compare`

### 7.2 Agent 2：文档 Agent

入口：

- [`agents/document_agent/main.py`](../agents/document_agent/main.py)

主要 handlers：

- [`agents/document_agent/handlers/image_concat_long.py`](../agents/document_agent/handlers/image_concat_long.py)
- [`agents/document_agent/handlers/extras.py`](../agents/document_agent/handlers/extras.py)

能力包括：

- 长图拼接
- PPTX 组装
- XLSX 组装
- DOCX 组装
- PDF 提取
- PDF OCR

### 7.3 Agent 3：图像 Agent

入口：

- [`agents/image_agent/main.py`](../agents/image_agent/main.py)

主要能力：

- 图片生成
- 批量生成
- 风格提取
- 图片质检
- 图片下载

### 7.4 Agent 4：影音 Agent

入口：

- [`agents/av_agent/main.py`](../agents/av_agent/main.py)

主要 handlers：

- `tts_generate`
- `audio_to_text`
- `bgm_select`
- `video_compose`
- `v15_real`

其中视频合成还有一条异步长任务链路：

- [`agents/av_agent/handlers/video_compose.py`](../agents/av_agent/handlers/video_compose.py)
- [`agents/av_agent/celery_tasks/video_workflow.py`](../agents/av_agent/celery_tasks/video_workflow.py)

这类长任务会先返回 `pending_external`，等 Celery 任务完成后再把最终结果写回 `agent_results:{task_id}`。

## 8. Agent 的能力是怎么实现的

Agent 的实际业务能力主要有两种来源：

1. 调 LLM
2. 调 MCP 工具

### 8.1 LLM 调用

核心文件：

- [`agents/_common/llm.py`](../agents/_common/llm.py)

职责：

- 根据 `task_type` 做模型路由
- 兼容多个提供商
- 统一 `chat/completions`
- 支持流式输出和音频输出

这里定义了不同任务类型默认用什么模型，例如：

- 文案任务
- 搜索总结任务
- 图像理解任务
- TTS / ASR 任务

### 8.2 MCP 工具调用

核心文件：

- [`agents/_common/mcp_client.py`](../agents/_common/mcp_client.py)

对应工具服务目录：

- [`mcp_servers/search`](../mcp_servers/search)
- [`mcp_servers/image_tools`](../mcp_servers/image_tools)
- [`mcp_servers/video_tools`](../mcp_servers/video_tools)
- [`mcp_servers/audio_tools`](../mcp_servers/audio_tools)
- [`mcp_servers/document_tools`](../mcp_servers/document_tools)
- [`mcp_servers/oss`](../mcp_servers/oss)

典型模式是：

1. handler 从 `task.inputs` 和 `task.parameters` 取参数
2. 通过 `mcp_client.call_tool()` 调某个 MCP server
3. 把输出转换成 `AgentResult`

例如文档 Agent 的 `extras.py`，本质就是把文档相关请求转发给 `mcp-document-tools`。

## 9. 主编排之外的智能体相关支线

### 9.1 私聊单 Agent 路径

核心文件：

- [`backend/app/services/private_chat.py`](../backend/app/services/private_chat.py)

特点：

- 不启动完整 Skill 工作流
- 不调度其他 Agent
- 直接使用短上下文和系统提示词回复

这条路径更像“轻量单 Agent 会话”。

### 9.2 支持型 Agent

核心文件：

- [`backend/app/services/support_agent.py`](../backend/app/services/support_agent.py)

包括：

- `hr`
- `finance_manager`

这两个支持型 Agent：

- 只在主会话中出现
- 不进入 `agent_tasks:*` 队列
- 直接调用 LLM 回复

所以它们属于“智能体角色”，但不属于 4 个执行 Agent 的流水线体系。

### 9.3 Agent 互动编排

核心文件：

- [`agents/orchestrator_agent/interaction.py`](../agents/orchestrator_agent/interaction.py)

职责：

- 在跨 Agent 交接时生成一条群聊互动消息
- 写入消息表
- 推送 WS

它不负责业务执行，而是负责增强多 Agent 协作的表现层。

## 10. 增强能力

### 10.1 Reflexion 反思链路

核心文件：

- [`agents/orchestrator_agent/langgraph_runner/reflexion_graph.py`](../agents/orchestrator_agent/langgraph_runner/reflexion_graph.py)

作用：

- 对失败任务做根因分析
- 提出 prompt 改进建议
- 落库形成待审核候选项

这条链路不参与主任务执行，而是属于“失败后学习”的飞轮能力。

### 10.2 Checkpointer

核心文件：

- [`agents/orchestrator_agent/langgraph_runner/checkpointer.py`](../agents/orchestrator_agent/langgraph_runner/checkpointer.py)

作用：

- 给 LangGraph 提供持久化 checkpoint
- 支持中断恢复
- 支持状态历史
- 支持 time-travel / rollback

它是主编排的运行时基础设施，不直接产出内容，但决定了任务能否恢复和回滚。

## 11. 运行时支撑链路

除了 `LangGraphTaskRunner` 本体，还可以顺着这两层看运行时行为：

- [`agents/orchestrator_agent/langgraph_runner/result_waiter.py`](../agents/orchestrator_agent/langgraph_runner/result_waiter.py)
- [`agents/orchestrator_agent/langgraph_runner/checkpointer.py`](../agents/orchestrator_agent/langgraph_runner/checkpointer.py)

说明：

- `result_waiter.py` 负责等待 `agent_results:{task_id}` 中当前 step 的回执
- `checkpointer.py` 负责 checkpoint 持久化、恢复和历史读取
- 任务推进、HITL 恢复、回滚和历史查询都围绕这套链路展开

## 12. 推荐阅读顺序

如果是第一次接手这个项目，建议按下面顺序看：

1. [`backend/app/api/messages.py`](../backend/app/api/messages.py)
2. [`agents/orchestrator_agent/runner_factory.py`](../agents/orchestrator_agent/runner_factory.py)
3. [`agents/orchestrator_agent/langgraph_runner/compiler.py`](../agents/orchestrator_agent/langgraph_runner/compiler.py)
4. [`agents/orchestrator_agent/langgraph_runner/runner.py`](../agents/orchestrator_agent/langgraph_runner/runner.py)
5. [`agents/orchestrator_agent/langgraph_runner/state.py`](../agents/orchestrator_agent/langgraph_runner/state.py)
6. [`backend/app/services/dispatcher.py`](../backend/app/services/dispatcher.py)
7. [`agents/_common/consumer.py`](../agents/_common/consumer.py)
8. 某个具体 Agent 的 `main.py` 和 `handlers/*.py`
9. 对应的 `skills/*.yaml`

## 13. 一句话总结

这个项目的智能体逻辑本质上是：

- `messages.py` 决定要不要启动任务
- `skills/*.yaml` 定义多 Agent 工作流
- `LangGraph runner` 负责任务编排、状态推进、HITL 和回滚
- `dispatcher + Redis Streams` 负责主编排和 Agent 之间的通信
- `AgentConsumer + handlers` 负责真正执行具体任务
- `MCP + LLM` 提供底层能力

如果只找“最核心的大脑”，优先看：

- `backend/app/api/messages.py`
- `agents/orchestrator_agent/runner_factory.py`
- `agents/orchestrator_agent/langgraph_runner/compiler.py`
- `agents/orchestrator_agent/langgraph_runner/runner.py`
