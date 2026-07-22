# ADR-022: MD Skills 一等公民 + Episode 召回

**状态**: Accepted (C 阶段已落地)
**日期**: 2026-05-09
**关联**: ADR-011(Qdrant 工作流轨迹)、ADR-017(LangGraph 唯一内核)、ADR-019(Planner Agent)

## 结论

智能体平台同时支持两种 Skill 形态,**正交**:

| 类型 | 文件 | 角色 | 谁执行 |
|---|---|---|---|
| **MD Skill**(知识) | `*.md`(Anthropic / Kimi 兼容 frontmatter) | 给 Agent 看的领域知识 / 风格规范 | Planner 把它注入 step.prompt_template,Worker 内化执行 |
| **YAML Playbook**(产线) | `*.yaml` | 可直接编译成 LangGraph 的工作流 | `compiler.build_state_graph()` |

两者在 `SkillRegistry` 下统一索引,Planner 拿到 snapshot 后**分两块呈现**给认知层模型。

接通 ADR-011 已存的 Qdrant `workflow_traces` collection,做相似历史任务召回 →
Planner prompt 增加"# 历史相似任务"段。**flag 默认关**,启用前需确认 backend 写入对齐。

## 背景

ADR-019 引入了 Planner,但 Planner 只看到平铺的 "skill 列表"(YAML),拿不到:
1. 用户已有的 MD Skill 知识(行业规范 / 写作指南 / 合规清单)
2. 历史相似任务的 plan + outcome(用得越多越聪明的飞轮基础)

2026 年硅谷一线产品(Anthropic Claude with Skills、Kimi K2)的统一形态:
- **SKILL.md** 是知识包,带 frontmatter 进度披露(progressive disclosure)
- 用户 / 第三方能直接写 / 分享 SKILL.md

我们的 `agents/skills/` 目录里**已有**这种格式:`SKILL_xhs-note-creator.md` /
`SKILL_seo_analyser.md` 等。但代码里没人读 — 只有 YAML 在被 compiler 用。

## 决策

### 1. MD Skill = 知识,YAML Playbook = 产线

**MD Skill 不会被引擎直接执行**,它是 Planner 在产 Plan 时的**参考资料**。
Planner 看到匹配场景的 MD Skill 后,把规范精华塞进 `step.prompt_template`。

**YAML Playbook 是可执行工作流**,compiler 直接编译。Planner 看到匹配的
Playbook 时,会在 rationale 里点名("可参考 short_video 的 5 步拆法"),
但 Plan 仍是新拆出来的(未来 S5 的 Skill induction 会让 Planner 凝固高频 plan
为新 Playbook)。

### 2. Anthropic / Kimi 兼容,零迁移成本

```yaml
---
name: xhs-note-creator
description: "小红书笔记的写作风格、合规红线、爆款句式与排版规范。
              当用户要写小红书时使用。"
---

# 小红书笔记规范
## 风格 ...
## 合规 ...
```

frontmatter 必填:`name` + `description`。可选扩展(私有约定,不破坏兼容性):
- `when_to_use`:更结构化的触发条件描述
- `required_tools`:list of MCP URIs,声明本 skill 需要的工具
- `scripts`:list of relative paths,可调脚本(S3 sandbox 时真正可执行)

**用户从 Claude / Kimi 拷 SKILL.md 过来直接可用,这是 ADR 选这个格式的核心理由。**

### 3. 渐进式加载(Progressive Disclosure)

`MDSkill` dataclass:
- `name` + `description` + `when_to_use`:**始终加载**(< 1KB / skill,常驻 Planner 索引)
- `body`:**按需加载**(`load_body()` 第一次调用时读盘)
- `scripts`:列表常驻,**真正调用时才读文件**(S3 sandbox 接通)

理由:仓库可能堆几十上百个 SKILL.md,全读 body 进内存 = 几 MB context 浪费。

### 4. 统一 SkillRegistry

```python
reg = SkillRegistry.from_directory("agents/skills/")
reg.list_md_skills()       # → list[MDSkill]
reg.list_playbooks()       # → list[PlaybookIndex]  
reg.find_md("xhs-note-creator")
reg.find_playbook("short_video")
reg.search_md("小红书")     # 子串打分(S2 升级到向量召回)
reg.summary_for_planner()  # 给 Planner 用的统一 snapshot
```

进程级单例 `get_default_registry()`(扫 `SKILLS_DIR` 或仓库默认目录),
`clear_default_registry()` 让测试 / 热重载强制重扫。

### 5. Planner Prompt 分两块呈现

`render_planner_user_prompt()` 加 `available_md_skills_summary` 字段:

```text
# 可用 MD Skill 知识包(进 step.prompt_template 引用,例如『按 X 规范……』)
- xhs-note-creator (xhs-note-creator) — when: 用户要写小红书
  what: 小红书笔记的写作风格、合规红线...
- seo-analyser ...

# 已有 YAML Playbook(参考拆步思路,不要直接调用 — 你只能用 4 个 worker)
- short_video (短视频制作) [视频,短视频]: 制作通用短视频
- ecommerce_detail_image ...
```

Planner system prompt 已写明"MD Skill 不是要调用,是要在 prompt_template 里引用"。

### 6. Episode 召回(ADR-011 接通)

`episode_retrieval.py` 从 stub 升级为真实 Qdrant 查询:
- `ENABLE_EPISODE_RETRIEVAL=false`(默认)→ 返回空,不调 Qdrant
- 启用时:
  1. `qdrant_client.embed_text(user_request)` 走 LiteLLM `/embeddings` 端点(`bge-m3` 默认)
  2. `qdrant_client.search_episodes(filter={"user_id": user, "outcome": "success"}, top_k=3)`
  3. 反序列化为 `EpisodePayload` → 转 `Episode` → `format_episodes_for_prompt`
  4. 拼到 Planner prompt 的"# 历史相似任务"段

**graceful 三级**:
- 嵌入失败 → embed_text 返回 None → search 短路返回 [] → Planner 看不到 episode 段
- Qdrant 不可达 / 404 / 解析失败 → search 捕获返回 []
- 任何空 → episode_retrieval.format_episodes_for_prompt 返回空字符串 → Planner prompt 里写"# 历史相似任务(无)"

### 7. 不引入 qdrant-client SDK

只用 httpx 直连 Qdrant REST(`POST /collections/{name}/points/search`)。理由:
- 我们只用一个端点,SDK 全套 overkill
- 减少依赖面,后续升级 Qdrant 服务端不被 SDK 版本绑死
- httpx 已经在 pyproject 里

### 8. Schema 与 backend 对齐(写约定,本仓库只读)

backend 写入 `workflow_traces` collection 的 payload 形如:
```json
{
  "task_id": "...",
  "user_id": "...",
  "user_request": "...",
  "plan_summary": "...",
  "outcome": "success|failed|partial",
  "user_rating": 0.92,
  "duration_s": 320,
  "cost_usd": 0.045,
  "skill_id": "short_video"
}
```

字段在 `qdrant_client.EpisodePayload.from_qdrant_hit` 里反序列化,**容错读取**
(.get + 默认值)— 即使 backend 字段名调整,只需改这一个方法,其余逻辑零改动。

## 模块结构

```
agents/agents/_common/
├── skill_loader.py            ← 新增
│   ├── MDSkill(dataclass)
│   ├── parse_md_skill(path)
│   ├── parse_md_skill_from_text(text, source_path)
│   └── SkillLoadError
│
├── skill_registry.py          ← 新增
│   ├── PlaybookIndex(dataclass)
│   ├── SkillRegistry
│   ├── get_default_registry()
│   └── clear_default_registry()
│
└── qdrant_client.py           ← 新增(只依赖 httpx)
    ├── EpisodePayload(dataclass)
    ├── embed_text(text)        (走 LiteLLM /embeddings)
    ├── search_episodes(...)    (graceful)
    └── healthcheck()

agents/agents/orchestrator_agent/planner/
├── episode_retrieval.py       ← stub → 实装
└── planner_agent.py           ← 加 skill_registry 参数 + MD/YAML 分两块格式化
└── prompts.py                 ← render_planner_user_prompt 加 md_skills 字段
└── entry.py                   ← plan_and_compile 透传 skill_registry
```

## 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `SKILLS_DIR` | `agents/skills/` | 注册表扫描目录 |
| `SKILL_MD_MAX_BYTES` | `262144` (256KB) | MD body 截断上限 |
| `ENABLE_EPISODE_RETRIEVAL` | `false` | episode 召回开关 |
| `EPISODE_RETRIEVAL_TOP_K` | `3` | 召回数 |
| `EPISODE_RETRIEVAL_ONLY_SUCCESS` | `true` | 只取成功案例 |
| `QDRANT_URL` | `http://qdrant:6333` | |
| `QDRANT_API_KEY` | `""` | 没有就不加 header |
| `QDRANT_WORKFLOW_TRACES_COLLECTION` | `workflow_traces` | |
| `QDRANT_TIMEOUT_S` | `5` | |
| `EMBEDDING_MODEL` | `bge-m3` | LiteLLM 端别名 |
| `EMBEDDING_DIM` | `1024` | bge-m3 default |

## 与 ADR / 铁律兼容性

| ADR / 铁律 | 兼容 | 说明 |
|---|---|---|
| ADR-009(MCP-first)| ✓ | MD Skill `required_tools` 字段引用 MCP URI |
| ADR-011(Qdrant 轨迹)| 强化 | 从只写转为读写闭环(本 ADR 加读端) |
| ADR-017(LangGraph 唯一内核)| ✓ | 不影响 graph 拓扑 |
| ADR-019(Planner)| 协同 | Planner 看到分块的 MD + Playbook + Episode 三种上下文 |
| 铁律 4(产物用引用)| ✓ | MD body 渐进加载,大文件不进 LangGraph state |
| 铁律 7(LiteLLM)| ✓ | embed_text 走同一 proxy |

## 测试

`agents/tests/unit/`:
- `test_skill_loader.py` — frontmatter 解析 / 扩展字段 / 错误路径 / load_body 缓存 / 真仓库 SKILL*.md 全部能解析
- `test_skill_registry.py` — 扫目录 / 缺失目录 / 坏文件跳过 / collision / search 打分 / 真仓库 short_video + xhs-note-creator 命中
- `test_qdrant_episode_retrieval.py` — 嵌入失败短路 / Qdrant 不可达 / 404 / 真实响应反序列化 / flag off / flag on
- `test_planner_with_registry.py` — 摘要格式化 / prompt 含 MD 块 / make_plan 自动用注册表

## 风险

| 风险 | 缓解 |
|---|---|
| 用户拷来的 SKILL.md 含恶意脚本路径(scripts) | S1 不执行 scripts;S3 sandbox 接通时强制路径校验 + 沙箱执行 |
| Qdrant 写入字段不对齐 → search 返回空或解析失败 | EpisodePayload 容错 + graceful;flag 默认关,启用前必须验证 |
| 注册表扫到几百个 SKILL → Planner prompt 爆炸 | summary_for_planner 默认 max_md=30 / max_playbooks=30 |
| MD body 巨大(几 MB)→ 内存爆炸 | SKILL_MD_MAX_BYTES 硬截断 + lazy load |
| 用户 SKILL.md 名字与 Playbook ID 重名 | SkillRegistry 分两个字典索引,不冲突 |

## S2 后续

- `flywheel/promoter.py` 写入端 — 任务完成时把 plan + outcome 写 Qdrant `workflow_traces`
- `SkillRegistry.search_md` 升级为向量召回(走 BGE-M3)
- Skill induction(S5 hero):高频 dynamic plan 自动凝固为 YAML Playbook 草稿,落 `skill_drafts`,人工审核后入注册表
