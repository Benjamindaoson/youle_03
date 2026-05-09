# ADR-024: S2 集成路径(Planner / Critique-Signal / 飞轮闭环)

**状态**: Partial(agents 端已落,backend 端待办清单见下)
**日期**: 2026-05-09
**关联**: ADR-019(Planner)、ADR-020(Critic)、ADR-023(Critique→Reflexion 桥)

## 结论

把 ADR-019 / 020 / 023 的"骨架"接通生产链路。**agents 端**:
- `runner.py` 在任务 finalize 后调 `scan_and_emit_from_state(state)` 把 critic
  低分 step 推到 flywheel:signals(默认 `ENABLE_CRITIQUE_SIGNAL_EMIT=true`,
  graceful — Redis 挂不阻塞)

**backend 端**(本仓库不动,留 TODO 给团队):
1. `messages.py`:Skill 不命中或匹配置信度 < 0.6 时,调 `agents.orchestrator_agent.planner.entry.plan_and_compile()`,把返回的 `skill_yaml_dict` 注入 task.parameters 后启动 runner
2. `prompt_improvement_candidates` 表加 `source` 列(VARCHAR(32),nullable),区分 `step_failed` / `critic_low_score` / 未来 `user_low_rating`
3. backend 的 reflexion runner 把 payload 里的 `source` 字段透传到入库行
4. `flywheel/promoter.py`:按 `source` 分桶统计成功率;`critic_low_score` 来源走更激进的 A/B 流量

## 背景

ADR-019 / 020 / 023 已完成"读 / 处理 / 桥接",但生产链路里:
- messages.py 仍只走 Skill YAML 路径,Planner 不被调起
- runner.py finalize 不发 critique signal,飞轮"写"端断了
- backend 的 reflexion runner 不识别新 source 字段

不接通 = 飞轮空转。本 ADR 接通最后一环。

## 决策

### 1. agents 端:runner.py 在 _finalize_task_db 内尾部加调用

```python
# 在 flywheel.emit_trace 之后、ws publish 之前:
if os.getenv("ENABLE_CRITIQUE_SIGNAL_EMIT", "true").lower() in {"1","true","yes"}:
    try:
        from agents.orchestrator_agent.langgraph_runner.critique_signal import (
            scan_and_emit_from_state,
        )
        n_emitted = await scan_and_emit_from_state(state)
        if n_emitted:
            log.info("lg.critique_signal.emitted", task_id=..., n_signals=n_emitted)
    except Exception as e:
        log.warning("lg.critique_signal_emit_failed", err=str(e))
```

为什么默认开:
- ADR-020 的 Critic Loop 默认**关**,所以默认情况下不会有 critique 字段产生 → emit 扫描结果空 → 零成本
- 只要 critic 没开,这一行就是 no-op
- 一旦 critic 开,飞轮就立即跑起来

为什么不在 messages.py 集成 Planner:
- messages.py 在 backend(`backend/app/api/messages.py`),agents-only 边界下不能改

### 2. backend 端 TODO(留给团队)

#### TODO-1: messages.py 调用 Planner

现状 messages.py(伪代码):
```python
# Skill 匹配
skill = await skill_matcher.match(user_request)
if skill is None or skill.confidence < 0.5:
    # 当前:回澄清流程或拒答
    await ask_clarification(...)
    return
task = create_task(skill.yaml, ...)
await runner.start(task)
```

S2 改造:
```python
from agents.orchestrator_agent.planner.entry import (
    is_dynamic_plan_enabled,
    plan_and_compile,
)
from agents.orchestrator_agent.langgraph_runner.runner import (
    LangGraphTaskRunner,
)

skill = await skill_matcher.match(user_request)
if skill is None or skill.confidence < 0.5:
    if is_dynamic_plan_enabled():
        try:
            plan, skill_yaml_dict, builder = await plan_and_compile(
                user_request=user_request,
                user_id=str(user.id),
                collected_fields=collected,
                dispatcher=dispatch_task,           # backend 已有
                result_waiter=wait_for_step_result, # backend 已有
            )
        except PlannerError:
            await ask_clarification(...)  # planner 失败回澄清
            return
        # 把 skill_yaml_dict 当作 skill 走 runner
        task = create_task_from_dynamic(plan, skill_yaml_dict, ...)
        await runner.start(task)
        return
    else:
        await ask_clarification(...)
        return
# Skill 命中:走原有 YAML 路径
task = create_task(skill.yaml, ...)
await runner.start(task)
```

灰度策略:
- 第 1 周:`ENABLE_DYNAMIC_PLAN=false`(默认),完全等同当前行为
- 第 2 周:5% 流量开启,Grafana 看 plan 质量 / 成本 / 用户满意度
- 第 3 周后:看数据决定 100% / 调整阈值 / 改 Planner prompt

#### TODO-2: prompt_improvement_candidates 加 source 列

```sql
-- alembic migration
ALTER TABLE prompt_improvement_candidates
  ADD COLUMN source VARCHAR(32) NULL,
  ADD COLUMN extra_metadata JSONB NULL;

CREATE INDEX idx_pic_source ON prompt_improvement_candidates(source);
```

枚举值:`step_failed` / `critic_low_score` / 未来扩展。

#### TODO-3: reflexion runner 透传 source

backend 的 reflexion runner 消费 `flywheel:reflexion` stream 时,把 payload 的
`source` 与 `metadata` 传入 process_reflexion_event,在 _persist 节点写入新列:

```python
# backend/agents.../reflexion_graph.py 的 _persist 节点(后改)
cand = PromptImprovementCandidate(
    ...,
    source=state.get("source"),                     # NEW
    extra_metadata=state.get("extra_metadata") or {},  # NEW
)
```

ReflexionState 同步加字段。

#### TODO-4: promoter 按 source 分桶

`backend/flywheel/promoter.py`(若已存在,否则 S2 新建):
```python
async def daily_promote() -> None:
    # critic_low_score 来源:积极晋升(A/B 流量 5%)
    crit_candidates = await fetch_pending(source="critic_low_score", limit=10)
    for c in crit_candidates:
        await schedule_ab_test(c, traffic_pct=0.05)
    # step_failed 来源:保守晋升(只在人工审核后才上)
    # 或者按 success rate 自动路由
```

## 配置(agents 端)

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `ENABLE_CRITIQUE_SIGNAL_EMIT` | `true` | runner.py 是否调 scan_and_emit_from_state |
| `REFLEXION_FROM_CRITIQUE_MAX_SCORE` | `0.6` | (ADR-023)只有 score 低于这个才入 reflexion |
| `REFLEXION_FROM_CRITIQUE_MAX_PER_TASK` | `5` | (ADR-023)单任务上限 |
| `ENABLE_DYNAMIC_PLAN` | `false` | (ADR-019)上游 messages.py 是否调 Planner |

## 与 ADR / 铁律兼容性

| ADR / 铁律 | 兼容 | 说明 |
|---|---|---|
| ADR-002(Worker 不互调)| ✓ | 仅在主编排层加调用 |
| ADR-011(Qdrant 轨迹)| ✓ | 不改 trace 写入 |
| ADR-017(LangGraph 唯一内核)| ✓ | 仅在 runner.py 尾部加调用,不动 graph |

## 风险

| 风险 | 缓解 |
|---|---|
| critique signal 调用挂掉影响主任务 finalize | try/except 包裹,异常只 log,不向上抛 |
| 默认 ON 引入意外行为 | critic 默认关 → emit 扫描结果空 → 零影响;且可单 flag 关 |
| backend 升级前 emit 进了 stream 但下游不识别 source | source 字段是 payload 的额外字段;旧 reflexion runner 消费 reflexion 信号时不会因为多字段崩(payload 是 dict),只是不写新列 — 等 backend 跟进就生效 |
