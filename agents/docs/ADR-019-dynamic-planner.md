# ADR-019: Planner Agent 与动态规划路径

**状态**: Accepted (S1 骨架已落地)
**日期**: 2026-05-09
**关联**: ADR-001-rev(4 Worker 边界)、ADR-002(Worker 不互调)、ADR-009(MCP-first)、ADR-011(Qdrant 工作流轨迹)、ADR-017(LangGraph 唯一内核)

## 结论

主编排引入**动态规划路径**:

- 当用户请求未命中任何 Skill Playbook(YAML)或匹配置信度低于阈值时,
  调 **Planner Agent** 用认知层模型(Opus / GPT-5 级)产出 `Plan(JSON)`。
- `Plan` 经 `dynamic_compiler` 翻成 LangGraph StateGraph,**复用**
  ADR-017 的 `LangGraphTaskRunner` 全部下游基建(节点工厂、HITL、
  failure_handling、router、checkpointer、result_waiter)。
- production 路径(Skill 命中走 YAML)默认行为完全不变,由
  `ENABLE_DYNAMIC_PLAN` 环境变量控制,**默认关闭**。

## 背景

ADR-017 把主编排收敛到 LangGraph + Skill YAML 双轨:

- Skill YAML 定义产线工艺,引擎照单执行
- 优点:可预测、可审计、HITL 位置明确、成本可控
- 缺点:**只能跑 YAML 已经写过的工作流**

随着用户开放式请求增加,YAML 命中率不足。2026 年硅谷一线
(OpenAI Swarm / Anthropic Claude Skills + Task tool / Devin / Manus)
的共识是:

> **Plan 是数据,不是代码**。LLM 动态产 plan,引擎执行。
> 旧的 YAML 不丢 — 它降级为"产线",dynamic plan 升为"大脑"。

我们的现状(无 dynamic 路径)将无 Skill 命中的开放任务成功率压在 ~35%,
而本次升级目标是 ≥ 75%。

## 决策

### 1. 双轨并行,Skill 命中优先

```
用户请求
   │
   ▼
意图识别 + Skill 匹配(messages.py)
   │
   ├─ 命中且置信度高    ─────► YAML 路径(原有,不动)
   │
   └─ 不命中 / 低置信度
                            │
                            ▼   (S2 集成)
                       Planner Agent
                            │
                            ▼
                          Plan(JSON)
                            │
                            ▼
                      dynamic_compiler
                            │
                            ▼   (与 YAML 路径汇合)
                    LangGraphTaskRunner
```

### 2. Plan 是 skill_yaml 的子集

`Plan.to_skill_yaml()` 产出的 dict 与 `agents/skills/*.yaml`
解析后**同 shape**,可直接喂给 `compiler.build_state_graph()`。

这是"复用而不分叉"的关键 — 不引入新引擎,只新增"input source"。

```python
# YAML 路径
skill_yaml = yaml.safe_load(open("short_video.yaml"))
graph = build_state_graph(skill_yaml, dispatcher=..., result_waiter=...)

# Dynamic 路径
plan = await make_plan(user_request="...", user_id="...")
graph = build_state_graph_from_plan(plan, dispatcher=..., result_waiter=...)
                # ↑ 内部:plan.to_skill_yaml() → build_state_graph(...)
```

### 3. 认知层模型解耦于 task_type 路由

新增 `agents._common.llm.complete_cognitive()`:

- 永远走 `COGNITIVE_TIER`(默认 `claude-sonnet-4-6`,备 `gpt-5` / `kimi-k2`)
- 不读 `AGENT_ROUTING`(那张表是按 task_type 选执行模型)
- 用途:Planner / Replanner / Critic(S2)/ Reflexion(S2)/ 中断分类

理由:认知层用量小但极度影响质量。Planner 用便宜模型 = plan 质量塌方,
下游再优化也白搭。预计认知层占总成本 < 15%。

### 4. Subagent spawn 是主编排层原语,**不**违反 ADR-002

ADR-002:Worker 不互相调用。
ADR-019 新增 `Subagent.spawn(goal, persona, return_schema)`:

- **只能由主编排层调用**(Planner / Critic / 主 ReAct loop 的特定节点)
- S1:内存级实现 — 直接调认知层 LLM,产 structured JSON 返回
- S3 升级:递归子图 — 子任务跑独立 LangGraphTaskRunner,父任务在节点里
  await 子图

Worker 仍然只能通过 Redis Streams + AgentTask 协议被主编排派单 —
ADR-002 的边界完全保留。

### 5. Replanner 在失败时被调起

`replan(original_plan, failed_step_id, ...)`:

- 已完成 step 的 step_id 必须保留 → LangGraph state 视为 completed,
  自动跳过(compiler.py 的 `_node` 第 142 行 skip_completed 逻辑)
- Replan 次数有上限(`REPLANNER_MAX_REPLANS=2`),超过即任务 fail
- `Plan.source` 字段区分 "planner" / "replanner",便于飞轮信号

### 6. 情景记忆(C 阶段已实装,见 ADR-022)

`episode_retrieval.retrieve_similar_episodes()`:

- ~~S1:返回 `[]`,production 不依赖~~
- **C 阶段已落地**:接通 `agents._common.qdrant_client`,top-K 召回相似历史任务的 plan + outcome,送进 Planner prompt(默认 flag 仍关 — `ENABLE_EPISODE_RETRIEVAL=false`)
- 这一行改完,Planner 立刻具备"经验" — 用户用得越多越懂他

ADR-011 已经在落数据但没反哺 — ADR-019 + ADR-022 把这个金矿打开。

## 模块结构

```
agents/agents/orchestrator_agent/
├── planner/                          ← 新增
│   ├── __init__.py
│   ├── plan_schema.py                # Pydantic 模型 + to_skill_yaml()
│   ├── prompts.py                    # PLANNER / REPLANNER system prompt
│   ├── episode_retrieval.py          # C 阶段已接 Qdrant
│   ├── planner_agent.py              # make_plan() 主入口
│   ├── replanner.py                  # replan() 失败重规划
│   ├── subagent.py                   # Subagent.spawn() 原语
│   └── entry.py                      # plan_and_compile() 集成桥
│
├── langgraph_runner/
│   ├── compiler.py                   # 不动
│   └── dynamic_compiler.py           ← 新增,4 行调用 build_state_graph
│
└── runner_factory.py                 ← 加 is_dynamic_plan_enabled()
```

## 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `ENABLE_DYNAMIC_PLAN` | `false` | 全局开关,S1 不开启 |
| `COGNITIVE_PRIMARY_MODEL` | `claude-sonnet-4-6` | 认知层主模型 |
| `COGNITIVE_FALLBACK_MODEL` | `gpt-5` | 认知层备模型 |
| `PLANNER_MAX_RETRIES` | `2` | LLM 输出无效时重试次数 |
| `REPLANNER_MAX_REPLANS` | `2` | 失败重规划上限 |
| `SUBAGENT_MAX_DEPTH` | `3` | spawn 递归深度上限 |
| `SUBAGENT_DEFAULT_BUDGET_TOKENS` | `4000` | spawn 默认预算 |
| `ENABLE_EPISODE_RETRIEVAL` | `false` | C 阶段已实装,启用前需确认 backend 写入对齐 |
| `EPISODE_RETRIEVAL_TOP_K` | `3` | 情景记忆召回数 |

## 与 ADR / 铁律兼容性

| ADR / 铁律 | 是否冲突 | 说明 |
|---|---|---|
| ADR-001-rev(4 Worker 按媒介)| 否 | Plan 只能用 agent_1..4 |
| ADR-002(Worker 不互调)| 否 | Subagent 是主编排层原语 |
| ADR-009(MCP-first)| 否 | Plan 的 mcp_tools 仍走 MCP 白名单 |
| ADR-011(Qdrant 轨迹)| 强化 | C 阶段把 traces 反哺给 Planner |
| ADR-017(LangGraph 唯一内核)| 否 | dynamic_compiler 委托给 build_state_graph,内核不变 |
| 铁律 4(产物用引用)| 否 | Plan 字段大小受限,大产物仍走 OSS |
| 铁律 7(LiteLLM 调用)| 否 | complete_cognitive 走同一 LiteLLM |
| 铁律 13(Worker 派发走 Redis Streams)| 否 | dispatcher 不变 |

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| Plan 质量不达标(认知模型表现差)| S1 验收先用 mock,实测在 5% 灰度上跑 100+ 真实请求,质量门槛不达标重新设计(可能引入 best-of-N + critic 选优) |
| 成本失控(认知层贵)| 认知层用量极少;Plan 缓存 + Skill induction 把高频动态 plan 凝固为 YAML;按 (purpose × model) 看 Grafana 切片,周成本超阈值告警 |
| 破坏 production 链路 | 双开关(ENABLE_DYNAMIC_PLAN + S2 messages.py 集成点)默认关;dynamic 路径完全独立模块,删除即回滚 |
| Plan 不稳定(同一请求两次产物差异大)| temperature=0.2;PLANNER_MAX_RETRIES=2;replanner 接住失败 |
| 无意识违反 ADR-002 | Subagent 仅供主编排引用;`agents/_common/cross_call.py` 的 NotImplementedError 不动 |

## 已完成的后续(原本列在 S2-S5)

- [x] **B 阶段**(ADR-020):Critic Loop 接入,创作类 step 自动评审 + 重派 1 次
- [x] **C 阶段**(ADR-022):接通 Qdrant 情景检索 + MD Skill 一等公民
- [x] **E 阶段**(ADR-021):Persona 层 — react_runner 读 plan.parameters._planner.persona
- [x] **G 阶段**(ADR-023):Critique → Reflexion 桥接(写飞轮)
- [x] **F 阶段**(ADR-024):agents 端集成 + backend TODO 清单

## 留给后续的事

- [ ] **F 之 backend 端**:`messages.py` 集成 Skill 不命中 → Planner 兜底(ADR-024 列出 TODO)
- [ ] **S2 真接通**:`failure_policy.py` 接入 replanner,重试耗尽改调 replan
- [ ] **S3 sandbox 真隔离**:Subagent 升级为递归子图(配合 ADR-025)
- [ ] **S5 Skill induction**:高复用 dynamic plan 自动蒸馏为 YAML 草稿入 `skill_drafts`

## 测试

单元测试在 `agents/tests/unit/`(C 阶段后从 backend/ 迁出):

- `test_planner_plan_schema.py` — schema 校验
- `test_planner_dynamic_compiler.py` — Plan → StateGraph 链路
- `test_planner_agent.py` — make_plan / replan / subagent / flag
- `test_planner_with_registry.py` — Planner ↔ SkillRegistry 集成(C 阶段新增)

LITELLM_MOCK 下不依赖外部网络。
