# ADR-021: Step Persona —— 能力维度的 Worker 上层人格

**状态**: Accepted (E 阶段已落地)
**日期**: 2026-05-09
**关联**: ADR-001-rev(4 Worker 按媒介)、ADR-019(Planner Agent)、ADR-020(Critic Loop)

## 结论

引入 **Step Persona** —— 与 Worker Persona(ReactPersona)**正交**的能力维度人格。
Planner 在 Plan 里按 step 指定 persona 名字(`researcher` / `critic` /
`fact_checker` / `art_director` / `editor` / `seo_specialist` / `compliance` / `default`),
react_runner 在执行时:

1. 把 persona 的 `addendum` 追加到 system prompt
2. 按 persona 的 `allowed_pattern` / `denied_pattern` 过滤 MCP 工具白名单
3. 按 persona 的 `temperature` 覆盖 ReAct 默认温度
4. 按 persona 的 `forced_artifact_type` / `require_structured_output` 在 prompt 里加约束
5. 按 plan 给的 `budget_tokens` 设置 `max_tokens`(硬上限 32000)

未指定 persona / 指定 unknown → 自动 fallback 到 `default`,**与无 persona 行为完全等同**。

## 背景

ADR-001-rev 把 Worker 按**媒介**分(文字 / 文档 / 图像 / 影音)— 这是对的,因为它对应:
- GPU / CPU 资源池切分
- 进程级依赖隔离(av_agent 需要 moviepy + GPU)
- 派发队列分流(Redis Streams 4 个 stream)

但用户的开放任务往往跨**能力**:研究 → 评审 → 撰写 → 核查 → 合规。如果只按媒介分,所有这些都落到 `agent_1`(文字 worker),system prompt 是同一个"文字调研专员",行为千篇一律。

2026 年硅谷一线(Anthropic Claude with Skills、Manus、Cognition):
> Worker 是执行单元,不是决策单元。每个 step 应该有自己的角色人格,system prompt + 工具白名单 + 预算单独配置。

我们的现状:Plan schema 已经在 step 上有 `persona` 字段(ADR-019),通过
`parameters._planner.persona` 下传到 worker,**但 worker 端没读**。本 ADR 补这个空缺。

## 决策

### 1. 两层人格,不替换不合并

| 维度 | 谁定义 | 何时加载 | 例子 |
|---|---|---|---|
| Worker Persona(ReactPersona)| 进程级写死,按 agent_id 分 | worker 启动 | "文字与调研专员" / "影音师" |
| Step Persona(StepPersona)| Plan 在 step 上指定 | 每个 task 处理时 | "researcher" / "critic" |

**组合而不是替换**:
```
final_system = ReactPersona.title + frugality_rules
             + StepPersona.addendum (if not default)
             + StepPersona constraint clauses (if any)
```

### 2. 工具白名单是核心约束

Skill YAML 给的 `mcp_tools` 是**必要条件**,Step Persona 给的是**充分条件**:

```
final_tools = (Skill.mcp_tools ∪ ReactPersona.default_mcp_uris)
            ∩ StepPersona.allowed_pattern
            ∖ StepPersona.denied_pattern
```

`critic` persona 的 `denied_pattern=("mcp://*",)` → critic step 看不到任何 MCP 工具,
只能调 `agent_finish` —— 这是**强约束**,LLM 想用工具也用不了。

### 3. 注册表写死 + 可注册扩展

注册表在 `agents/_common/step_persona.py` 里硬编码 8 个核心 persona。新增 persona 三种方式:
- 修改本文件(推荐,代码评审可控)
- 测试时调 `register_persona(StepPersona(...), override=True)`
- S5 的 Skill induction 闭环:Planner 创新出新 persona 名 → 落 `skill_drafts` → 人工审 → 加到注册表

### 4. 软约束 vs 硬约束

| 约束类型 | 表现 | 例子 |
|---|---|---|
| 硬约束 | 工具不暴露给 LLM | critic 没有 MCP 工具 |
| 半硬约束 | 在 prompt 里写"必须" | `require_structured_output=True` → "必须用 structured_payload 返回" |
| 软引导 | 在 addendum 里写身份 + 风格 | "你以**研究员**身份工作,优先 web_search 收集信息" |

S1 阶段不做"agent_finish 参数后置校验"硬约束(LLM 仍可能违规)— 半硬 + 软足够,
留观察一段时间再加 enforcement。

### 5. 8 个核心 Persona

| 名字 | 关键约束 | 典型场景 |
|---|---|---|
| `default` | 无 | 任何未声明 persona 的 step |
| `researcher` | readonly,只允许 search/* + pdf_extract | 信息收集 step |
| `critic` | readonly,**denied=mcp://\***,structured_payload,温度 0.1 | 任何创作后的评审(配合 ADR-020 的 critic_node 不一样:那个是 LangGraph 内嵌的特殊 critic;Step Persona critic 是给"显式 plan 出 critic step"用) |
| `fact_checker` | readonly,只允许 search/*,结构化输出 | 事实核查 step |
| `art_director` | 只允许 image_tools/quality_check + search | 视觉风格指导 step |
| `editor` | 禁所有 MCP,温度 0.3 | 文本润色 step |
| `seo_specialist` | 只允许 search/*,结构化输出 | SEO 优化 step |
| `compliance` | readonly,只允许 search/web_fetch,结构化输出,温度 0.1 | 广告法 / 内容安全审核 step |

## 模块结构

```
agents/agents/_common/
├── react_personas.py          (不动,worker 维度)
├── step_persona.py            ← 新增
│   ├── StepPersona            (frozen dataclass)
│   ├── _REGISTRY              (8 个核心 persona + 可注册扩展)
│   ├── get_step_persona(name)
│   ├── filter_mcp_uris_by_persona(uris, persona) -> (kept, dropped)
│   ├── extract_planner_meta(parameters)
│   ├── resolve_step_persona_for_task(parameters)
│   └── resolve_budget_tokens(parameters, default)
│
└── react_runner.py            ← 微创式 patch
    ├── _merged_mcp_uris(task, persona, step_persona)  ← 加白名单过滤
    ├── _build_tools(task, persona, step_persona)      ← 透传
    ├── _system_instruction(task, persona, step_persona) ← 加 addendum + 约束
    └── run_react_agent_task(task, persona)
        ├── step_persona = resolve_step_persona_for_task(task.parameters)
        ├── persona_temperature = step_persona.temperature ?? 0.35
        └── persona_max_tokens = resolve_budget_tokens(...)
```

## 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `ENABLE_STEP_PERSONA` | `true` | 全局开关(关掉 → 全部 fallback default) |
| `STEP_PERSONA_MAX_BUDGET_TOKENS` | `32000` | budget_tokens 硬上限,防止 plan 写大数搞挂 |

## 与 ADR / 铁律兼容性

| ADR / 铁律 | 兼容 | 说明 |
|---|---|---|
| ADR-001-rev(4 Worker)| ✓ | Worker 进程不变,Step Persona 是逻辑层 |
| ADR-002(Worker 不互调)| ✓ | Step Persona 不引入跨 worker 调用 |
| ADR-009(MCP-first)| 强化 | persona 白名单是 MCP 工具的另一道闸 |
| ADR-017(LangGraph 唯一内核)| ✓ | 不动 LangGraph 拓扑 |
| ADR-019(Planner)| 协同 | Planner 在 Plan.step.persona 上下传,这里读 |
| ADR-020(Critic Loop)| 协同 | LangGraph 节点内嵌的 critic ≠ Step Persona critic;两者并存,前者是引擎自动评审,后者是 plan 显式 critic step |

## 测试

`agents/tests/unit/`:
- `test_step_persona.py` — 注册表 / 白名单过滤 / budget 解析 / 黑白名单优先级
- `test_react_runner_step_persona.py` — `_build_tools` / `_system_instruction` 行为:
  - default → 完全不变
  - critic → MCP 全黑,prompt 含 "[Step Persona: critic]" + "只读" + "structured_payload"
  - researcher → 只剩 search/*,image / video 工具被剥
  - art_director → 只剩 image_tools/quality_check + search
  - unknown 名字 → silent fallback default
  - budget_tokens 透传 + 硬上限裁剪

## 风险

| 风险 | 缓解 |
|---|---|
| Plan 给出 unknown persona 名字 | 自动 fallback default + log warning,不抛 |
| 工具白名单太严导致 step 跑空 | 单元测试覆盖各 persona × MCP 组合;监控 step_dispatch_counts 异常 |
| `forced_artifact_type` LLM 没遵守 | S1 软约束;S2 看数据决定要不要做 agent_finish 参数后置校验 |
| Worker Persona + Step Persona 冲突(罕见)| Step Persona 拥有最终决定权(白名单是交集,prompt addendum 在 worker 之后追加) |

## S3 后续

- 把 ADR-019 的 `Subagent.spawn(persona=...)` 实装为递归子图,子图加载对应 persona 跑独立 ReAct 循环
- Persona × task_type 的成本 / 质量数据滚动统计 → `flywheel/persona_tuner.py` 自动调整白名单
- `agent_finish` 参数后置校验(硬 enforcement)
