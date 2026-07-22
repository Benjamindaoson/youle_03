# ADR-020: Critic Loop —— 创作 step 自动评审 + 一次重派

**状态**: Accepted (B 阶段已落地)
**日期**: 2026-05-09
**关联**: ADR-017(LangGraph 唯一内核)、ADR-019(Planner Agent)、ADR-021(Step Persona)、ADR-018(Group multi-agent)

## 结论

任何创作类 step(`long_writing` / `short_video_script` / `xhs_carousel_copy` / ...)
完成后,**LangGraph 节点自动执行评审**;不达阈值则携带反馈**重派一次**;
仍不达标则把 critique 落到 `step_result["critique"]`,主流程不阻塞。

- **flag 控制**:`ENABLE_CRITIC_LOOP=false` 默认关 — production 行为完全不变
- **task_type 白名单**:文本类创作默认开,图像 / 视频走专属 quality_check
- **Skill YAML 可逐步覆盖**:`step.critic.{enabled,threshold,max_retries,rubric}`
- **零阻塞**:critic 自身故障(LLM 挂 / JSON 解析失败 / 取产物失败)→ `passed()=True`

## 背景

ADR-017 已落地静态 YAML 编排 + ADR-019 引入动态规划,但缺一环:**质量保障**。

2026 年硅谷一线产品(Sierra / Cognition / Devin)的共识:
> 任何创作 step 后接一个 critic step,质量直接 +1 档,成本只增 10-20%。

我们的现状:
- 短视频 / 详情图等高 ROI 任务质量靠 HITL gate 兜底 → 用户负担重
- 飞轮信号停留在"成功 / 失败"的二元判断 → 没有"完成但质量差"这种宝贵的中间态

## 决策

### 1. 评审在 LangGraph 节点内嵌,而不是单独节点

**为什么不做成独立的 critic StateGraph 节点?**

候选方案 A(独立节点):
```
step_a → critic_a → step_b
              ↓ 不过则回 step_a
```
优点:time-travel 友好,critic 状态可见
缺点:graph 拓扑变复杂,需要新增 conditional edges,跟 ADR-017 的固定 router 模式分叉

候选方案 B(节点内嵌)✓ 我们选这个:
- compiler.py 的 `_make_step_node._node()` 在 worker 成功后追加 critic 块
- 行为完全本地化,topology 不变
- 与现有 retry 循环正交(retry 处理 worker failed,critic 处理 worker completed-but-low-quality)

### 2. critic 调认知层模型(ADR-019)

不复用 task_type 路由 — critic 是评审任务,需要稳定 + 强推理 → 走
`agents._common.llm.complete_cognitive(purpose="critic", ...)`,默认 sonnet-4-6。

### 3. 重试策略

- 默认 `CRITIC_MAX_RETRIES=1` — 单次重派,不允许 critic 自己变成无限循环
- 重派时 prompt 自动追加 `[Critic 反馈]` 段,worker 看到反馈重生成
- 多轮重派**不累加**反馈段(正则剥旧块,只保留最新一轮)
- `idempotency_key` 含 `c{n}` 后缀,worker 端 dedup 不会误判幂等

### 4. critic 故障 = passed

`CritiqueResult.skipped_reason` 非空 → `passed()=True`。
理由:critic 是**质量保障**而不是**质量门禁**,它挂了不能让正主任务挂。
Skill 若需强门禁,用 HITL gate(那是阻塞式的、有人介入)。

### 5. critique 落地为 step_result 的子字段

`step_result["critique"] = critique.to_dict()`(StepResult TypedDict 已加该字段)。
这个字段是飞轮的关键饲料:
- ADR-019 的 replanner 在 S2 接通后会读它,决定是否调起 replan
- ADR-G(Reflexion ↔ Critic 联动)会扫低分 critique 产 prompt 改进候选

## 模块结构

```
agents/agents/orchestrator_agent/langgraph_runner/
├── critic_node.py             ← 新增
│   ├── CritiqueResult         (dataclass)
│   ├── evaluate(...)          (调认知层 LLM,产 critique)
│   ├── build_retry_prompt(...) (反馈拼回 prompt)
│   ├── is_critic_enabled_for(task_type, step_def)
│   ├── get_threshold / get_max_retries
│   └── CRITIC_DEFAULT_ON_TASK_TYPES
│
├── compiler.py                ← 微创式 patch
│   └── _make_step_node._node()
│       └── 在 pending_external 循环后、step_result 构造前
│           插入 critic 块(flag-gated)
│
└── state.py                   ← StepResult 加 critique 字段
```

## 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `ENABLE_CRITIC_LOOP` | `false` | 全局开关 |
| `CRITIC_THRESHOLD` | `0.7` | 默认阈值 |
| `CRITIC_MAX_RETRIES` | `1` | 默认 critic 驱动重派上限 |
| `CRITIC_TIMEOUT_S` | `30` | 单次评审超时 |

Skill YAML 单 step 可覆盖:
```yaml
- step_id: script
  agent: agent_1
  task_type: long_writing
  critic:
    enabled: true            # 显式开启,即使全局 off
    threshold: 0.85
    max_retries: 2
    rubric: |
      1. 开头钩子有冲突感
      2. 每段案例含真实数字
      3. 结尾呼吁清晰
```

## 默认开启的 task_type

```python
CRITIC_DEFAULT_ON_TASK_TYPES = {
    "short_writing", "long_writing", "structured_writing", "short_video_script",
    "xhs_carousel_plan", "xhs_carousel_copy", "xhs_delivery_summary",
    "web_search",
}
```

图像 / 视频不在范围 — 它们有专属 `image_quality_check` step + HITL 终审。

## 与 ADR / 铁律兼容性

| ADR / 铁律 | 兼容 | 说明 |
|---|---|---|
| ADR-002(Worker 不互调)| ✓ | critic 走 LangGraph 节点内嵌的认知层调用,worker 边界不变 |
| ADR-009(MCP-first)| ✓ | critic 不调 MCP,纯 LLM 评估 |
| ADR-017(LangGraph 唯一内核)| ✓ | 仅在 _node 内增量,topology 不变 |
| 铁律 4(产物用引用)| ✓ | critic 只读产物 excerpt,不重新落 OSS |
| 铁律 7(走 LiteLLM)| ✓ | complete_cognitive 走同一 proxy |

## 测试

`agents/tests/unit/`:
- `test_critic_node.py` — 纯单元(策略 / 阈值 / build_retry_prompt 不累加 / mock 通过路径)
- `test_critic_loop_runtime.py` — 用 InMemorySaver 真跑 LangGraph,验证:
  - flag off → 行为完全不变
  - critic pass → 1 次派发,critique 落地
  - critic 一次不过 → 重派 + prompt 含反馈 + 最终采用重派结果
  - critic 始终不过 → max_retries 命中后 step 仍 completed,critique 落地为低分
  - step.critic.enabled=true 在 flag off 时仍生效

## 风险

| 风险 | 缓解 |
|---|---|
| critic 把质量好的产物误判低分 → 重派浪费成本 | 默认 `max_retries=1`;低分阈值 0.7 偏宽容;有 1 周灰度看数据再调 |
| critic 自身挂导致主流程挂 | `skipped_reason` → `passed()=True`,主流程不阻塞 |
| 反馈在 prompt 累加导致雪球 | 正则 `_CRITIC_FEEDBACK_BLOCK` 在 build_retry_prompt 时剥旧块 |
| 与 HITL gate 冲突(HITL 已经审了又被 critic 重派)| critic 在 `pending_external` 之后、HITL gate 之前;HITL 看到的产物已是 critic 通过的最终版 |

## S2 后续

- ADR-G:Reflexion 扫低分 critique 产 prompt 改进候选(写飞轮)
- ADR-019 的 replanner 接收 critique → 决定是否 replan(读飞轮)
- 图像 / 视频 critic(S3,需要多模态认知层)
