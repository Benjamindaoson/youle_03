# ADR-017: LangGraph 作为唯一主编排内核

**状态**: Accepted
**日期**: 2026-05-08

## 结论

项目主编排已经收敛为单轨 LangGraph：

- 运行时只保留 `LangGraphTaskRunner`
- `runner_factory.make_runner(session)` 固定返回 LangGraph runner
- 旧版 `TaskRunner` 与 legacy `result_consumer` 已删除
- 回滚、历史查询、HITL 恢复都直接依赖 LangGraph checkpoint 能力

## 背景

项目早期存在一套手写编排器，负责：

- 把 Skill YAML 编译成 DAG
- 按依赖关系派发 step
- 用数据库状态和 HITL gate 推进任务

这套实现后来暴露出两个核心问题：

1. 回滚到第 N 步、改方向续跑这类 time-travel 能力很难自然实现。
2. 同时维护手写 runner 和 LangGraph 双轨，心智成本和维护成本都偏高。

## 决策

主编排统一采用 LangGraph，并保留现有系统边界：

- LangGraph 负责任务状态、节点调度、HITL 暂停/恢复、checkpoint 和 time-travel
- Redis Streams 继续负责主编排到 Agent 的分布式派发
- Agent 进程继续消费 `agent_tasks:*` 并写回 `agent_results:{task_id}`
- 数据库中的 `tasks`、`task_steps`、`hitl_gates`、`artifacts` 继续作为业务侧可查询镜像

核心模块如下：

```text
agents/orchestrator_agent/langgraph_runner/
├── compiler.py
├── runner.py
├── state.py
├── subgraph.py
├── result_waiter.py
├── checkpointer.py
└── reflexion_graph.py
```

## 当前调用链

- `app/api/messages.py` 创建任务后调用 `make_runner(session).start(task_id)`
- `app/api/hitl.py` 通过 `resolve_hitl(...)` 恢复或改写当前中断
- `app/api/tasks.py` 提供 `rollback` 和 `history` 端点
- `app/main.py` 启动时初始化 LangGraph checkpointer

## 直接收益

- `interrupt()` / `Command(resume=...)` 负责 HITL 暂停和恢复
- `AsyncPostgresSaver` 负责 checkpoint 持久化
- `aget_state_history()` 和 `aupdate_state(...)` 直接支撑回滚和改方向
- `Send(...)` 和条件边负责并行 step 与动态推进

## 不变的边界

- 不用 LangGraph 直接替代 Redis Stream 派发
- 不把 MCP server 内联进 runner
- 不把大产物内容塞进 state，state 里只保留引用

## 后果

优点：

- 编排路径单一，代码和文档更一致
- 回滚、历史和恢复能力成为一等能力
- API 层不再需要 feature flag 或双轨判断

代价：

- 不再保留切回旧 runner 的低成本回退路径
- 任何编排层问题都需要直接在 LangGraph 实现上修复

## 迁移结果

本次清理同时完成了这些收敛动作：

- 删除 `agents/orchestrator_agent/runner.py`
- 删除 `backend/app/services/result_consumer.py`
- 删除旧 runner 专属测试
- 移除 `USE_LANGGRAPH_RUNNER` 配置分支
- 更新启动链路、API 注释和说明文档
