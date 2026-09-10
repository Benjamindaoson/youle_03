# 决策：是否将 `SkillRunner` 迁移到 `agno.Workflow`

- **日期**：2026-05-15
- **决策**：**Go**（建议迁移）—— 但**分两期**，MVP 期不动现有引擎
- **复现**：`python tmp/spike_workflow.py`（agno==2.6.5）

---

## 1. 背景

`src/skills/engine.py` 自研了一个 `SkillRunner`（~490 LOC），承担：

- Step 串行执行 + prompt 变量替换
- 3 个 HITL Gate（`version_select` / `quality_review` / `final_approval`）
- 流式事件发布（`WorkflowStep*` domain events → SSE）
- Artifact / Brief 持久化钩子

Agno 2.6.5 在 `agno.workflow` 下已提供同类原语（`Workflow` + `Step` +
`HumanReview`）。问题：**Agno 的 HITL 模型能不能干净映射到我们现有的 3 个 Gate
语义**？这是「迁移 vs 继续自研」的关键未知，spike 就是为它而做。

## 2. 测试方法

写一个**不依赖 LLM/网络**的最小 workflow（`tmp/spike_workflow.py`）：
3 个 Step 的纯 Python executor，中间 Step 配 `HumanReview(requires_output_review=True,
on_reject=OnReject.cancel)`。跑 4 个场景，全部 `assert` 验证。

## 3. 测试结果（验收契约 4/4 通过）

| # | 契约 | Agno API | 实测 |
|---|------|----------|------|
| 1 | 流式可对接 | `wf.arun(..., stream=True, stream_events=True)` | ✅ 收到 `WorkflowStartedEvent` / `StepStartedEvent` / `StepOutputEvent` / `StepCompletedEvent`，Step 级粒度满足前端 `AgentPanel` 右栏需求 |
| 2 | Gate 在 Step **完成后** 打开 | `Step(human_review=HumanReview(requires_output_review=True))` | ✅ `run.is_paused=True`，`status=paused`，下一 Step 未执行 |
| 3 | "modified" 决策能注入下一 Step | `requirement.edit(new_content)` | ✅ 下游 Step 看到的是修改后的内容，原始草稿被完全覆盖 |
| 4 | "cancelled" 干净终止 | `requirement.reject()` + `on_reject=OnReject.cancel` | ✅ 下一 Step 未执行，`status=cancelled` |

完整运行输出：

```
── 场景 A：confirm ──
  ✓ workflow 在 draft 后挂起 (status=RunStatus.paused)
  ✓ gate 挂在正确的 step: draft
  ✓ publish 看到原始草稿，final status=RunStatus.completed
── 场景 B：edit（modified） ──
  ✓ publish 收到的是修改版（原始草稿已被覆盖）
── 场景 C：reject（cancelled） ──
  ✓ publish 没有执行，final status=RunStatus.cancelled
── 场景 D：streaming（验证 Step 事件可消费） ──
  ✓ 收到 8 个事件: ['WorkflowStartedEvent', 'StepStartedEvent', 'StepOutputEvent',
                   'StepCompletedEvent', 'StepStartedEvent', 'StepOutputEvent', ...]
✅ ALL 4 ACCEPTANCE CRITERIA PASSED
```

## 4. 对照映射表

| 我们现有概念 | Agno 对应 |
|------------|-----------|
| `SkillStep` | `agno.workflow.Step` |
| `SkillDefinition.steps: list[SkillStep]` | `Workflow(steps=[...])` |
| `AgentInvoker.invoke()` | `Step(agent=...)` 或 `Step(executor=callable)` |
| `gate_type=version_select/quality_review/final_approval` | `HumanReview(requires_output_review=True, output_review_message=...)` |
| `HITLGateRegistry.open()` + `asyncio.Future` | `run.is_paused` + `run.steps_requiring_output_review` + `wf.continue_run(run)` |
| `decision == "approved"` | `requirement.confirm()` |
| `decision == "modified"` (输出覆盖) | `requirement.edit(new_content)` |
| `decision == "cancelled"` | `requirement.reject()` + `on_reject=OnReject.cancel` |
| `WorkflowStartedEvent / WorkflowStepStartedEvent / WorkflowStepStreamingEvent / WorkflowStepCompletedEvent` | Agno 同名/近名 streaming events |
| `step_outputs[sid]` 模板替换 | `StepInput.previous_step_content` / `get_step_content(name)` |

**唯一非平凡的转换**：`step.prompt_template` 的 `{user_input}` / `{step:<id>}`
占位符在 Agno 模式下要通过 `StepInput.previous_step_content` 拉取，或者把替换逻辑放
进 `executor=` 包装函数里。这是一次性的工程工作，不影响可行性结论。

## 5. 决策与执行计划

### 决策：迁移可行，**但分两期**

**MVP 期（即现在）**：**不动** `SkillRunner`。理由：

- 它已对接 EventBus、HITL Future、ArtifactSink、BriefSink，跑得通
- 切换有不可忽略的工程量（事件名映射、`HITLGateRegistry` 的 Future 模型 ↔ Agno `requirement` 模型的双向桥接）
- MVP 当前阻塞项是「auto 模式 + 小红书 Skill 端到端跑通 + 前端联调」，不是引擎选型

**MVP 上线后（V1）**：迁移到 `agno.Workflow`。理由：

- 减少 ~490 LOC 自研代码
- 拿到 Agno session DB 提供的工作流恢复（多 worker 部署时的关键依赖）
- 拿到 `Loop` / `Parallel` / `Router` / `Condition` 这些后续 Skill 用得上的原语，不用再自己实现
- 与铁律 4 兼容：让 `src/skills/` 仅保留 YAML manifest + 提示词，把 Agno 适配放在 `src/teams/group.py` 或新建 `src/skills_runtime/`（**不**在 `src/skills/` 里 import agno）

### V1 期迁移粒度

1. 新建 `src/skills_runtime/agno_runner.py`：把 `SkillDefinition` 编译成 `agno.Workflow`
2. `gate_type` → `HumanReview` 映射表
3. `HITLGateRegistry` 改造成 Agno `requirement` 的桥接：API 收到 `approve/modify/cancel/rollback` 时映射成 `confirm/edit/reject`，然后 `wf.continue_run(...)`
4. Streaming 事件适配：Agno `StepStartedEvent` → 我们的 `WorkflowStepStartedEvent`（保持 SSE 契约 §7.4 不变）
5. 灰度切换：旧 `SkillRunner` 保留 1 个版本周期，用 feature flag 路由；2 周稳定后删除

## 6. 留给后续的待答问题（不阻塞当前结论）

- Agno 的 session DB（默认 SqliteDb）能否承载我们的多会话吞吐？需要在 V1 期间做压测。
- 同时跑 Agno workflow session + 我们自己的 Postgres `events` 表，是否会出现状态不一致？需要明确"谁是 source of truth"（结论应该仍是 Postgres `events`，Agno session DB 只做工作流执行态缓存）。
- `OnTimeout` 默认 `cancel`，我们 §7.2 约定 HITL gate 超时 3600s。需要在迁移期把 `hitl_timeout=3600` 显式配上。

## 7. 工件

- Spike 代码：`tmp/spike_workflow.py`
- SQLite 输出：`tmp/spike_dbs/spike_{confirm,edit,reject,stream}.db`（可删）
