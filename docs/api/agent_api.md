# Agent 模块接口文档

## 元信息

| 项 | 内容 |
|---|---|
| 文档版本 | v1.0（自动生成） |
| 生成时间 | 2026-05-09T10:56:38+08:00 |
| Git Commit | 未检测到 Git 仓库 |
| Git Branch | — |
| 扫描入口 | `backend/app`（FastAPI 路由 + `main.py` 挂载）、WebSocket 推送相关 `app/schemas/ws.py`、`app/ws/`、`agents/agents/orchestrator_agent`（`publish`/`ws_manager.publish` 调用） |
| 维护人 | 赖老师 |

## 扫描摘要

- 扫描文件总数：**21**（`backend/app/api` 下 12 个 router 模块、`main.py`、`app/schemas/ws.py`、`app/ws/manager.py`，以及 `agents/agents/orchestrator_agent` 内 `runner.py` / `interaction.py` / `hitl_gate.py` + `app/services/brief_builder.py` / `app/services/agent_status.py`）
- HTTP 接口数：**56**（✅ **52** / 🔨 **2** / ⏳ **2**）
- WebSocket：**1** 个连接端点；服务端推送事件类型见「WebSocket 模块」（枚举中另有未见推送实现的类型，见附录 C）
- 其他接口数：**0**（`backend/app` 内未发现 `StreamingResponse` / `EventSourceResponse` 业务路由）
- 业务模块数：**11**（按 `main.py` 的 `prefix` + 功能分组）

## 接口总表

按业务模块分组的所有接口一览：

| 编号 | 模块 | 协议 | 接口名 | 路径/事件 | 状态 | 代码位置 |
|---|---|---|---|---|---|---|
| 001 | 基础设施 | HTTP | 存活探测 | GET /health | ✅ | backend/app/main.py:104 |
| 002 | 基础设施 | HTTP | 就绪探测 | GET /ready | ✅ | backend/app/main.py:110 |
| 003 | 基础设施 | HTTP | Prometheus 指标 | GET /metrics | ✅ | backend/app/main.py:159 |
| 004 | 认证 | HTTP | 发送短信验证码 | POST /api/auth/sms/send | ✅ | backend/app/api/auth.py:44 |
| 005 | 认证 | HTTP | 登录 | POST /api/auth/login | ✅ | backend/app/api/auth.py:63 |
| 006 | 认证 | HTTP | 刷新 Token | POST /api/auth/refresh | 🔨 | backend/app/api/auth.py:86 |
| 007 | 认证 | HTTP | 登出 | POST /api/auth/logout | ✅ | backend/app/api/auth.py:93 |
| 008 | 认证 | HTTP | 当前用户 | GET /api/auth/me | 🔨 | backend/app/api/auth.py:98 |
| 009 | 会话 | HTTP | 会话列表 | GET /api/conversations | ✅ | backend/app/api/conversations.py:54 |
| 010 | 会话 | HTTP | 创建会话 | POST /api/conversations | ✅ | backend/app/api/conversations.py:67 |
| 011 | 会话 | HTTP | 会话详情 | GET /api/conversations/{conversation_id} | ✅ | backend/app/api/conversations.py:98 |
| 012 | 会话 | HTTP | 开小窗私聊 | POST /api/conversations/private-chat/{agent_id} | ✅ | backend/app/api/conversations.py:120 |
| 013 | 会话 | HTTP | 获取 Brief | GET /api/conversations/{conversation_id}/brief | ✅ | backend/app/api/conversations.py:157 |
| 014 | 会话 | HTTP | 重置 Brief | POST /api/conversations/{conversation_id}/brief/reset | ✅ | backend/app/api/conversations.py:169 |
| 015 | 会话 | HTTP | 切换工作模式 | POST /api/conversations/{conversation_id}/switch-work-mode | ✅ | backend/app/api/conversations.py:183 |
| 016 | 会话 | HTTP | 群成员与状态 | GET /api/conversations/{conversation_id}/members | ✅ | backend/app/api/conversations.py:250 |
| 017 | 记忆 | HTTP | 记忆 Context Pack | GET /api/conversations/{conversation_id}/memory/context-pack | ✅ | backend/app/api/memory.py:18 |
| 018 | 消息 | HTTP | 发消息 | POST /api/conversations/{conversation_id}/messages | ✅ | backend/app/api/messages.py:350 |
| 019 | 任务 | HTTP | 任务详情 | GET /api/tasks/{task_id} | ✅ | backend/app/api/tasks.py:71 |
| 020 | 任务 | HTTP | 外部步骤回执 | POST /api/tasks/{task_id}/external-step-result | ✅ | backend/app/api/tasks.py:124 |
| 021 | 任务 | HTTP | 澄清作答 | POST /api/tasks/{task_id}/answer-clarification | ✅ | backend/app/api/tasks.py:151 |
| 022 | 任务 | HTTP | 冲突处理 | POST /api/tasks/{task_id}/resolve-conflict | ✅ | backend/app/api/tasks.py:178 |
| 023 | 任务 | HTTP | 中断 | POST /api/tasks/{task_id}/interrupt | ✅ | backend/app/api/tasks.py:203 |
| 024 | 任务 | HTTP | 回滚步骤 | POST /api/tasks/{task_id}/rollback | ✅ | backend/app/api/tasks.py:236 |
| 025 | 任务 | HTTP | Checkpoint 历史 | GET /api/tasks/{task_id}/history | ✅ | backend/app/api/tasks.py:264 |
| 026 | 上传 | HTTP | 预签名 | POST /api/upload/sign | ✅ | backend/app/api/upload.py:45 |
| 027 | 上传 | HTTP | 确认上传 | POST /api/upload/confirm | ✅ | backend/app/api/upload.py:63 |
| 028 | HITL | HTTP | HITL 列表 | GET /api/tasks/{task_id}/hitl_gates | ✅ | backend/app/api/hitl.py:53 |
| 029 | HITL | HTTP | 批准 | POST /api/tasks/{task_id}/hitl_gates/{gate_id}/approve | ✅ | backend/app/api/hitl.py:64 |
| 030 | HITL | HTTP | 微调 | POST /api/tasks/{task_id}/hitl_gates/{gate_id}/modify | ✅ | backend/app/api/hitl.py:80 |
| 031 | HITL | HTTP | 取消 | POST /api/tasks/{task_id}/hitl_gates/{gate_id}/cancel | ✅ | backend/app/api/hitl.py:98 |
| 032 | HITL | HTTP | 网关门回滚 | POST /api/tasks/{task_id}/hitl_gates/{gate_id}/rollback | ⏳ | backend/app/api/hitl.py:114 |
| 033 | 支持/配额 | HTTP | Agent 状态列表 | GET /api/agent-status/me | ✅ | backend/app/api/support.py:51 |
| 034 | 支持/配额 | HTTP | 配额摘要 | GET /api/quota/me | ✅ | backend/app/api/support.py:62 |
| 035 | 支持/配额 | HTTP | 月度账单 | GET /api/quota/me/billing | ✅ | backend/app/api/support.py:76 |
| 036 | 支持/配额 | HTTP | HR 对话 | POST /api/support/hr/respond | ✅ | backend/app/api/support.py:99 |
| 037 | 支持/配额 | HTTP | 财务对话 | POST /api/support/finance/respond | ✅ | backend/app/api/support.py:121 |
| 038 | 素材/知识库 | HTTP | 素材列表 | GET /api/materials | ✅ | backend/app/api/library.py:56 |
| 039 | 素材/知识库 | HTTP | 创建素材 | POST /api/materials | ✅ | backend/app/api/library.py:71 |
| 040 | 素材/知识库 | HTTP | 删除素材 | DELETE /api/materials/{material_id} | ✅ | backend/app/api/library.py:95 |
| 041 | 素材/知识库 | HTTP | Prompt 列表 | GET /api/prompts | ✅ | backend/app/api/library.py:124 |
| 042 | 素材/知识库 | HTTP | 创建 Prompt | POST /api/prompts | ✅ | backend/app/api/library.py:137 |
| 043 | 素材/知识库 | HTTP | 删除 Prompt | DELETE /api/prompts/{prompt_id} | ✅ | backend/app/api/library.py:150 |
| 044 | 素材/知识库 | HTTP | Prompt 使用计数+1 | POST /api/prompts/{prompt_id}/use | ✅ | backend/app/api/library.py:163 |
| 045 | 素材/知识库 | HTTP | 成果列表 | GET /api/artifacts | ✅ | backend/app/api/library.py:207 |
| 046 | 素材/知识库 | HTTP | 个人资料 | GET /api/profile/me | ✅ | backend/app/api/library.py:250 |
| 047 | 素材/知识库 | HTTP | 更新资料 | PATCH /api/profile/me | ✅ | backend/app/api/library.py:264 |
| 048 | 素材/知识库 | HTTP | 个人统计 | GET /api/profile/me/stats | ✅ | backend/app/api/library.py:285 |
| 049 | 技能 | HTTP | 技能市场列表 | GET /api/skills | ✅ | backend/app/api/skills.py:40 |
| 050 | 技能 | HTTP | 我的技能 | GET /api/skills/mine | ✅ | backend/app/api/skills.py:82 |
| 051 | 技能 | HTTP | 技能详情 | GET /api/skills/{skill_id} | ✅ | backend/app/api/skills.py:127 |
| 052 | 技能 | HTTP | 订阅 | POST /api/skills/{skill_id}/subscribe | ✅ | backend/app/api/skills.py:179 |
| 053 | 技能 | HTTP | 取消订阅 | DELETE /api/skills/{skill_id}/subscribe | ✅ | backend/app/api/skills.py:198 |
| 054 | 飞轮 | HTTP | 偏好向量 | GET /api/users/{user_id}/preference_vector | ✅ | backend/app/api/flywheel.py:18 |
| 055 | 飞轮 | HTTP | Skill 草稿列表 | GET /api/users/{user_id}/skill_drafts | ✅ | backend/app/api/flywheel.py:32 |
| 056 | 飞轮 | HTTP | 发布草稿 | POST /api/skill_drafts/{draft_id}/publish | ⏳ | backend/app/api/flywheel.py:44 |
| 057 | WebSocket | WS | 用户事件通道 | GET /ws（WebSocket） | ✅ | backend/app/api/ws.py:17 |

---

## 模块：基础设施（`main.py` 直连）

> 模块说明：健康检查与运维抓取，无 `/api` 前缀。  
> 代码位置：`backend/app/main.py`

### 接口 001 · liveness — 进程是否活着

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 / 事件名 | `/health` |
| 状态 | ✅ 已实现 |
| 认证 | 不需要（无 `Depends`） |
| 代码位置 | `backend/app/main.py:104` |

#### 请求

无 Path/Query/Body。

#### 响应

**成功**（HTTP 状态码：200）：

```json
{
  "status": "ok",
  "env": "development",
  "version": "dev"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| status | string | 固定为上下文中的运行环境标识 |
| env | string | `settings.ENV` |
| version | string | 环境变量 `APP_VERSION`，缺省 `dev` |

---

### 接口 002 · readiness

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 / 事件名 | `/ready` |
| 状态 | ✅ 已实现 |
| 认证 | 不需要 |
| 代码位置 | `backend/app/main.py:110` |

#### 响应

**成功**（整体正常时 HTTP **200**；任一项失败时 HTTP **503** ，仍返回 JSON body）：

```json
{
  "status": "ok",
  "checks": {
    "db": "ok",
    "redis": "ok",
    "litellm": "mock"
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| status | string | `ok` 或 `degraded` |
| checks | object | 键为 `db` / `redis` / `litellm`，值为 `ok`、以 `fail:` 开头的错误摘要或 `mock`（`LITELLM_MOCK` 为真时） |

---

### 接口 003 · Prometheus 指标

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 / 事件名 | `/metrics` |
| 状态 | ✅ 已实现 |
| 认证 | 不需要 |
| 代码位置 | `backend/app/main.py:159` |

#### 响应

**成功**（HTTP 200，`Content-Type: text/plain; version=0.0.4`）：正文为 Prometheus 文本，由 `render_prometheus_metrics()` 生成（结构以运行时输出为准）。

---

## 模块：认证（`prefix=/api/auth`）

> 模块说明：短信验证码与 JWT。  
> 代码位置：`backend/app/api/auth.py`

### 接口 004 · 发送短信验证码

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/auth/sms/send` |
| 状态 | ✅ 已实现 |
| 认证 | 不需要 |
| 代码位置 | `backend/app/api/auth.py:44` |

#### 请求

**Body**：

```json
{
  "phone": "13800000000"
}
```

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|---|---|---:|---|---|---|
| phone | string | 是 | — | `min_length=11`, `max_length=20` | 手机号 |

#### 响应

**成功**：HTTP **204**，无 body。

**失败**：

| HTTP Code | 说明 |
|---|---|
| 502 | 短信发送失败（`SmsError`，非 `SMS_DEV_MODE`） |

---

### 接口 005 · 登录

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/auth/login` |
| 状态 | ✅ 已实现 |
| 认证 | 不需要 |
| 代码位置 | `backend/app/api/auth.py:63` |

#### 请求

```json
{
  "phone": "13800000000",
  "code": "123456"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| phone | string | 是 | 手机号 |
| code | string | 是 | 短信验证码 |

#### 响应

**成功**（200）：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| access_token | string | JWT |
| token_type | string | 默认 `bearer` |
| user_id | string | 用户 UUID 字符串 |

**失败**：

| HTTP Code | 说明 |
|---|---|
| 401 | 验证码错误或已过期 |

---

### 接口 006 · 刷新 Token

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/auth/refresh` |
| 状态 | 🔨 开发中（依赖注入无法得到 `user_id`，见附录 C） |
| 认证 | 设计意图为需已登录用户；代码为 `Depends(lambda: None)`，与 `get_current_user_id` 不一致 |
| 代码位置 | `backend/app/api/auth.py:86` |

#### 请求

无 Body。

#### 响应

**成功**（200）：与登录相同 `TokenResponse`。

**失败**：

| HTTP Code | 说明 |
|---|---|
| 401 | `user_id is None` → `"未授权"` |

---

### 接口 007 · 登出

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/auth/logout` |
| 状态 | ✅ 已实现（函数体为空，无服务端注销状态） |
| 认证 | 不需要 |
| 代码位置 | `backend/app/api/auth.py:93` |

#### 响应

HTTP **204**，无 body。

---

### 接口 008 · 当前用户

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 | `/api/auth/me` |
| 状态 | 🔨 开发中（同接口 006 的 `Depends(lambda: None)` 问题） |
| 认证 | 代码未使用 `get_current_user_id` |
| 代码位置 | `backend/app/api/auth.py:98` |

#### 响应

**成功**（200）：

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "phone": "13800000000",
  "nickname": "用户昵称"
}
```

**失败**：

| HTTP Code | 说明 |
|---|---|
| 401 | 未授权 |
| 404 | 用户不存在 |

---

## 模块：会话（`prefix=/api/conversations`，`conversations.py`）

> 模块说明：会话 CRUD、Brief、工作模式、成员列表（v3.0 ADR-014 等，见文件头注释）。  
> 代码位置：`backend/app/api/conversations.py`

### 接口 009 · 列出会话

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 | `/api/conversations` |
| 状态 | ✅ 已实现 |
| 认证 | 需要，`Depends(get_current_user_id)` |
| 代码位置 | `backend/app/api/conversations.py:54` |

#### 响应

**成功**（200）：`ConversationOut` 数组。

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "新会话",
    "mode": "group",
    "work_mode": "plan",
    "status": "active"
  }
]
```

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string(uuid) | 会话 ID |
| name | string | 名称 |
| mode | string | `main_session` \| `group` \| `private_chat` |
| work_mode | string \| null | `plan` \| `ask` \| `auto` |
| status | string | 会话状态（ORM 字段） |

---

### 接口 010 · 创建会话

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/conversations` |
| 状态 | ✅ 已实现 |
| 认证 | 需要 |
| 代码位置 | `backend/app/api/conversations.py:67` |

#### 请求

```json
{
  "mode": "group",
  "work_mode": "plan",
  "skill_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "项目群"
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| mode | string | 否 | `group` | `main_session` \| `group` \| `private_chat` |
| work_mode | string \| null | 否 | null | `plan` \| `ask` \| `auto` |
| skill_id | string(uuid) \| null | 否 | null | |
| name | string \| null | 否 | null | |

#### 响应

201：**ConversationOut**（同接口 009 单条）。

**失败**：

| HTTP Code | 说明 |
|---|---|
| 401 | 用户不存在（创建前 `get(User)` 失败） |
| 402 | 群创建配额超限，`detail` 为 `{ "code", "detail" }` |

---

### 接口 011 · 获取单个会话

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 | `/api/conversations/{conversation_id}` |
| 状态 | ✅ 已实现 |
| 认证 | **不需要**（代码未校验 `user_id`） |
| 代码位置 | `backend/app/api/conversations.py:98` |

#### 响应

200：`ConversationOut`，404：`会话不存在`。

---

### 接口 012 · 开小窗私聊

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/conversations/private-chat/{agent_id}` |
| 状态 | ✅ 已实现 |
| 认证 | 需要 |
| 代码位置 | `backend/app/api/conversations.py:120` |

#### Path

| 参数 | 类型 | 说明 |
|---|---|---|
| agent_id | string | 允许的 Agent：`ceo_assistant`、`agent_1`～`agent_4`、`hr`、`finance_manager` |

#### 响应

200：**ConversationOut**。

**失败**：400 未知 `agent_id`。

---

### 接口 013 · 获取 Brief

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 | `/api/conversations/{conversation_id}/brief` |
| 状态 | ✅ 已实现 |
| 认证 | 需要，且校验 `conv.user_id == user_id` |
| 代码位置 | `backend/app/api/conversations.py:157` |

#### 响应

200：JSON 对象，默认结构至少包含：

```json
{
  "完成度": 0.0,
  "字段": {},
  "决策日志": []
}
```

（实际为 `conv.brief` 字典。）

---

### 接口 014 · 重置 Brief

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/conversations/{conversation_id}/brief/reset` |
| 状态 | ✅ 已实现 |
| 认证 | 需要 |
| 代码位置 | `backend/app/api/conversations.py:169` |

#### 响应

200：同上默认 Brief 对象。

---

### 接口 015 · 切换工作模式

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/conversations/{conversation_id}/switch-work-mode` |
| 状态 | ✅ 已实现 |
| 认证 | **不需要**（未使用 `get_current_user_id`） |
| 代码位置 | `backend/app/api/conversations.py:183` |

#### 请求

```json
{
  "target": "auto",
  "triggered_by": "user"
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| target | string | 是 | — | `plan` \| `ask` \| `auto` |
| triggered_by | string | 否 | `user` | `user` \| `orchestrator` |

#### 响应

200：

```json
{
  "conversation": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "新会话",
    "mode": "group",
    "work_mode": "auto",
    "status": "active"
  },
  "ws_event": {
    "type": "work_mode_changed",
    "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
    "from": "plan",
    "to": "auto"
  }
}
```

（`type` 取自 `WSEventType.WORK_MODE_CHANGED`。）

---

### 接口 016 · 会话成员

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 | `/api/conversations/{conversation_id}/members` |
| 状态 | ✅ 已实现 |
| 认证 | 需要 |
| 代码位置 | `backend/app/api/conversations.py:250` |

#### 响应

200：`AgentMember` 数组。

```json
[
  {
    "id": "ceo_assistant",
    "status": "idle"
  }
]
```

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 角色 id |
| status | string | `working` / `idle` / `fishing` / `training`（缺数据时为 `idle`） |

**失败**：403 无权；404 会话不存在。

---

## 模块：记忆（`prefix=/api/conversations`，`memory.py`）

> 模块说明：装配会话记忆包（Brief+滚动摘要等）。  
> 代码位置：`backend/app/api/memory.py`

### 接口 017 · Memory Context Pack

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 | `/api/conversations/{conversation_id}/memory/context-pack` |
| 状态 | ✅ 已实现 |
| 认证 | 需要 |
| 代码位置 | `backend/app/api/memory.py:18` |

#### Query

| 参数 | 类型 | 必填 | 默认 | 约束 |
|---|---|---:|---|---|
| recall_query | string \| null | 否 | null | max_length=500 |
| task_limit | integer | 否 | 5 | 1～20 |

#### 响应

200：**MemoryContextPack**

```json
{
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "brief_digest": "摘要文本",
  "rolling_summary": "滚动摘要",
  "preference_digest": "偏好摘要",
  "recent_tasks": [
    {
      "task_id": "550e8400-e29b-41d4-a716-446655440001",
      "status": "completed",
      "one_liner": "一句话",
      "skill_id": "550e8400-e29b-41d4-a716-446655440002",
      "primary_ref": "oss://bucket/key"
    }
  ],
  "recalled_artifacts": [
    {
      "artifact_id": "550e8400-e29b-41d4-a716-446655440003",
      "title": "标题",
      "summary": "概述",
      "type": "image",
      "reference_tail": "path/to/file",
      "score": 0.85
    }
  ],
  "meta": {}
}
```

**失败**：404（`ValueError` 转译）。

---

## 模块：消息（`prefix=/api`，`messages.py`）

> 模块说明：主编排消息入口（文件模块注释）。  
> 代码位置：`backend/app/api/messages.py`

### 接口 018 · 发送消息

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/conversations/{conversation_id}/messages` |
| 状态 | ✅ 已实现 |
| 认证 | **未使用** `get_current_user_id`；仅校验会话存在及 `User` 存在 |
| 代码位置 | `backend/app/api/messages.py:350` |

#### 请求

```json
{
  "content": "用户提交的文本",
  "role": "user",
  "mentions": []
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| content | string | 是 | — | 消息正文 |
| role | string | 否 | `user` | |
| mentions | array[string] | 否 | [] | @ 的 Agent id 列表 |

#### 响应

200：**SendMessageResponse**

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "decision": "task_started",
  "payload": {}
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| message_id | string(uuid) | 写入的用户消息 id |
| decision | string | 代码注释列举：`task_started` / `clarification_required` / `chitchat` / `mode_switched` / `mention_replied` / `plan_discussion` / `task_conflict` / `interrupt_handled` 等（**任意字符串**，以实际返回为准） |
| payload | object | 结构随 `decision` 变化，类型为 **`dict[str, Any]`**（见附录 C） |

**失败**：

| HTTP Code | 说明 |
|---|---|
| 404 | 会话不存在 |
| 401 | 会话归属用户不存在 |
| 402 | Plan 轮次等配额：`detail` 为字符串（本接口路径，`HTTPException(..., e.detail)`） |

---

## 模块：任务（`prefix=/api/tasks`）

> 模块说明：任务查询、外部回执、澄清、冲突、中断、回滚、历史。  
> 代码位置：`backend/app/api/tasks.py`

### 接口 019 · 任务详情

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 | `/api/tasks/{task_id}` |
| 状态 | ✅ 已实现 |
| 认证 | 需要，`get_current_user_id`；非所有者返回 404 |
| 代码位置 | `backend/app/api/tasks.py:71` |

#### 响应 200 · TaskDetailOut

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "skill_id": "550e8400-e29b-41d4-a716-446655440001",
  "progress": {
    "current": 3,
    "total": 5
  },
  "orchestration_run_id": "550e8400-e29b-41d4-a716-446655440002",
  "trace_id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "memory_card": {},
  "failure_digest": null
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| progress | object | JSON，默认含 `current`/`total`（Task 模型） |
| orchestration_run_id | string \| null | 最多 36 字符 |
| trace_id | string \| null | 最多 64 字符 |
| memory_card | object \| null | |
| failure_digest | string \| null | 由 `error_detail` 推导 |

---

### 接口 020 · 外部步骤回执

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/tasks/{task_id}/external-step-result` |
| 状态 | ✅ 已实现 |
| 认证 | 需要 |
| 代码位置 | `backend/app/api/tasks.py:124` |

#### Body · ExternalStepResultBody

`status` 类型为 **`AgentStatus`**：`pending` \| `running` \| `completed` \| `failed` \| `pending_external`。

**ArtifactRef**：

```json
{
  "artifact_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "image",
  "reference": "oss://bucket/path",
  "extra_metadata": {}
}
```

| 字段 | 类型 | 必填 | 默认 |
|---|---|---:|---|
| step_id | string | 是 | — |
| status | string(枚举) | 是 | — |
| output | object \| null | 否 | null |
| extra_artifacts | array | 否 | [] |
| cost_usd | number \| null | 否 | null |
| duration_ms | integer \| null | 否 | null |
| model_used | string \| null | 否 | null |
| error_detail | object \| null | 否 | null |
| external_workflow_id | string \| null | 否 | null |

#### 响应 200

```json
{
  "status": "published"
}
```

---

### 接口 021 · 澄清作答

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/tasks/{task_id}/answer-clarification` |
| 状态 | ✅ 已实现 |
| 认证 | 不需要（代码未使用 `get_current_user_id`） |
| 代码位置 | `backend/app/api/tasks.py:151` |

#### Body

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| clarification_id | string | 是 | |
| field | string | 是 | |
| value | any | 是 | Pydantic 为 `Any` |

#### 响应 200

```json
{
  "status": "accepted"
}
```

---

### 接口 022 · 冲突处理

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/tasks/{task_id}/resolve-conflict` |
| 状态 | ✅ 已实现 |
| 认证 | 不需要 |
| 代码位置 | `backend/app/api/tasks.py:178` |

#### Body

```json
{
  "action": "queue"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| action | string | 是 | `queue` \| `cancel_current` \| `new_group` |

#### 响应 200

- `cancel_current` → `{"status":"cancelled","next":"send_message_again"}`
- `queue` → `{"status":"queued"}`
- `new_group` → `{"status":"client_navigate","next":"create_new_group"}`

**失败**：400 `未知操作:{action}`

---

### 接口 023 · 中断

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/tasks/{task_id}/interrupt` |
| 状态 | ✅ 已实现 |
| 认证 | 不需要 |
| 代码位置 | `backend/app/api/tasks.py:203` |

#### Body

```json
{
  "interrupt_class": "A",
  "payload": {}
}
```

| 字段 | 类型 | 必填 | 默认 |
|---|---|---:|---|
| interrupt_class | string | 是 | — |
| payload | object \| null | 否 | null |

#### 响应 200

```json
{
  "status": "received",
  "interrupt_class": "A",
  "action": "pause_task"
}
```

（`action` 由 `handle_interrupt` 返回，类型为代码中的动态值。）

**失败**：400 V1 不支持的中断类（C/D 等提示信息）。

---

### 接口 024 · 回滚步骤

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/tasks/{task_id}/rollback` |
| 状态 | ✅ 已实现 |
| 认证 | 不需要 |
| 代码位置 | `backend/app/api/tasks.py:236` |

#### Body

| 字段 | 类型 | 必填 |
|---|---|---:|
| target_step_id | string | 是 |
| instruction | string \| null | 否 |

#### 响应 200

```json
{
  "status": "rolled_back",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "target_step_id": "step_1",
  "cleared_steps": ["step_2"],
  "rollback_count": 1
}
```

---

### 接口 025 · Checkpoint 历史

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | GET |
| 路径 | `/api/tasks/{task_id}/history` |
| 状态 | ✅ 已实现 |
| 认证 | 不需要 |
| 代码位置 | `backend/app/api/tasks.py:264` |

#### 响应 200

`list[dict]`，每项含 `checkpoint_id`、`next`、`values_summary`（见 `LangGraphTaskRunner.get_history`）。

---

## 模块：上传（`prefix=/api/upload`）

> 模块说明：OSS 预签名上传。  
> 代码位置：`backend/app/api/upload.py`

### 接口 026 · 预签名

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/upload/sign` |
| 状态 | ✅ 已实现 |
| 认证 | 需要 |
| 代码位置 | `backend/app/api/upload.py:45` |

#### Body · SignRequest

| 字段 | 类型 | 必填 | 默认 | 约束 |
|---|---|---:|---|---|
| file_name | string | 是 | — | |
| content_type | string | 是 | — | |
| purpose | string | 否 | `user_upload` | `user_upload` / `artifact` / `bgm`；头像路径时走校验逻辑 |
| size_bytes | integer \| null | 否 | null | `>0`（若提供） |

#### 响应 200 · SignResponse

```json
{
  "upload_url": "https://oss.example.com/presigned",
  "object_key": "user_upload/foo.bin",
  "expires_in": 3600
}
```

---

### 接口 027 · 确认上传

| 项 | 内容 |
|---|---|
| 协议 | HTTP |
| 方法 | POST |
| 路径 | `/api/upload/confirm` |
| 状态 | ✅ 已实现 |
| 认证 | 需要 |
| 代码位置 | `backend/app/api/upload.py:63` |

#### Body · ConfirmRequest

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| object_key | string | 是 | |
| size_bytes | integer | 是 | `>0` |
| sha256 | string \| null | 否 | |

#### 响应 200

头像路径时额外返回 `avatar_url`；否则 `{"object_key":"...","status":"confirmed"}`。

---

## 模块：HITL（`prefix=/api/tasks`，`hitl.py`）

> 模块说明：HITL gate 批准/微调/取消/回滚（V1 回滚未实现）。  
> 代码位置：`backend/app/api/hitl.py`

### 接口 028 · 列出 HITL

**GET** `/api/tasks/{task_id}/hitl_gates`，需认证且任务属主。响应：`HITLGateOut` 数组（`id`,`task_id`,`step_id`,`gate_type`,`resolution`）。

### 接口 029 · 批准

**POST** `.../approve`，Body：`{"user_choice": {}}`（`user_choice` 可选）。响应：`{"status":"approved","dispatched_next": ...}`（bool 或运行时值）。

### 接口 030 · 微调

**POST** `.../modify`，Body：`target_step`（必填），`parameters`（可选 object）。响应：`{"status":"modified","redispatched": ...}`。

### 接口 031 · 取消

**POST** `.../cancel`，Body：`reason` 可选。响应：`{"status":"cancelled"}`。

### 接口 032 · 网关门回滚

**POST** `.../rollback`。响应 **501**，detail 固定为代码内中文说明（V2 功能）。

---

## 模块：支持 / 配额（`prefix=/api`，`support.py`）

> 代码位置：`backend/app/api/support.py`

### 033 GET `/api/agent-status/me`

需认证。响应：`list[dict[str,str]]`（`list_status` 返回的结构，字段以运行时为准）。

### 034 GET `/api/quota/me`

需认证。响应：**dict**（含 `limits_table`、`warnings`、财务摘要等，无单一 Pydantic 模型）。

### 035 GET `/api/quota/me/billing`

Query：`month` 可选，格式 `YYYY-MM`。响应：

```json
{
  "month": "2026-05",
  "by_quota_type": {
    "auto_tasks_daily": 3
  },
  "total_items": 3
}
```

### 036 POST `/api/support/hr/respond`

Body：`SupportRequest`。响应：**SupportResponse**（`message_id`,`role`,`content`,`quota_warning`）。

### 037 POST `/api/support/finance/respond`

同上，`role` 为 `finance_manager`，`quota_warning` 可能非空。

---

## 模块：素材库 / 个人资料（`prefix=/api`，`library.py`）

> 代码位置：`backend/app/api/library.py`（材料、Prompt、Artifacts、Profile、Stats）。

### 038 GET `/api/materials`

Query：`folder`、`mime_prefix`。响应：**MaterialOut** 列表。

### 039 POST `/api/materials`

Body：**MaterialIn**。响应：201 **MaterialOut**。

### 040 DELETE `/api/materials/{material_id}`

响应：**204**。

### 041～044 Prompt CRUD + use

见 `PromptIn`/`PromptOut`；`POST .../use` 返回 `{"id":"...","used_count": 2}`。

### 045 GET `/api/artifacts`

Query：`artifact_type`、`conversation_id`、`only_final`。响应：**ArtifactRow** 列表。

### 046 GET `/api/profile/me` / 047 PATCH `/api/profile/me`

**ProfileOut** / **ProfilePatch**（PATCH 禁止直接改 `avatar_url`，会 400）。

### 048 GET `/api/profile/me/stats`

响应：`{"artifacts": 12, "skills_used": 3}`。

---

## 模块：技能（`prefix=/api`，`skills.py`）

> 代码位置：`backend/app/api/skills.py`

### 049 GET `/api/skills`

Query：`domain`、`scenario`。需认证。返回 **SkillCard** 列表（控制器自行组装 dict）。

### 050 GET `/api/skills/mine`

需认证。**SkillCard** 列表。

### 051 GET `/api/skills/{skill_id}`

需认证。**SkillDetail**（含 `yaml_definition`、`inputs_schema`、`workflow_summary` 等）。

### 052 POST `/api/skills/{skill_id}/subscribe`

响应：`{"skill_id":"...","status":"subscribed"}`。

### 053 DELETE `/api/skills/{skill_id}/subscribe`

响应：**204**。

---

## 模块：飞轮（`prefix=/api`，`flywheel.py`）

> 代码位置：`backend/app/api/flywheel.py`

### 054 GET `/api/users/{user_id}/preference_vector`

无认证。无 `response_model`。200：含 `preferences`、`preference_vec`。

### 055 GET `/api/users/{user_id}/skill_drafts`

无认证。返回草稿列表（`id`,`name`,`status`,`created_at`）。

### 056 POST `/api/skill_drafts/{draft_id}/publish`

**501**，detail：`Skill 创作市场是 V1.5 范围`。

---

## 模块：WebSocket

> 模块说明：单连接 + 服务端经 Redis 广播推送；客户端发送 `ping` 或超时被动 `pong`。  
> 代码位置：`backend/app/api/ws.py`、`app/ws/manager.py`

### 接口 057 · WebSocket 连接

| 项 | 内容 |
|---|---|
| 协议 | WebSocket |
| 方法 | GET（升级） |
| 路径 | `/ws` |
| 状态 | ✅ 已实现 |
| 认证 | Query `token`：代码中 `settings.is_dev` 时或未传 token 时 `user_id` 为 **`anonymous`**；非 dev 且传 token 时用 JWT 解 `user_id` |
| 代码位置 | `backend/app/api/ws.py:17` |

#### 客户端 → 服务端

| 消息 | 说明 |
|---|---|
| `"ping"` | 文本帧；服务端回复 JSON `{"type":"pong"}` |
| （超时） | 无消息时每 `WS_HEARTBEAT_SECONDS` 秒服务端发 `{"type":"pong"}` |

#### 服务端 → 客户端（连接内）

| type 字段 | 说明 |
|---|---|
| pong | 心跳应答（见上） |

### 服务端推送事件（经 `ws_manager.publish` / `LangGraphTaskRunner.publish`）

以下 **`type` 字符串** 来自实际 `publish` 调用（**含** `WSEventType` 枚举值）；若与 `app/schemas/ws.py` 中 Pydantic 模型字段不一致，以 **推送代码中的 dict** 为准。

| type | 代表性 payload 字段（代码实际） | 代码来源 |
|---|---|---|
| conversation_status_changed | `conversation_id`, `status`, `task_id` | `messages.py` |
| task_failed | `task_id`, `reason` | `messages.py`；亦用于 LangGraph 步骤失败 |
| work_mode_changed | `conversation_id`, `from`, `to` | `messages.py` |
| message_added | `conversation_id`, `message`（嵌套字段因分支不同：`content`+`kind` 或 `text`+`kind`+`from_agent` 等） | `messages.py`、`interaction.py` |
| brief_updated | `conversation_id`, `brief` | `brief_builder.py` |
| mode_choice_required | `conversation_id`, `suggestion`, `reason`, `score` | `brief_builder.py` |
| agent_status_changed | `agent_id`, `status`, `last_active_at`, `conversation_id` | `agent_status.py` |
| step_started | `task_id`, `step_id`（**无** `agent_id` 字段） | `runner.py` |
| step_completed | `task_id`, `step_id`, `artifact`（可为含 `artifact_id`/`type`/`reference`/`metadata` 的对象或 null） | `runner.py` |
| task_completed | `task_id`, `primary_artifact` | `runner.py` |
| hitl_gate_opened | **两种 shape**：(A) `hitl_gate.py`：`task_id`,`gate`,`preview_artifact`；(B) `runner.py` 中断路径：`task_id`,`step_id`,`preview` | `hitl_gate.py` / `runner.py` |

**说明**：`WSEventType` 枚举中还包含 `conversation_created`、`step_streaming`、`clarification_required`、`quota_warning`、`hitl_gate_closed` 等值，在 **本次扫描的 Python `publish` 调用中未见发送**（见附录 C）。

---

## 附录 A：通用响应格式

**无**统一外层包装（如 `code`/`data`/`msg`）。成功时多为 Pydantic `response_model` 模型、或直接 `dict`/`list`/`Response`。异常时由 FastAPI 默认 **`{"detail": ...}`** 呈现（`HTTPException` 的 `detail` 可为 `str` 或 `dict`，依抛出位置而定）。

## 附录 B：错误码总表（归纳自 `backend/app` 中 `HTTPException`）

| 含义（归纳） | HTTP Status | 典型 detail / 条件 | 抛出位置（示例） |
|---|---|---|---|
| 参数/业务错误 | 400 | 未知操作；未知 Agent；仅群支持模式切换；头像 URL 直接修改；文件名不合法 等 | `tasks.py`、`conversations.py`、`library.py`、`avatar.py` |
| 未授权 / 验证码 / Token | 401 | 缺少/无效 Bearer；未授权；验证码错误；会话用户不存在 | `auth.py`、`messages.py` |
| 支付/配额 | 402 | 配额超限（`detail` 为 str 或 `{code,detail}`） | `messages.py`、`conversations.py` |
| 权限 | 403 | 无权操作任务；无权访问会话；头像归属 | `hitl.py`、`conversations.py`、`avatar.py` |
| 不存在 | 404 | 各类资源不存在 | 多处 |
| 短信网关 | 502 | 短信发送失败 | `auth.py` |
| 未实现 | 501 | HITL 门回滚；飞轮发布草稿 | `hitl.py`、`flywheel.py` |
| 就绪降级 | 503 | `/ready` 依赖项失败 | `main.py` |

（另外还有校验层 **422**（请求体验证），由 FastAPI 默认生成。）

## 附录 C：未实现 / 待确认清单

| 位置 | 类型 | 说明 |
|---|---|---|
| `auth.py` `refresh` / `me` | 待赖老师确认 | 使用 `Depends(lambda: None)`，`user_id` 恒为 `None`，与 `get_current_user_id` 不一致，`refresh`/`me` 实际无法通过正常 JWT 注入用户 // 待赖老师确认 |
| `messages.py` `send_message` | 待赖老师确认 | 路由未要求 `Authorization`，仅靠 `conversation_id` 访问 // 待赖老师确认 |
| `conversations.py` `get_conversation` / `switch_work_mode` | 待赖老师确认 | 无用户校验，与 Brief/members 等接口不一致 // 待赖老师确认 |
| `flywheel.py` `GET .../preference_vector` 等 | 待赖老师确认 | 路径含任意 `user_id`，无 `get_current_user_id` // 待赖老师确认 |
| `schemas/ws.py` 枚举 | 待赖老师确认 | `conversation_created`、`step_streaming`、`clarification_required`、`quota_warning`、`hitl_gate_closed` 等未见本次扫描范围内的 `publish` 发送 // 待赖老师确认 |
| `flywheel.py` `publish_skill_draft` | 已实现抛错 | 固定 `501`，docstring 称 V1.5 |
| `hitl.py` `rollback_gate` | 已实现抛错 | 固定 `501` |

## 附录 D：扫描日志

- **跳过**：`backend/.venv`、二进制与 `.git` 不存在导致无法取 commit。
- **异味（统计）**：
  - 若干路由未声明 `response_model`（如多数 `tasks` 子路径、`support` 的 GET、`flywheel` 全部、`auth` 除 login 外、`conversations` 部分路径等）。
  - `SendMessageResponse.payload`、`InterruptRequest.payload` 等 **`dict[str, Any]`** 无固定 JSON Schema。
  - `messages.py` 存在 `except NotImplementedError` 分支（中断处理），非 HTTP 接口层行为。

