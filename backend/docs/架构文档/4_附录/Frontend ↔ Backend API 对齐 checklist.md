# Frontend ↔ Backend API 对齐 checklist

> 用法:frontend 入仓后,逐项核对自己的 `lib/api.ts` / `lib/ws-events.ts` / `stores/*` 是否与本表一致。**不一致时改 frontend**(backend 是 V1 RC1 契约)。
>
> 来源:`haole/backend/app/main.py` route 注册 + `haole/backend/app/api/*.py` 实际声明 + `haole/backend/app/schemas/ws.py`。

---

## REST endpoint(全量,prefix 已展开)

### 鉴权 — `auth.py` `prefix=/api/auth`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/sms/send` | 发送验证码(dev 模式 console 打印) |
| POST | `/api/auth/login` | 验证码登录,返回 JWT |
| POST | `/api/auth/refresh` | 刷新 token |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/me` | 当前用户信息 |

### 会话 — `conversations.py` `prefix=/api/conversations`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/conversations` | 列出我的群聊 |
| POST | `/api/conversations` | 新建群 |
| GET | `/api/conversations/{conv_id}` | 群详情 |
| POST | `/api/conversations/private-chat/{agent_id}` | 与单个 Agent 私聊(HR / 财务) |
| GET | `/api/conversations/{conv_id}/brief` | 获取该群 Brief |
| POST | `/api/conversations/{conv_id}/brief/reset` | 重置 Brief |
| POST | `/api/conversations/{conv_id}/switch-work-mode` | 切换 Plan/Ask/Auto(铁律 #17) |
| GET | `/api/conversations/{conv_id}/members` | 群成员栏(主会话 7 个 / 普通群 5 个) |

### 消息 — `messages.py` `prefix=/api`

| 方法 | 路径 | 说明 |
|------|------|------|
| 详见后端代码 | `/api/...` | 消息发送 / 读取(@router.post 装饰器看具体路径) |

### 任务 + HITL — `tasks.py` + `hitl.py` `prefix=/api/tasks`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tasks/{task_id}` | 任务详情 |
| POST | `/api/tasks/{task_id}/answer-clarification` | 回应澄清(中断 A) |
| POST | `/api/tasks/{task_id}/resolve-conflict` | 解决冲突(中断 B) |
| POST | `/api/tasks/{task_id}/interrupt` | 用户主动中断(暂停/取消) |
| POST | `/api/tasks/{task_id}/rollback` | V2 中断 C(本 V1 不暴露,后端有 stub) |
| GET | `/api/tasks/{task_id}/history` | LangGraph checkpoint 历史(time-travel) |
| GET | `/api/tasks/{task_id}/hitl_gates` | 列出 HITL gates |
| POST | `/api/tasks/{task_id}/hitl_gates/{gate_id}/approve` | HITL: 接受 |
| POST | `/api/tasks/{task_id}/hitl_gates/{gate_id}/modify` | HITL: 微调(中断 B) |
| POST | `/api/tasks/{task_id}/hitl_gates/{gate_id}/cancel` | HITL: 取消(中断 F) |
| POST | `/api/tasks/{task_id}/hitl_gates/{gate_id}/rollback` | V2,前端先 hide |

### 上传 — `upload.py` `prefix=/api/upload`

| 方法 | 路径 | 说明 |
|------|------|------|
| 详见后端代码 | `/api/upload/...` | 头像 / 素材 OSS 直传 + confirm |

### 飞轮 — `flywheel.py` `prefix=/api`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/users/{user_id}/preference_vector` | 偏好画像(V1-P2 前端可视化用) |
| GET | `/api/users/{user_id}/skill_drafts` | Skill 草稿列表 |
| POST | `/api/skill_drafts/{draft_id}/publish` | 发布草稿 |

### 个人 — `support.py` `prefix=/api`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/profile/me` | 个人档案 |
| PATCH | `/api/profile/me` | 更新档案 |
| GET | `/api/profile/me/stats` | 个人统计 |

### 库 — `library.py` `prefix=/api`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/materials` | 素材库 |
| POST | `/api/materials` | 新增素材 |
| DELETE | `/api/materials/{material_id}` | 删除素材 |
| GET | `/api/prompts` | 我的 prompt 库 |
| POST | `/api/prompts` | 新增 prompt |
| DELETE | `/api/prompts/{prompt_id}` | 删除 |
| POST | `/api/prompts/{prompt_id}/use` | 标记使用 +1(用于排序) |
| GET | `/api/artifacts` | 成果库(产物列表) |

### Skills — `skills.py` `prefix=/api`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/skills` | 技能市场列表 |
| GET | `/api/skills/mine` | 我已添加的技能 |

### WebSocket — `ws.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| WS | `/ws?token=<JWT>` | 单一 WS 通道,**所有**实时事件走这里 |

---

## WebSocket 事件类型(`schemas/ws.py::WSEventType`)

frontend `lib/ws-events.ts` 必须与本表对齐(手写,因为 OpenAPI 不覆盖 WS):

| `type` 字符串 | 触发场景 | payload 关键字段 |
|------------|---------|----------------|
| `conversation_created` | 新群被创建 | `conversation_id` |
| `conversation_status_changed` | 群状态变(活跃/归档) | `conversation_id`, `status` |
| `message_added` | 群里新消息(用户 / Agent) | `conversation_id`, `message` |
| `step_started` | LangGraph step 开始执行 | `task_id`, `step_id`, `agent_id` |
| `step_completed` | step 完成 | `task_id`, `step_id`, `artifact{id,type,reference,metadata}` |
| `step_streaming` | LLM 流式 chunk(用于 long_writing 边写边推) | `task_id`, `step_id`, `chunk` |
| `task_completed` | 整个 Task 完成 | `task_id`, `final_artifact_ref` |
| `task_failed` | Task 失败(含死锁兜底 / recursion_exceeded) | `task_id`, `failure_reason` |
| `clarification_required` | 中断 A — 缺字段需要追问 | `task_id`, `field`, `options[]` |
| `mode_choice_required` | Brief 完成度 ≥ 0.8 → 建议切 Auto | `conversation_id`, `suggestion`, `score` |
| `work_mode_changed` | 模式切换(Plan ↔ Ask ↔ Auto)| `conversation_id`, `from`, `to` |
| `brief_updated` | Brief 字段更新(防抖批量) | `conversation_id`, `brief` |
| `hitl_gate_opened` | HITL 审核打开,等用户决议 | `task_id`, `gate_id`, `gate_type`, `payload` |
| `hitl_gate_closed` | HITL 决议完成 | `task_id`, `gate_id`, `decision` |
| `quota_warning` | 配额接近上限(铁律 #20) | `quota_type`, `used`, `limit` |
| `agent_status_changed` | Agent 工作状态变化(working/idle/...) | `agent_id`, `status`, `conversation_id` |
| `pong` | 心跳响应 | — |

---

## 跨语言 Schema 同步(CLAUDE.md §9)

后端是源,前端自动生成:

```
haole/backend/app/schemas/*.py  (Pydantic v2)
        │
        │ FastAPI 自动 /openapi.json
        ▼
haole/scripts/gen-frontend-types.sh
        │
        │ openapi-typescript /openapi.json -o lib/api-types.ts
        ▼
haole/frontend/lib/api-types.ts  (auto-generated)
```

**WS event 不走 OpenAPI**,frontend `lib/ws-events.ts` 手写,与本文档同步维护。修 `schemas/ws.py` 必须同步本文档。

---

## CI 强制规则

PR 修改 `haole/backend/app/schemas/**` 必须:

1. 在 `haole/frontend/` 跑 `pnpm gen:api` 重新生成 `lib/api-types.ts`
2. 把生成产物 commit 入 PR

CI 会 grep `git diff` 检查:如果 `schemas/` 改了但 `lib/api-types.ts` 没改 → fail。

---

## 已知不在前端覆盖的 backend endpoint

(纯后端 / Webhook / 内部用途,前端不要调)

- `/health` `/ready`(K8s liveness/readiness)
- `/api/__internal__/*`(假如未来有)
- `/api/admin/*`(V1 不开放)
