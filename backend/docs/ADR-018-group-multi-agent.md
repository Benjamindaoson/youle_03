# ADR-018:群内多智能体 — 成员路由 + @ Mention 短路径

**状态**:Accepted(2026-05-06)
**关联铁律**:1(单一调度者)/ 18(HR/财务仅主会话)/ 19(拟人化 4 状态)
**关联 ADR**:ADR-001-rev、ADR-013(支持 Agent 仅主会话)、ADR-015(拟人化)

## 背景

CLAUDE.md §1 和 §11 第 9 问明确:**主会话 7 角色,普通群 5 角色**。
但 V1 实现里:

1. ❌ 后端无 `GET /api/conversations/{id}/members` — 前端 `useMembers` 调它,落空回 `MOCK_MEMBERS`
2. ❌ 后端无 `@` mention 解析 — 前端 Composer 让用户在 popover 选 Agent,
   但 `messages.py` 收到时不区分,所有消息走完整意图理解 → Skill 匹配
3. ❌ Skill 市场无详情页端点 — 用户点市场 Skill 卡片想看 workflow 步骤,
   只能从 `/skills` 列表里取一坨,不友好

这 3 项让"群内多智能体"概念在 V1 只是 UI 表象,后端没真打通。

## 决定

### A. 群成员显式 API

```
GET /api/conversations/{id}/members
→ list[AgentMember{id, status}]
```

成员集合按 `Conversation.mode` 派生(V1 硬编码,V1.5 引入 `conversation_members` 表):

| mode | members |
|---|---|
| `main_session` | ceo_assistant, agent_1..4, hr, finance_manager(7 个)|
| `group` | ceo_assistant, agent_1..4(5 个,**无 HR/财务** — 铁律 18) |
| `private_chat` | 仅 `private_chat_agent_id` 1 个 |

`status` 取自 `agent_status` 表(铁律 19 的 4 状态:working / idle / fishing / training)。

### B. `@` Mention 短路径(messages.py)

**铁律 1** 明确:Agent 之间不互相 @。**用户 → Agent 是允许的**(第 3 方),
所以群内用户 @ 单个 Agent 让其单独响应是合法的。

请求体加可选 `mentions: list[str]` 字段(前端 Composer 的 popover 选定后回填):

```json
POST /api/conversations/{id}/messages
{ "content": "@设计师 来一张", "mentions": ["agent_3"] }
```

`messages.py` 解析逻辑(`_parse_mentions`):
1. 优先信任前端 `hint`(过滤合法 id 集合,防注入)
2. 没 hint 时从文本扫 `@设计师 / @研究员` 等显示名(中文 fallback)
3. 仅 1 个 mention 且**非 ceo_assistant**(总裁助理本就是调度者,走原路径) →
   跳过 Skill 匹配,直接 `private_chat_respond` 让该 Agent 单独回
4. mention 命中**该群允许的角色集合**才生效:
   - 主会话:5 个分任务 Agent + HR + 财务经理
   - 普通群:仅 5 个分任务 Agent(**HR / 财务被过滤** — 铁律 18 一致)

返回 `decision="mention_replied"`,前端把回复按"群内私聊气泡"渲染。

### C. Skill 市场详情页

```
GET /api/skills/{id}
→ SkillDetail{
    ...SkillCard 全字段...,
    yaml_definition,
    inputs_schema,
    workflow_summary: [{step_id, agent, task_type, depends_on, phase}],
    delivery, anti_signals,
}
```

给前端 `/market/[skill_id]` 详情页用。**workflow 只暴露 summary**(不返完整 prompt template
等内部细节,**避免泄露 Skill IP**;创作者计划 V2 时再决定可见性)。

## 边界(V1.5+ 才做)

- ❌ 群成员**动态加减**(创建群时拉部分 Agent):V1 是按 mode 硬编码,
  V1.5 引入 `conversation_members(conv_id, agent_id)` 表
- ❌ 群内 Agent **互相 @**:永久不做(铁律 1 + ADR-002)
- ❌ Skill 评分 / 评论 / 案例库:V1.5
- ❌ 创作者上传 / 审核 / 分润:V2

## 测试覆盖(+12 新单测,全套 109 过)

`tests/unit/test_conversation_members.py`(5):
- 主会话恰好 7 角色含 HR + 财务
- 普通群 5 角色,无 HR / 财务(铁律 18 守住)
- 私聊 1 角色,默认 ceo_assistant
- `_MAIN_SESSION_ROLES` 顺序稳定(对齐 ADR-001-rev)

`tests/unit/test_mention_routing.py`(7):
- hint 优先且过滤非法 id(防注入)
- 中文显示名 fallback(@设计师 → agent_3)
- 多 mention 去重保序
- 无 mention 返回空
- HR / 财务经理 fallback 也能解析

## 铁律自检

- ✅ 铁律 1:Agent 间不互相 @(代码里 `@` 路径只接受 user→Agent,Agent 间永远走 Redis Streams)
- ✅ 铁律 18:普通群 mention HR / 财务时,被 `_MENTION_TARGETS_GROUP` 过滤掉
- ✅ 铁律 19:members 端点返回的 status 取自 `agent_status` 表(4 状态)

## 端点摘要(本 PR 新增)

| 端点 | 用途 |
|---|---|
| `GET /api/conversations/{id}/members` | 群成员 + 状态(前端右栏成员栏) |
| `GET /api/skills/{skill_id}` | Skill 市场详情页 |
| `POST /api/conversations/{id}/messages` 改 | 接受可选 `mentions: []` 字段;短路径 `decision=mention_replied` |
