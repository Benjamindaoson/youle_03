# ADR-027: Eval 评测体系

**状态**: Skeleton(本地 harness 完成;CI 集成 + live executor 留 S2)
**日期**: 2026-05-09
**关联**: ADR-019 (Planner)、ADR-020 (Critic)、ADR-026 (browser/code MCP)

## 结论

新增 `agents.eval` 包,提供:

- **Golden Suite 加载**:从 YAML fixture 目录加载评测 case,字段错误的文件跳过 + 警告
- **打分规则**:7 条规则加权打分(final_status / must_have_steps / artifact_types / primary_artifact / cost_cap / duration_cap / critic_pass)
- **Suite Runner**:顺序或并发跑整套 case,产 `SuiteReport`,可序列化、可作 CI 卡门槛
- **Mock Executor**:默认实现让 fixture 自检不连任何外部
- **真 Executor 接口**:`CaseExecutor` 是 `Callable[[EvalCase], Awaitable[dict]]`,
  调用方注入 LangGraph 驱动的 executor 即可

## 背景

S 档系统的最后一公里:**没有 eval 就没有进步**。我们已经做了 ADR-019..026
所有的"能力",但没有度量,无法判断:
- 改一个 prompt 后整体好了还是坏了
- 加 critic 后真的提升 1 档了吗
- Planner 灰度到 5% 流量时和 YAML 路径比谁更便宜
- 模型从 sonnet-4-6 切到 opus-4-7,值不值

ADR-027 提供这套度量基建。

## 决策

### 1. Golden Suite + 加权打分

```yaml
case_id: short_video_basic
description: 短视频 happy path
tags: [video, hero, short_video]
input:
  user_request: 给我做一个城市夜景短视频
  collected_fields:
    年份: 2026
    主题: 城市夜景
    受众: 城市老人
    时长: 60s
expected:
  must_have_steps: [research, script, image_process, bgm, video_compose]
  must_have_artifact_types: [text, image_collection, video]
  primary_artifact_step: video_compose
  max_total_cost_usd: 10.0
  max_p95_duration_s: 600
  must_pass_critic: false
  min_score: 0.7
budget:
  total_cost_usd: 8.0
  total_duration_s: 480
```

打分规则 + 默认权重(`metrics.score_case`):

| 规则 | 权重 |
|---|---:|
| final_completed(任务整体成功)| 0.35 |
| must_have_steps(步骤覆盖)| 0.25 |
| must_have_artifact_types(产物类型覆盖)| 0.10 |
| primary_artifact(主产物 step 通过)| 0.10 |
| cost_cap(成本不超)| 0.10 |
| duration_cap(延迟不超)| 0.05 |
| critic_pass(若声明 must_pass_critic)| 0.05 |

每条规则 0..1,加权后总分。`passed = score >= min_score && final_status == "completed"`。

### 2. Executor 注入,不耦合

`run_suite(suite, executor=my_exec)` — 调用方提供:

```python
async def my_exec(case: EvalCase) -> dict:
    """跑一次 case,返回 LangGraph final_state。"""
    plan = await make_plan(...)        # ADR-019
    builder = build_state_graph_from_plan(plan, ...)
    graph = builder.compile(checkpointer=InMemorySaver())
    state = make_initial_state(...collected_fields = case.collected_fields)
    return await graph.ainvoke(state, config={"configurable": {"thread_id": case.case_id}})
```

不写死 executor,因为 production / mock / shadow 三种 mode 的 executor 不同:
- `mock`:LITELLM_MOCK=true,LangGraph 编译 + ainvoke,所有 LLM 走 fixture
- `live`:真调认知层 + worker(贵,只在 release pipeline 跑)
- `shadow`:5% 真流量旁挂(S2 + backend 配合;本 ADR 不覆盖)

S1 `_make_mock_executor` 是 fallback,让本 ADR 的单测自洽。

### 3. CI 集成(S2)

production CI 加一个 job:
```yaml
- name: eval-mock
  run: |
    cd agents
    uv run python -m agents.eval.cli  # S2 加 cli.py
    # 卡 pass_rate >= 0.8 + 平均 score >= 0.75
```

S1 没写 CLI,`run_suite` 已经够 CI 调用。

### 4. SuiteReport 是 source of truth

`SuiteReport.summary_text()` 给人看,`.cases` 是结构化数据,可序列化为 JSON
喂给 Grafana / 飞书机器人。

## 模块结构

```
agents/agents/eval/
├── __init__.py
├── golden.py              # EvalCase + EvalSuite + from_directory + filter_by_tag
├── metrics.py             # score_case + aggregate_report + CaseResult + SuiteReport
├── runner.py              # run_case + run_suite + _make_mock_executor
└── golden/                # YAML fixtures(用户/团队维护)
    ├── short_video_basic.yaml
    └── xhs_note_basic.yaml
```

## 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `EVAL_DEFAULT_TIMEOUT_S` | `600` | 单 case 硬上限 |

## 与 ADR / 铁律兼容性

| ADR / 铁律 | 兼容 | 说明 |
|---|---|---|
| ADR-017(LangGraph 唯一内核)| ✓ | eval 通过 executor 复用 LangGraph,不分叉 |
| ADR-019(Planner)| 协同 | live executor 可走 dynamic plan |
| ADR-020(Critic)| 协同 | `must_pass_critic` 是评分维度之一 |
| ADR-023(Critique 桥)| 互补 | 两个东西做不同事:23 是飞轮反馈,27 是质量度量 |

## 测试

`agents/tests/unit/test_eval_harness.py` — 25+ cases:
- 加载:正常 / 缺字段跳过 / 坏 YAML 跳过 / 缺目录返回空 / 标签过滤
- 打分:perfect run / 缺 step / failed status / 成本超限 / critic 通过率 / skipped 不计
- Runner:executor 异常 catch / 超时 catch / suite 顺序 / suite 并发
- 真仓库:`agents/eval/golden/` 至少有 1 个 case 且 mock executor 都跑得通

## 风险

| 风险 | 缓解 |
|---|---|
| Mock executor 给假阳性 → 真 case 实际跑挂还能 pass | live executor 才是 release gate;mock 只是结构验证 |
| 评分规则权重不合理 → 优化方向跑偏 | 规则 + 权重在 metrics.py 公开,可代码评审调整;每个版本规则变更同时更新 fixture |
| fixture 长期不维护 → eval 失真 | 飞轮:用户长期高/低评分的 case 自动入 fixture(S5) |
| 一个 case 时长 > 10 分钟 拖垮 CI | `EVAL_DEFAULT_TIMEOUT_S=600` 硬上限;CI 只跑 mock + smoke 子集,live 单独 schedule |

## S2 后续

- `agents/eval/cli.py`:`python -m agents.eval` 启动,产 JSON / Markdown 报告
- 真 LangGraph executor 实现(基于 InMemorySaver + dispatcher mock)
- Shadow traffic:复用真 worker / 真 LLM,5% 流量旁挂
- Grafana 看板:每 release 后写入 metrics
- Fixture 飞轮:从生产环境的高/低用户评分 case 自动产 fixture 草稿
