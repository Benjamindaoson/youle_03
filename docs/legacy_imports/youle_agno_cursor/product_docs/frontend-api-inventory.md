# 「有了」前端接口手册

修订日期：2026-05-15
**纯前端视角**：列出**所有**给前端用的接口，每个按统一格式给出：

- **请求路径** · **请求方式** · **请求参数** · **返回参数** · **接口用途**

代码基线：`F:\youle\youle_mas_agno\qianduan\lib\api.ts`（2253 行）
基础前缀：所有路径都在 `https://<host>` 之下，默认带 `Authorization: Bearer <access_token>` header（除 auth 的 `config`/`otp` 系列）。
状态标记：✅ 已实现 · ⚠️ 部分 · ❌ 未实现 · 🔒 内部不给前端用

---

## 目录

1. [鉴权 / 登录](#1-鉴权--登录)
2. [会话（群聊列表 + 管理）](#2-会话群聊列表--管理)
3. [消息（对话气泡 + 实时流）](#3-消息对话气泡--实时流)
4. [任务（Run + 进度 + 控制）](#4-任务run--进度--控制)
5. [HITL（人工审核卡片）](#5-hitl人工审核卡片)
6. [Skills（技能商店）](#6-skills技能商店)
7. [素材库 / Prompts / 产物](#7-素材库--prompts--产物)
8. [个人 / 设置 / 配额](#8-个人--设置--配额)
9. [上传（OSS 直传）](#9-上传oss-直传)
10. [SSE 实时事件](#10-sse-实时事件)

---

# 1. 鉴权 / 登录

## 1.1 获取认证配置 ✅

| | |
|---|---|
| **请求路径** | `/api/auth/config` |
| **请求方式** | `GET` |
| **请求参数** | 无 |
| **返回参数** | `enabled_channels`: string[] — 当前启用的验证码通道，如 `["email", "sms"]`<br>`default_channel`: string — 默认通道<br>`registration_enabled`: bool — 是否开放注册<br>`invite_required`: bool — 注册是否要邀请码<br>`invite_validate_enabled`: bool — 是否支持邀请码预校验<br>`otp_code_length`: int — 验证码位数（如 6）<br>`otp_expires_in`: int — 验证码有效期（秒）<br>`otp_resend_after`: int — 建议重发等待时间（秒） |
| **接口用途** | **登录/注册页**首次加载，前端据此决定显示邮箱还是手机号、是否要求邀请码 |

## 1.2 发送验证码 ✅

| | |
|---|---|
| **请求路径** | `/api/auth/otp/send` |
| **请求方式** | `POST` |
| **请求参数** | `channel`: string — `"email"` 或 `"sms"`<br>`identifier`: string — 邮箱或手机号<br>`invite_code`?: string — 新用户必填（若 `invite_required=true`） |
| **返回参数** | `challenge_id`: string — verify 时必须原样传回<br>`channel`: string<br>`identifier_masked`: string — 脱敏后的身份（如 `us***@example.com`）<br>`mode`: `"login"` \| `"register"`<br>`expires_in`: int — 有效期（秒）<br>`resend_after`: int — 重发等待 |
| **接口用途** | **登录/注册页**点"获取验证码"按钮调用，前端用 `mode` 区分新老用户文案 |

## 1.3 验证验证码并登录 ✅

| | |
|---|---|
| **请求路径** | `/api/auth/otp/verify` |
| **请求方式** | `POST` |
| **请求参数** | `challenge_id`: string — 来自 1.2 的返回<br>`channel`: string<br>`identifier`: string<br>`code`: string — 用户输入的验证码<br>`invite_code`?: string |
| **返回参数** | `access_token`: string — JWT，后续放 `Authorization: Bearer`<br>`token_type`: `"bearer"`<br>`user_id`: string<br>`expires_in`: int — 秒<br>`is_new_user`?: bool<br>`profile`?: { `id`, `email`, `phone`, `nickname`, `avatar_url`, `plan` } |
| **接口用途** | **登录/注册页**用户输完验证码后调用，成功后存 token 到 LocalStorage |

## 1.4 邀请码预校验 ✅

| | |
|---|---|
| **请求路径** | `/api/auth/invites/validate` |
| **请求方式** | `POST` |
| **请求参数** | `invite_code`: string<br>`channel`: string<br>`identifier`: string |
| **返回参数** | `valid`: bool<br>`invite_id`?: string<br>`remaining_uses`?: int<br>`expires_at`?: string ISO<br>`allowed_identity_type`?: string<br>`code`?: string — 业务错误码（invalid 时）<br>`message`?: string — 中文提示 |
| **接口用途** | **注册页**用户输入邀请码后实时校验，失败时立即提示 |

## 1.5 SMS 发送（兼容预留）⚠️

| | |
|---|---|
| **请求路径** | `/api/auth/sms/send` |
| **请求方式** | `POST` |
| **请求参数** | `phone`: string（11 位手机号） |
| **返回参数** | 同 1.2 OTP 系列 |
| **接口用途** | 老短信通道兼容；**第一期前端默认走邮箱**，这个接口预留 |

## 1.6 SMS 登录（兼容预留）⚠️

| | |
|---|---|
| **请求路径** | `/api/auth/login` |
| **请求方式** | `POST` |
| **请求参数** | `phone`: string<br>`code`: string — 6 位验证码 |
| **返回参数** | 同 1.3 的 TokenResponse |
| **接口用途** | 老短信登录兼容；第一期前端不调 |

## 1.7 刷新 token ✅

| | |
|---|---|
| **请求路径** | `/api/auth/refresh` |
| **请求方式** | `POST` |
| **请求参数** | 无（用旧 token 鉴权） |
| **返回参数** | 同 1.3 的 TokenResponse，但 `is_new_user=null` |
| **接口用途** | token 临期时主动调用拿新 token；前端可在 401 时自动重试 |

## 1.8 退出登录 ✅

| | |
|---|---|
| **请求路径** | `/api/auth/logout` |
| **请求方式** | `POST` |
| **请求参数** | 无 |
| **返回参数** | 204 No Content |
| **接口用途** | 退出按钮调用；前端清 LocalStorage |

## 1.9 当前用户信息 ✅

| | |
|---|---|
| **请求路径** | `/api/auth/me` |
| **请求方式** | `GET` |
| **请求参数** | 无 |
| **返回参数** | `id`: string<br>`phone`?: string<br>`email`?: string<br>`nickname`?: string<br>`avatar_url`?: string<br>`plan`: `"free"` \| `"personal"` \| `"team"`<br>`status`?: string<br>`created_at`?: ISO |
| **接口用途** | 应用启动时拿当前用户信息，渲染顶部头像 / 昵称 |

---

# 2. 会话（群聊列表 + 管理）

## 2.1 会话列表 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations` |
| **请求方式** | `GET` |
| **请求参数（Query）** | `status`?: string[] — 如 `["active","paused"]`，默认排除 `deleted`<br>`mode`?: string[] — 如 `["group","private_chat"]`<br>`q`?: string — 模糊搜索群名<br>`limit`?: int — 默认 50，上限 200 |
| **返回参数** | `ConversationSummary[]` 数组，每个含：<br>• `id`: string<br>• `name`: string \| null<br>• `kind`: `"main_session"` \| `"group"` \| `"private_chat"`<br>• `work_mode`: `"plan"` \| `"ask"` \| `"auto"` \| null<br>• `preview`: string? — 最后一条消息预览<br>• `preview_time`: string? — `"14:23"`/`"昨天"`/`"5/12"`<br>• `unread`: int<br>• `pinned` / `muted`: bool<br>• `serious_mode`: bool — 金融/医疗等严肃场景<br>• `agents`?: string \| null<br>• `avatar_colors` / `avatar_image` / `avatar_bg` / `avatar_text`: 头像渲染 |
| **接口用途** | **左栏渲染**所有群聊列表，按 mode 分区 |

## 2.2 新建会话 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations` |
| **请求方式** | `POST` |
| **请求参数** | `mode`?: `"group"` \| `"private_chat"` — 默认 `group`<br>`work_mode`?: `"plan"` \| `"ask"` \| `"auto"`<br>`skill_id`?: string — `group` 可指定关联 skill<br>`name`?: string — 不传时自动生成 |
| **返回参数** | 单个 `ConversationSummary`（同 2.1 每行） |
| **接口用途** | **左栏 "+ 新建群" 按钮**；开私聊请用 2.6 |

## 2.3 会话详情 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}` |
| **请求方式** | `GET` |
| **请求参数** | 路径：`conversation_id` |
| **返回参数** | 单个 `ConversationSummary` |
| **接口用途** | 进入群页面时拿群基础信息 |

## 2.4 用户偏好（置顶/静音）✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}/preferences` |
| **请求方式** | `PATCH` |
| **请求参数** | `pinned`?: bool — 置顶<br>`muted`?: bool — 静音 |
| **返回参数** | 更新后的 `ConversationSummary` |
| **接口用途** | **群条目右键菜单/详情页**：置顶 / 静音 |

## 2.5 软删会话 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}` |
| **请求方式** | `DELETE` |
| **请求参数** | 路径：`conversation_id` |
| **返回参数** | `ok`: bool |
| **接口用途** | **"删除会话"按钮**；二次确认 + 产物保留至成果库；主会话不可删 |

## 2.6 开私聊 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/private-chat/{agent_id}` |
| **请求方式** | `POST` |
| **请求参数** | 路径：`agent_id` — `ceo_assistant`/`agent_1..4`/`hr`/`finance_manager` |
| **返回参数** | `ConversationSummary` |
| **接口用途** | **成员栏点 Agent 头像 → 开私聊**；幂等：已有 active 私聊则返回现有 |

## 2.7 会话简报（Brief）✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}/brief` |
| **请求方式** | `GET` |
| **请求参数** | 路径 |
| **返回参数** | JSON 对象：`{ 完成度, 字段, 决策日志, ... }`（结构灵活，由后端决定） |
| **接口用途** | **群顶部任务卡**：显示当前 task 的字段收集进度 / 决策记录 |

## 2.8 重置简报 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}/brief/reset` |
| **请求方式** | `POST` |
| **请求参数** | 路径 |
| **返回参数** | 重置后的 brief 对象（空状态） |
| **接口用途** | "重置任务"按钮，清空收集字段 |

## 2.9 切换工作模式 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}/switch-work-mode` |
| **请求方式** | `POST` |
| **请求参数** | `target`: `"plan"` \| `"ask"` \| `"auto"`<br>`triggered_by`: string — `"user"` |
| **返回参数** | `conversation`: ConversationSummary<br>`ui_event`?: object — 可选的 UI 事件 |
| **接口用途** | **群顶部模式切换器**：plan（规划）/ ask（澄清）/ auto（自动执行） |

## 2.10 群成员栏 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}/members` |
| **请求方式** | `GET` |
| **请求参数** | 路径 |
| **返回参数** | `AgentMember[]`，每个含：<br>• `role`: string — Agent 角色标识（如 `agent_1`、`hr`）<br>• `name`: string — 显示名（如"总助理"/"研究员"）<br>• `title`?: string<br>• `status`: `"idle"` \| `"working"` \| `"offline"`<br>• `avatar_text`?: string<br>• `avatar_bg`?: string<br>• `avatar_url`?: string |
| **接口用途** | **右侧/底部成员栏**：渲染该群可见的 Agent + 实时状态 |

## 2.11 群内任务列表 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}/tasks` |
| **请求方式** | `GET` |
| **请求参数（Query）** | `status`?: string[] — `["pending","running","completed","failed","cancelled"]`<br>`limit`?: int — 默认 50 |
| **返回参数** | `TaskSummary[]`，每个含：<br>• `id`: string<br>• `skill_id`?: string<br>• `status`: string<br>• `title`?: string<br>• `progress`?: { `current`, `total` }<br>• `created_at` / `completed_at`?: ISO<br>• `cost_usd`?: float<br>• `primary_artifact`?: ArtifactRef — 完成时的主产物 |
| **接口用途** | **群顶部 dashboard**：看这个群历史 / 进行中的 task 列表 |

## 2.12 群上下文记忆 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}/memory/context-pack` |
| **请求方式** | `GET` |
| **请求参数** | 路径 |
| **返回参数** | JSON 对象，包含本群滚动摘要、用户偏好向量摘要等 |
| **接口用途** | **群侧栏"上下文"面板**：让用户看 AI 现在记着哪些内容 |

---

# 3. 消息（对话气泡 + 实时流）

## 3.1 历史消息列表 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}/messages` |
| **请求方式** | `GET` |
| **请求参数（Query）** | `before`?: string — 拿这条之前的（向前翻页）<br>`after`?: string — 拿这条之后的（增量更新）<br>`task_id`?: string — 过滤特定 task 的消息<br>`limit`?: int — 默认 50，上限 200 |
| **返回参数** | `Message[]`，每个含：<br>• `id`: string<br>• `conversation_id`: string<br>• `kind`: `"user_text"`/`"agent_text"`/`"system"`/`"interaction"`/`"agent_card"`/`"hitl_script"`/`"hitl_image"`/`"hitl_video"`<br>• `role`: `"user"`/`"ceo_assistant"`/`"agent_1..4"`/`"hr"`/`"finance_manager"`<br>• `text`?: string<br>• `attachments`?: Attachment[]<br>• `images`?: { id, url }[] — hitl_image<br>• `video_url`?: string — hitl_video<br>• `versions`?: { label, content }[] — hitl_script<br>• `task_id`?: string<br>• `gate_id`?: string — HITL 消息必带<br>• `created_at`?: ISO |
| **接口用途** | **进入群时拉历史消息**；翻页用 `before`，SSE 之外的增量补拉用 `after` |

## 3.2 发消息 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}/messages` |
| **请求方式** | `POST` |
| **请求参数** | `content`: string — 用户输入文本<br>`client_message_id`?: string — 前端本地 ID，乐观回显 / 幂等键<br>`quoted_message_id`?: string — 引用消息<br>`attachments`?: Attachment[] — `{ name, mime?, size?, object_key?, url? }`<br>`mentions`?: string[] — `@agent_3` 等定向 mention |
| **返回参数** | `message`: Message — 已落库的用户消息<br>`task_id`?: string — `auto` 模式触发 Run 时返回<br>`stream_url`?: string — SSE 地址<br>`quota_warning`: unknown[] |
| **接口用途** | **消息输入框 Send 按钮**——**核心接口**；发完立即打开 `stream_url` 监听 SSE |

## 3.3 SSE 实时流 ✅

| | |
|---|---|
| **请求路径** | 由 3.2 返回的 `stream_url` 决定（动态路径） |
| **请求方式** | `GET`（返回 `text/event-stream`） |
| **请求参数（Header + Query）** | **Header**：`Authorization: Bearer <token>`<br>**Header**：`Last-Event-ID: <id>` — 断线重连游标（自动）<br>**Query**：`client_message_id`? — 关联本地回显<br>**Query**：`task_id`? — 只订阅这个 task<br>**Query**：`source_message_id`? — 源消息 ID |
| **返回参数** | SSE 帧流，每帧形如：<br>`id: <event_id>`<br>`event: <name>`<br>`data: <json>`<br><br>事件类型见 §10。心跳每 15s |
| **接口用途** | **发完消息立即监听**，接收 Agent 回复 token 流 / 任务进度 / HITL 卡 / 状态更新 |

## 3.4 收藏消息 ✅

| | |
|---|---|
| **请求路径** | `/api/messages/{message_id}/star` |
| **请求方式** | `POST` |
| **请求参数** | 路径：`message_id` |
| **返回参数** | `message_id`: string<br>`starred`: bool — 操作后状态（总为 true） |
| **接口用途** | **气泡右上角 ⭐ 按钮**；幂等（已收藏不重复写） |

## 3.5 取消收藏 ✅

| | |
|---|---|
| **请求路径** | `/api/messages/{message_id}/star` |
| **请求方式** | `DELETE` |
| **请求参数** | 路径 |
| **返回参数** | `message_id`: string<br>`starred`: bool — 总为 false |
| **接口用途** | 取消收藏；幂等 |

## 3.6 撤回消息 ✅

| | |
|---|---|
| **请求路径** | `/api/conversations/{conversation_id}/messages/{message_id}` |
| **请求方式** | `DELETE` |
| **请求参数** | 路径：`conversation_id` + `message_id` |
| **返回参数** | `ok`: bool<br>`message_id`: string<br>`status`: `"withdrawn"` |
| **接口用途** | **气泡"撤回"按钮**；约束：**仅自己发的 role=user 文本消息**；Agent 消息 / HITL 卡 不可撤回（400） |

---

# 4. 任务（Run + 进度 + 控制）

## 4.1 任务详情 ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}` |
| **请求方式** | `GET` |
| **请求参数** | 路径 |
| **返回参数** | `id`: string<br>`status`: `"pending"`/`"running"`/`"completed"`/`"failed"`/`"cancelled"`<br>`skill_id`?: string<br>`title`?: string<br>`progress`?: { `current`: int, `total`: int }<br>`created_at`?: ISO<br>`completed_at`?: ISO<br>`cost_usd`?: float<br>`orchestration_run_id`?: string<br>`trace_id`?: string<br>`memory_card`?: object — 履历卡<br>`failure_digest`?: string — 失败摘要 |
| **接口用途** | **任务详情面板**：进度条 + 状态 + trace 链接 |

## 4.2 任务 state 快照 ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/state` |
| **请求方式** | `GET` |
| **请求参数** | 路径 |
| **返回参数** | 完整 state 快照（JSON 结构与 skill YAML 相关） |
| **接口用途** | **调试面板**：看任务当前节点输入 / 输出 |

## 4.3 任务历史 ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/history` |
| **请求方式** | `GET` |
| **请求参数** | 路径 |
| **返回参数** | 历史状态变更数组 |
| **接口用途** | 调试面板时间轴 |

## 4.4 中断任务 ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/interrupt` |
| **请求方式** | `POST` |
| **请求参数** | `interrupt_class`: enum — `A`/`B`/`E`/`F`/`G`/`H`/`I`（对应 8 类中断）<br>`payload`?: object |
| **返回参数** | `ok`: bool |
| **接口用途** | **"中断"按钮**：用户主动停止正在跑的任务（中断分类对应不同处理路径） |

## 4.5 回滚任务 ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/rollback` |
| **请求方式** | `POST` |
| **请求参数** | `target_step_id`?: string — 回滚到哪个 step；空则上一节点 |
| **返回参数** | `ok`: bool |
| **接口用途** | **"回滚"按钮**：用户对结果不满意时回退到上一个 step 重做 |

## 4.6 任务评分 ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/rate` |
| **请求方式** | `POST` |
| **请求参数** | `rating`: int — 1~5<br>`feedback`?: string |
| **返回参数** | `ok`: bool |
| **接口用途** | **任务完成后的"👍/👎"评分卡** |

## 4.7 回答澄清问题 ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/answer-clarification` |
| **请求方式** | `POST` |
| **请求参数** | `clarification_id`: string<br>`field`: string — 字段名<br>`value`: any — 用户的回答 |
| **返回参数** | `ok`: bool |
| **接口用途** | **澄清卡片**用户填字段后提交（SSE 收到 `clarification_required` custom 事件时弹卡） |

## 4.8 解决冲突 ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/resolve-conflict` |
| **请求方式** | `POST` |
| **请求参数** | 冲突相关 payload |
| **返回参数** | `ok`: bool |
| **接口用途** | 多 Agent 输出冲突时用户裁决 |

## 4.9 清 checkpoint ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/checkpoints` |
| **请求方式** | `DELETE` |
| **请求参数** | 路径 |
| **返回参数** | `ok`: bool |
| **接口用途** | 调试用，清掉编排器的 checkpoint 让任务重跑 |

---

# 5. HITL（人工审核卡片）

## 5.1 待审 gate 列表 ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/hitl_gates` |
| **请求方式** | `GET` |
| **请求参数** | 路径 |
| **返回参数** | `HitlGate[]`，每个含：<br>• `id`: string<br>• `task_id`: string<br>• `step_id`: string<br>• `gate_type`: string — `version_select`/`script_review`/`script_approval`/`final_approval`/`video_review`/`video_final_review`/`image_review`<br>• `extra_metadata`: object — `{ versions?, images?, preview_artifact?, video_url?, ... }`<br>• `opened_at`: ISO<br>• `closed_at`?: ISO |
| **接口用途** | **HITL 列表 / 同步多设备**（SSE 也会推 `hitl_gate_opened` 触发卡片） |

## 5.2 通过 gate ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/hitl_gates/{gate_id}/approve` |
| **请求方式** | `POST` |
| **请求参数** | `comment`?: string<br>`selection`?: any — 多版本时选哪个 |
| **返回参数** | `ok`: bool |
| **接口用途** | **HITL 卡片"通过"按钮**（脚本审核 / 配图审核 / 视频终审） |

## 5.3 修改 gate ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/hitl_gates/{gate_id}/modify` |
| **请求方式** | `POST` |
| **请求参数** | `modifications`: object — 用户改动（如 `user_choice`、`parameters`） |
| **返回参数** | `ok`: bool |
| **接口用途** | **HITL 卡片"修改"按钮**：用户编辑脚本/图片描述等再提交 |

## 5.4 取消 gate ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/hitl_gates/{gate_id}/cancel` |
| **请求方式** | `POST` |
| **请求参数** | `reason`?: string |
| **返回参数** | `ok`: bool |
| **接口用途** | **HITL 卡片"取消"按钮**：放弃这次 HITL，任务回退 |

## 5.5 回滚 gate ✅

| | |
|---|---|
| **请求路径** | `/api/tasks/{task_id}/hitl_gates/{gate_id}/rollback` |
| **请求方式** | `POST` |
| **请求参数** | `target_step_id`?: string |
| **返回参数** | `ok`: bool |
| **接口用途** | HITL 回滚到上一节点 |

---

# 6. Skills（技能商店）

## 6.1 商店全量 ✅

| | |
|---|---|
| **请求路径** | `/api/skills` |
| **请求方式** | `GET` |
| **请求参数** | 无 |
| **返回参数** | `SkillCard[]`，每个含：<br>• `id`: string<br>• `skill_id`: string — 业务 id，如 `xhs_cover_image`<br>• `name`: string<br>• `description`?: string<br>• `domain`?: string — 如 "电商"<br>• `version`: string<br>• `creator_type`: string<br>• `keywords`: string[]<br>• `subscribed`: bool — 我是否已订阅 |
| **接口用途** | **Skills 商店首页 / 技能学院** |

## 6.2 我订阅的 Skills ✅

| | |
|---|---|
| **请求路径** | `/api/skills/mine` |
| **请求方式** | `GET` |
| **请求参数** | 无 |
| **返回参数** | `SkillCard[]`（同上，但全部 `subscribed=true`） |
| **接口用途** | **"我的技能"页 / 新建群时的 skill picker** |

## 6.3 Skill 详情 ✅

| | |
|---|---|
| **请求路径** | `/api/skills/{skill_id}` |
| **请求方式** | `GET` |
| **请求参数** | 路径 |
| **返回参数** | `SkillCard` 全字段 + 详情：<br>• `yaml_definition`?: object<br>• `inputs_schema`: object[]<br>• `workflow_summary`: [{ `step_id`, `agent`, `task_type` }]<br>• `delivery`?: object — 交付物描述<br>• `anti_signals`: string[] — 不适用场景 |
| **接口用途** | 进入 Skill 详情页查看完整定义 |

## 6.4 订阅 Skill ✅

| | |
|---|---|
| **请求路径** | `/api/skills/{skill_id}/subscribe` |
| **请求方式** | `POST` |
| **请求参数** | 路径 |
| **返回参数** | `skill_id`: string<br>`status`: `"subscribed"` |
| **接口用途** | **"订阅"按钮** |

## 6.5 取消订阅 ✅

| | |
|---|---|
| **请求路径** | `/api/skills/{skill_id}/subscribe` |
| **请求方式** | `DELETE` |
| **请求参数** | 路径 |
| **返回参数** | `ok`: bool |
| **接口用途** | **"取消订阅"按钮** |

---

# 7. 素材库 / Prompts / 产物

## 7.1 素材列表 ✅

| | |
|---|---|
| **请求路径** | `/api/materials` |
| **请求方式** | `GET` |
| **请求参数（Query）** | `q`?: string — 搜索关键词<br>`category`?: string — `favorite`/`file`/`link`<br>`view_filter`?: string — `all`/`image_video`/`non_image_video`<br>`folder`?: string<br>`mime_prefix`?: string<br>`limit`?: int<br>`offset`?: int |
| **返回参数** | `MaterialItem[]`，每个含：<br>• `id`: string<br>• `name`: string<br>• `mime`?: string<br>• `folder`?: string<br>• `url`?: string — OSS 签名 URL<br>• `size`?: int<br>• `oss_key`?: string<br>• `source`: string — `"upload"`/`"url"`/`"task_output"`<br>• `created_at`: ISO |
| **接口用途** | **素材库页面 / 知识库** |

## 7.2 上传素材入库 ✅

| | |
|---|---|
| **请求路径** | `/api/materials` |
| **请求方式** | `POST` |
| **请求参数** | `name`: string<br>`object_key`?: string — 走完 9.1/9.2 拿到的 OSS key<br>`oss_key`?: string — 同 object_key（兼容字段）<br>`mime`?: string<br>`size`?: int<br>`size_bytes`?: int<br>`folder`?: string<br>`url`?: string<br>`source`?: string |
| **返回参数** | 新建的 MaterialItem |
| **接口用途** | OSS 直传成功后调用入库 |

## 7.3 删素材 ✅

| | |
|---|---|
| **请求路径** | `/api/materials/{material_id}` |
| **请求方式** | `DELETE` |
| **请求参数** | 路径 |
| **返回参数** | `ok`: bool |
| **接口用途** | 素材列表删除按钮 |

## 7.4 Prompt 列表 ✅

| | |
|---|---|
| **请求路径** | `/api/prompts` |
| **请求方式** | `GET` |
| **请求参数** | 无 |
| **返回参数** | `PromptItem[]`，每个含：<br>• `id`: string<br>• `name`: string<br>• `content`: string<br>• `used_count`: int<br>• `created_at`: ISO |
| **接口用途** | **Prompt 库面板** |

## 7.5 新建 Prompt ✅

| | |
|---|---|
| **请求路径** | `/api/prompts` |
| **请求方式** | `POST` |
| **请求参数** | `name`: string<br>`content`: string |
| **返回参数** | 新建的 PromptItem |
| **接口用途** | "新建 Prompt"按钮 |

## 7.6 删 Prompt ✅

| | |
|---|---|
| **请求路径** | `/api/prompts/{prompt_id}` |
| **请求方式** | `DELETE` |
| **请求参数** | 路径 |
| **返回参数** | `ok`: bool |
| **接口用途** | 删除按钮 |

## 7.7 标记 Prompt 使用 ✅

| | |
|---|---|
| **请求路径** | `/api/prompts/{prompt_id}/use` |
| **请求方式** | `POST` |
| **请求参数** | 路径 |
| **返回参数** | `used_count`: int — 更新后的累计次数 |
| **接口用途** | 用户从 Prompt 库选了一条放进输入框时调，统计使用 |

## 7.8 产物列表 ✅

| | |
|---|---|
| **请求路径** | `/api/artifacts` |
| **请求方式** | `GET` |
| **请求参数（Query）** | `q`?: string — 搜索关键词<br>`artifact_type`?: string — `favorite`/`file`/`link`<br>`view_filter`?: string<br>`type`?: string — `video`/`image`/`document`<br>`task_id`?: string<br>`conversation_id`?: string<br>`limit`?: int<br>`offset`?: int<br>`only_final`?: bool — 仅最终版 |
| **返回参数** | `ArtifactRow[]`，每个含：<br>• `id`: string<br>• `type`: string<br>• `is_final`: bool<br>• `reference`: string — OSS URI<br>• `url`?: string — 签名 URL<br>• `mime`?: string<br>• `size`?: int<br>• `title`?: string<br>• `summary`?: string<br>• `created_at`: ISO |
| **接口用途** | **"我的产物"页面 / 全局成果库**：查看历史生成的图片/视频/文档 |

---

# 8. 个人 / 设置 / 配额

## 8.1 个人资料 ✅

| | |
|---|---|
| **请求路径** | `/api/profile/me` |
| **请求方式** | `GET` |
| **请求参数** | 无 |
| **返回参数** | `id`: string<br>`phone`?: string<br>`email`?: string<br>`nickname`?: string<br>`avatar_oss_key`?: string<br>`avatar_url`?: string<br>`avatar_style`?: string<br>`plan`: string<br>`status`?: string<br>`created_at`?: ISO |
| **接口用途** | **个人主页** |

## 8.2 改资料 ✅

| | |
|---|---|
| **请求路径** | `/api/profile/me` |
| **请求方式** | `PATCH` |
| **请求参数** | `nickname`?: string<br>`avatar_style`?: string<br>`avatar_file`?: File — FormData 上传时使用 |
| **返回参数** | 更新后的 ProfileSummary |
| **接口用途** | 个人主页编辑昵称 / 头像（支持 JSON 或 FormData） |

## 8.3 统计 ✅

| | |
|---|---|
| **请求路径** | `/api/profile/me/stats` |
| **请求方式** | `GET` |
| **请求参数** | 无 |
| **返回参数** | `artifacts`: int — 产出成果数量<br>`skills_used`: int — 使用过的技能种类 |
| **接口用途** | 个人主页右侧统计卡 |

## 8.4 申请删除账户数据 ✅

| | |
|---|---|
| **请求路径** | `/api/profile/me/erase` |
| **请求方式** | `POST` |
| **请求参数** | `confirm`: bool — 必须 true<br>`reason`?: string |
| **返回参数** | `status`: `"scheduled"`<br>`request_id`: string<br>`scheduled_delete_at`: ISO |
| **接口用途** | **"删除我的所有数据"按钮**（GDPR/隐私合规，72h 内处理，不可恢复） |

## 8.5 头像签名 URL ✅

| | |
|---|---|
| **请求路径** | `/api/profile/me/avatar-url` |
| **请求方式** | `GET` |
| **请求参数（Query）** | `object_key`: string |
| **返回参数** | `url`: string — 临时访问 URL |
| **接口用途** | 根据 OSS key 拿头像的可访问 URL（私有 bucket 时需要） |

## 8.6 用户设置 ✅

| | |
|---|---|
| **请求路径** | `/api/settings/me` |
| **请求方式** | `GET` |
| **请求参数** | 无 |
| **返回参数** | `notifications_enabled`: bool<br>`data_share_enabled`: bool<br>`theme`: `"light"` \| `"dark"` \| `"system"`<br>`language`: `"zh"` \| `"en"` |
| **接口用途** | **设置页** |

## 8.7 改设置 ✅

| | |
|---|---|
| **请求路径** | `/api/settings/me` |
| **请求方式** | `PATCH` |
| **请求参数** | 上面 4 字段任意子集 |
| **返回参数** | 完整 UserSettings |
| **接口用途** | 设置页保存 |

## 8.8 配额 ✅

| | |
|---|---|
| **请求路径** | `/api/quota/me` |
| **请求方式** | `GET` |
| **请求参数** | 无 |
| **返回参数** | `plan`: string<br>`auto_tasks_daily`: { `used`, `total`, `remaining`, `percent` }<br>`video_tasks_daily`: { ... 同上 }<br>`groups_monthly`: { ... 同上 }<br>`warnings`?: string[] |
| **接口用途** | **顶部 / 个人页配额条**；前端每 60 秒自动轮询 |

## 8.9 月度账单 ✅

| | |
|---|---|
| **请求路径** | `/api/quota/me/billing` |
| **请求方式** | `GET` |
| **请求参数（Query）** | `month`?: string — 如 `2026-05` |
| **返回参数** | `month`: string<br>`by_quota_type`: Record<string, int><br>`total_items`: int |
| **接口用途** | 个人页"账单"标签 |

## 8.10 我视角的 Agent 状态 ✅

| | |
|---|---|
| **请求路径** | `/api/agent-status/me` |
| **请求方式** | `GET` |
| **请求参数** | 无 |
| **返回参数** | `[{ agent_id, status, conversation_id?, last_active_at }]`，7 个 agent 的当前状态<br>• `agent_id`: `ceo_assistant`/`agent_1..4`/`hr`/`finance_manager`<br>• `status`: `"idle"`/`"working"`/`"offline"` |
| **接口用途** | 应用启动时拿一次全局 agent 状态，后续 SSE `agent_status_changed` 增量更新 |

## 8.11 HR / 财务支持 ✅

| | |
|---|---|
| **请求路径** | `/api/support/{role}/respond` |
| **请求方式** | `POST` |
| **请求参数** | 路径：`role` — `"hr"` \| `"finance"`<br>`conversation_id`: string<br>`content`: string |
| **返回参数** | `message_id`: string<br>`role`: string<br>`content`: string<br>`quota_warning`: unknown[] |
| **接口用途** | **HR / 财务私聊**特殊响应入口（团队介绍 / 配额账单等） |

---

# 9. 上传（OSS 直传）

## 9.1 拿 OSS 签名 ✅

| | |
|---|---|
| **请求路径** | `/api/upload/sign` |
| **请求方式** | `POST` |
| **请求参数** | `file_name`: string<br>`content_type`: string — MIME<br>`purpose`?: string — `"material"`/`"artifact"`/`"bgm"`/`"user_upload"`，默认 `user_upload`<br>`size_bytes`?: int |
| **返回参数** | `upload_url`: string — 前端直接 PUT 到这<br>`object_key`: string — 留存以便确认<br>`expires_in`: int — 签名有效期（秒）<br>`headers`?: Record<string,string> — PUT 时需带的额外请求头 |
| **接口用途** | **上传步骤 1**：拿 OSS 临时签名 URL |

## 9.2 上传确认 ✅

| | |
|---|---|
| **请求路径** | `/api/upload/confirm` |
| **请求方式** | `POST` |
| **请求参数** | `object_key`: string<br>`size_bytes`: int<br>`sha256`?: string |
| **返回参数** | `object_key`: string<br>`status`?: `"confirmed"`<br>`material_id`?: string — 入库后的 id<br>`url`?: string — 直接可访问 URL<br>`content_type`?: string<br>`size_bytes`?: int |
| **接口用途** | **上传步骤 3**：PUT 到 OSS 成功后调用，后端入库 |

> **完整流程**：
> 1. `POST /api/upload/sign` → 拿 `upload_url` + `object_key`
> 2. `PUT {upload_url}` → 前端直传文件到 OSS（非后端接口）
> 3. `POST /api/upload/confirm` → 把 `object_key` 入库
> 4. （可选）`POST /api/materials` → 创建素材记录，关联到知识库

---

# 10. SSE 实时事件

## 10.1 端点说明

SSE 流的 URL 由 [3.2 发消息](#32-发消息-) 返回的 `stream_url` 字段决定，不是固定路径。

```
POST /api/conversations/{id}/messages   →  返回 { stream_url, task_id, ... }
GET  {stream_url}                        →  连接 SSE 接收事件
```

## 10.2 18 类事件总览

| event | 触发场景 | data 关键字段 | 前端动作建议 |
|---|---|---|---|
| `conversation_created` | 新会话创建 | `conversation` 对象 | 刷左栏列表 |
| `conversation_status_changed` | 归档 / 删除 / 恢复 | `conversation_id`, `status` | 刷左栏分区 |
| `work_mode_changed` | 模式切换 | `conversation_id`, `from`, `to` | 顶部模式器 UI 更新 |
| `message_added` | 新消息（用户/Agent/系统） | `message` 对象 | 追加气泡 |
| `message_withdrawn` | 消息撤回 | `message_id` | 渲染"[消息已撤回]" |
| `agent_message_started` | Agent 开始回复 | `message_id`, `role` | 占位气泡 |
| `agent_message_delta` | Agent 流式文本增量 | `message_id`, `delta`（文本块） | 追加 token |
| `agent_message_completed` | Agent 回复完成 | `message` 对象 | 替换占位为完整消息 |
| `task_started` | 任务启动 | `task_id` | 打开右侧执行流面板 |
| `task_step_started` | 任务步骤开始 | `step_id`, `agent_id` | 节点高亮 |
| `task_step_streaming` | 步骤流式文本块 | `step_id`, `chunk`, `stream_done` | 节点内文本追加 |
| `task_step_completed` | 步骤完成 | `step_id`, `artifact` | 节点变绿 |
| `hitl_gate_opened` | HITL 暂停等用户决定 | `gate`（含 id/type/versions/images/video_url 等） | 弹审核卡 |
| `hitl_gate_closed` | 用户决定后（可能来自其他设备） | `gate_id`, `resolution` | 关闭审核卡 |
| `task_completed` | 任务完成 | `task_id` | 弹评分卡 |
| `task_failed` | 任务失败 | `task_id`, `failure_digest` | 错误提示 |
| `done` | 流正常结束 | — | 关闭 EventSource |
| `error` | 流错误结束 | `code`, `message` | 重连或提示 |

## 10.3 断线重连机制

- 使用 `sessionStorage` 存储 `Last-Event-ID` 游标
- 网络断开/服务端超时切断后自动重连
- 指数退避：`1s → 2s → 4s → 8s → 15s`（上限）
- 连续失败 **5 次**放弃
- 收到过任何事件则重置失败计数

## 10.4 注意事项

- ❌ 不存在 `GET /api/ui-events` 轮询端点 — 一切走 SSE
- ❌ 不要把 `access_token` 放 URL — 走 `Authorization` header
- ❌ token 流（`agent_message_delta`）**不持久化**；断线丢中间 token 可接受，完整 message 可拉 [3.1 历史消息列表](#31-历史消息列表-) 补
- ✅ 心跳每 15s 一次，前端可忽略
- ✅ WebSocket 代码（`lib/ws.ts`）保留但禁用（`ENABLE_WS=false`），SSE 为正式方案

---

# 附录：接口总数

| 章节 | 接口数 | 实现状态 |
|---|---|---|
| 1 鉴权 | 9 | 全部 ✅ |
| 2 会话 | 12 | 全部 ✅ |
| 3 消息 | 6 | 全部 ✅ |
| 4 任务 | 9 | 全部 ✅ |
| 5 HITL | 5 | 全部 ✅ |
| 6 Skills | 5 | 全部 ✅ |
| 7 素材/Prompts/产物 | 8 | 全部 ✅ |
| 8 个人/设置/配额 | 11 | 全部 ✅ |
| 9 上传 | 2 | 全部 ✅ |
| **总计** | **67** | **全部 ✅** |

> SSE 实时通道（第 10 节）= 1 个动态端点（由 `stream_url` 返回），含 18 类事件。

---

# 附录：关键类型定义

## ConversationSummary

```typescript
{
  id: string;
  name: string | null;
  kind: 'main_session' | 'group' | 'private_chat';
  work_mode: 'plan' | 'ask' | 'auto' | null;
  preview: string | null;
  preview_time: string | null;
  unread: number;
  pinned: boolean;
  muted: boolean;
  serious_mode: boolean;
  agents: string | null;
  avatar_colors: string[] | null;
  avatar_image: string | null;
  avatar_bg: string | null;
  avatar_text: string | null;
}
```

## Message

```typescript
{
  id: string;
  conversation_id: string;
  kind: 'user_text' | 'agent_text' | 'system' | 'interaction'
      | 'agent_card' | 'hitl_script' | 'hitl_image' | 'hitl_video';
  role: RoleKey;
  text: string | null;
  attachments?: MessageAttachment[];
  images?: { id: string; url: string }[];
  video_url?: string;
  versions?: { label: string; content: string }[];
  task_id?: string;
  gate_id?: string;
  created_at: string | null;
}
```

## RoleKey

```typescript
type RoleKey =
  | 'user'
  | 'ceo_assistant'
  | 'agent_1' | 'agent_2' | 'agent_3' | 'agent_4'
  | 'hr'
  | 'finance_manager';
```

## WorkMode

```typescript
type WorkMode = 'plan' | 'ask' | 'auto';
```

---

*来源：`qianduan/lib/api.ts` (2253 行) 逐行提取 · 2026-05-15*
*维护：前端团队 · 评审周期：每周一同步 · 变更需走 PR*
