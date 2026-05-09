# ADR-023: Critique → Reflexion 桥接

**状态**: Accepted (G 阶段已落地)
**日期**: 2026-05-09
**关联**: ADR-011(Qdrant 工作流轨迹)、ADR-020(Critic Loop)、`reflexion_graph.py`(既有)

## 结论

ADR-020 的 Critic Loop 把"完成但低质量"的 step 落到 `step_result["critique"]`,
本 ADR 接通这个**写端飞轮**:

- 任务完成后,`critique_signal.scan_and_emit_from_state(state)` 扫所有 step 的
  critique,把 `score < 0.6` 的 step 转换为 reflexion payload 并 push 到
  `flywheel:signals` Redis Stream
- 走和"任务级 failed"完全相同的下游链路 — backend 的 reflexion runner
  消费,LLM 产 prompt 改进建议,落 `prompt_improvement_candidates`
- payload 多一个 `source: "critic_low_score"` 字段,便于晋升器(S2)对两类来源
  分别配置策略

## 背景

ADR-020 在 step_result 里存了 critique,但**没人消费**。这是飞轮闭环的最后一公里:
- **失败任务**:reflexion_graph.py 已经在产候选 ✓
- **完成但质量差**:数据躺在那,没产候选 ✗(ADR-023 解决这个)

> 2026 年硅谷一线产品(Sierra / Cognition)把"完成但用户低分"和"完成但 critic 低分"
> 视为更宝贵的飞轮饲料 — 失败任务往往是基建问题,而低分任务才是 prompt / 流程的问题。

## 决策

### 1. 不修改 reflexion_graph.py

`reflexion_graph.ReflexionState` 的契约就能接住 critique payload:
- `failure_reason`:由 critique 的 score / issues / suggestion 合成
- `trace_excerpt`:由 step_id / artifact_ref / collected_fields / issues 合成
- `prompt_name`:`{skill_id}::step_{step_id}::{task_type}`,与失败路径同 namespace

Reflexion 节点的 LLM 看到 `[critic_low_score]` 标记就知道这是质量改进信号而非
基建故障,会更聚焦在 prompt 层面的改进。

### 2. 走 Redis Stream,不直接调 reflexion_graph

`process_reflexion_event()` 在 backend 里(import 了 `app.db` / `app.models`),
agents-only 边界下不能直接调。所以走原有 `flywheel_emitter.emit(signal_type="reflexion", payload=...)`,
backend 的 `flywheel_consumer` 路由到 `flywheel:reflexion` stream,
backend reflexion runner 消费时调 `process_reflexion_event` —— **下游零改动**。

### 3. 两道防雪崩闸

- `REFLEXION_FROM_CRITIQUE_MAX_SCORE = 0.6`(严于 critic 自己的 0.7 threshold):
  防止小波动(0.65 这种)被当作可改进信号
- `REFLEXION_FROM_CRITIQUE_MAX_PER_TASK = 5`:单任务最多发 5 条信号,按 score
  升序(最差的优先)

### 4. graceful

- Redis 不可用 / `flywheel_emitter` 导入失败 → 静默放弃,**不抛**
- 单条 emit 抛异常 → 跳过该条,继续剩余信号
- state 缺 task_id → 直接返回 0
- step 状态 ≠ completed,或 critique.skipped_reason 非空 → 跳过

## 模块结构

```
agents/agents/orchestrator_agent/langgraph_runner/
├── critic_node.py             (ADR-020,产 critique)
├── compiler.py                (写入 step_result["critique"])
└── critique_signal.py         ← 新增,本 ADR
    ├── CritiqueSignal(dataclass)
    │   ├── prompt_name (property)
    │   ├── failure_reason()
    │   ├── trace_excerpt()
    │   └── to_reflexion_payload()
    ├── extract_critique_signals(...)
    ├── emit_critique_signals(...)
    └── scan_and_emit_from_state(state)  ← 一行调用入口
```

## 集成位置(留待 S2)

S1 阶段**只提供函数**,不在 runner.py 里强制调用 — runner.py 触碰 backend
session 风险高。S2 集成时,在主任务图 finalize 节点完成后加一行:

```python
# agents/orchestrator_agent/langgraph_runner/runner.py(S2 修改)
from agents.orchestrator_agent.langgraph_runner.critique_signal import (
    scan_and_emit_from_state,
)
# ... task finalized
await scan_and_emit_from_state(final_state)
```

或者由 backend 的某个 task-completion hook 调用。任意一边都行 — 这是个无副作用
的 fire-and-forget 调用。

## 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `REFLEXION_FROM_CRITIQUE_MAX_SCORE` | `0.6` | 只有 score 低于这个才入 reflexion |
| `REFLEXION_FROM_CRITIQUE_MAX_PER_TASK` | `5` | 单任务上限 |

## payload 字段约定

```json
{
  "task_id": "t-1",
  "prompt_name": "anti_fraud_video::step_script::long_writing",
  "failure_reason": "[critic_low_score] score=0.35 < threshold=0.70\nissues: 开头钩子无冲突感; ...\nsuggestion: 加真实数字开场",
  "trace_excerpt": "step_id: script\ntask_type: long_writing\nartifact_ref: oss://script.txt\n...\n--- critic issues ---\n- 开头钩子无冲突感",
  "source": "critic_low_score",
  "metadata": {
    "step_id": "script",
    "task_type": "long_writing",
    "skill_id": "anti_fraud_video",
    "score": 0.35,
    "threshold": 0.7,
    "n_issues": 1
  }
}
```

backend 的 reflexion runner 应当把 `source` 透传到 `prompt_improvement_candidates.source`
列(若已有)或 metadata,便于晋升器(S2)对两类来源**分别配置策略**:
- `step_failed` 来源:基建问题居多,改 prompt 收益有限
- `critic_low_score` 来源:prompt / 流程问题,改 prompt 收益最大

## 与 ADR / 铁律兼容性

| ADR / 铁律 | 兼容 | 说明 |
|---|---|---|
| ADR-002(Worker 不互调)| ✓ | 本桥接是主编排层,不引入跨 worker 调用 |
| ADR-011(Qdrant 轨迹)| ✓ | 走 Redis Stream(信号 3 channel),不直接写 Qdrant |
| ADR-017(LangGraph 唯一内核)| ✓ | 不动 graph 拓扑,纯尾部消费 |
| ADR-020(Critic Loop)| 协同 | 消费 ADR-020 写下的 critique 字段 |

## 测试

`agents/tests/unit/test_critique_signal.py`:
- 提取规则:status 过滤、skipped_reason 过滤、score 阈值、按 score 升序、上限
- payload shape:与 reflexion_graph 兼容、含 source 标记、动态 plan 兜底
- emit graceful:flywheel_emitter 不可用 / 单条失败不影响其他
- 端到端:scan_and_emit_from_state 命中 + 不命中 + 缺 task_id

## 风险

| 风险 | 缓解 |
|---|---|
| Reflexion 队列被 critique 信号淹没 | `MAX_PER_TASK=5` + `MAX_SCORE=0.6` 双闸;backend 的 reflexion runner 也有自己的限流 |
| critique 信号质量低(critic 误判)→ 产生噪音候选 | 候选默认 `status=pending` 由人工审,不会自动上线;晋升器(S2)按 source 分桶统计,critic 来源若噪音多可单独提阈值 |
| 同一 step 多次任务 emit 多次相同信号 | reflexion runner 端按 (prompt_name, failure_reason 摘要) 去重(已有逻辑);backend 决定 |
| Redis 挂导致信号丢失 | graceful 跳过 + log;workflow_traces(ADR-011)仍在 Qdrant 留了 source-of-truth,可批量回填 |

## S2 后续

- 在 `runner.py` 的 task-finalize 路径加一行 `await scan_and_emit_from_state(state)`
- backend 的 reflexion runner 把 `source` 字段透传到 `prompt_improvement_candidates`
- 晋升器(`flywheel/promoter.py`):按 source 分桶统计 success rate,critic 来源
  的候选可走更激进的 A/B 流量
