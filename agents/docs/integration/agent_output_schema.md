# 智能体输出 Schema 文档(前端对接)

## 元信息

| 项 | 内容 |
|---|---|
| 文档版本 | v2.0 |
| 生成时间 | 2026-05-09 |
| 维护人 | Benjamin |
| 数据通路 | 前端 ←(WebSocket)— 后端 ←(Redis Streams)— 智能体 |

## 总览

| 类别 | 数量 |
|---|---|
| WebSocket 事件 | 8 种 |
| 流式数据通道 | 1 种(LLM 打字机)|
| 嵌套数据结构 | 5 个 |
| 任务级状态 | 1 个(主动拉取)|
| 枚举类型 | 7 个 |

## 数据流

```
智能体 worker
    │ XADD agent_results:*
    ▼
后端 result_waiter
    │ ws_manager.publish(user_id, payload)
    ▼
WebSocket /ws?token=...
    │
    ▼
前端 store(Zustand) — 按 type 分发
```

---

## Part 1: WebSocket 事件

> 所有事件统一带 `type` 字段做 discriminator;前端按 `type` switch 分发到对应 store。

### 1.1 公共结构

```typescript
interface WSEventBase {
  type: WSEventType;        // 见 §6.1
}

type WSEvent =
  | StepStarted
  | StepCompleted
  | TaskCompleted
  | TaskFailed
  | HITLGateOpened
  | HITLGateClosed
  | MessageAdded
  | TaskRolledBack;
```

### 1.2 `step_started`

```typescript
interface StepStarted {
  type: "step_started";
  task_id: string;          // UUID
  step_id: string;
  agent_id?: AgentId;       // 见 §6.3
}
```

```json
{
  "type": "step_started",
  "task_id": "550e8400-e29b-41d4-a716-446655440001",
  "step_id": "research",
  "agent_id": "agent_1"
}
```

### 1.3 `step_completed`

```typescript
interface StepCompleted {
  type: "step_completed";
  task_id: string;
  step_id: string;
  artifact: {
    artifact_id: string | null;
    type: string | null;      // "text" | "structured" | "image" | "video" | "audio" | "generic"
    reference: string | null; // "oss://bucket/path"
    metadata: Record<string, any>;
  } | null;
}
```

```json
{
  "type": "step_completed",
  "task_id": "550e8400-...",
  "step_id": "research",
  "artifact": {
    "artifact_id": "8b2f1c4e-5d6a-4f23-9e7c-3a8b9d2f1c4e",
    "type": "structured",
    "reference": "oss://youle-prod/artifacts/550e8400/research.json",
    "metadata": {"row_count": 10, "source_profile": "short_video"}
  }
}
```

### 1.4 `task_completed`

```typescript
interface TaskCompleted {
  type: "task_completed";
  task_id: string;
  primary_artifact: {
    reference: string;
  } | null;
}
```

```json
{
  "type": "task_completed",
  "task_id": "550e8400-...",
  "primary_artifact": {
    "reference": "oss://youle-prod/artifacts/550e8400/video_compose.mp4"
  }
}
```

### 1.5 `task_failed`

```typescript
interface TaskFailed {
  type: "task_failed";
  task_id: string;
  step_id?: string;                    // step 级失败时存在
  artifact?: object | null;            // step 级失败时是该 step 的 artifact
  primary_artifact?: object | null;    // 任务级失败时存在(通常 null)
}
```

**示例 — step 级失败**:

```json
{
  "type": "task_failed",
  "task_id": "550e8400-...",
  "step_id": "video_compose",
  "artifact": null
}
```

**示例 — 任务级失败**:

```json
{
  "type": "task_failed",
  "task_id": "550e8400-...",
  "primary_artifact": null
}
```

> 错误详情不在 WS 事件 payload 里;需要时通过任务详情 API 拉 `step_results[].error_detail`(见 §4)。

### 1.6 `hitl_gate_opened`

```typescript
interface HITLGateOpened {
  type: "hitl_gate_opened";
  task_id: string;
  gate: {
    id: string;
    step_id: string;
    gate_type: HITLGateType;        // 见 §6.4
    timeout_seconds: number;        // 默认 600(10 分钟)
  };
  preview_artifact: {
    artifact_id: string | null;
    type: string | null;            // "text" / "structured" / "image" / ...
    reference: string | null;       // "oss://..."
    metadata: Record<string, any>;
  };
}
```

```json
{
  "type": "hitl_gate_opened",
  "task_id": "550e8400-...",
  "gate": {
    "id": "a1b2c3d4-e5f6-4a7b-9c8d-0e1f2a3b4c5d",
    "step_id": "script",
    "gate_type": "version_select",
    "timeout_seconds": 600
  },
  "preview_artifact": {
    "artifact_id": null,
    "type": "text",
    "reference": "oss://youle-prod/artifacts/550e8400/script.txt",
    "metadata": {"version_count": 3}
  }
}
```

### 1.7 `hitl_gate_closed`

```typescript
interface HITLGateClosed {
  type: "hitl_gate_closed";
  task_id: string;
  gate_id: string;
  resolution: HITLResolution;       // 见 §6.5
}
```

```json
{
  "type": "hitl_gate_closed",
  "task_id": "550e8400-...",
  "gate_id": "a1b2c3d4-...",
  "resolution": "approved"
}
```

### 1.8 `message_added`(Agent 间互动)

```typescript
interface MessageAdded {
  type: "message_added";
  conversation_id: string;
  message: {
    id: string;
    conversation_id: string;
    role: AgentId;
    kind: "interaction";
    text: string;
    from_agent: AgentId;
    to_agent: AgentId;
  };
}
```

```json
{
  "type": "message_added",
  "conversation_id": "f1e2d3c4-...",
  "message": {
    "id": "9a8b7c6d-...",
    "conversation_id": "f1e2d3c4-...",
    "role": "agent_1",
    "kind": "interaction",
    "text": "研究员:案例已经整理好了,@文案师 你来写脚本吧",
    "from_agent": "agent_1",
    "to_agent": "agent_1"
  }
}
```

> 用户消息、澄清提问、文件卡片、Brief 更新等其他消息类型由后端独立产生,不在本节范围。

### 1.9 `task_rolled_back`

```typescript
interface TaskRolledBack {
  type: "task_rolled_back";
  task_id: string;
  target_step_id: string;
  cleared_steps: string[];
  rollback_count: number | null;
}
```

```json
{
  "type": "task_rolled_back",
  "task_id": "550e8400-...",
  "target_step_id": "script",
  "cleared_steps": ["bgm", "image_process", "video_compose"],
  "rollback_count": 2
}
```

---

## Part 2: 流式数据(LLM 打字机)

### 2.1 `step_streaming`(后端从 Redis 转 WS)

> 长文本生成期间,智能体每收到一个 LLM chunk 就推一条;后端把 Redis Stream 中的字段封装为 WS event 转发到前端。

```typescript
interface StepStreaming {
  type: "step_streaming";
  task_id: string;
  step_id: string;
  chunk: string;          // LLM 增量文本(可能空字符串 — done 哨兵)
  done?: "0" | "1";       // 后端转发时建议带上;"1" = 流结束
  seq?: number;           // 单调递增的序号(后端可选转发)
}
```

```json
{
  "type": "step_streaming",
  "task_id": "550e8400-...",
  "step_id": "script",
  "chunk": "大家好,今天讲一个真实案例。",
  "done": "0",
  "seq": 12
}
```

**前端处理**:

- 按 `step_id` 累积 chunk → 实时显示打字机文本
- 收到 `done="1"` 后,以 `step_completed` 事件中的 artifact reference 拉 OSS 取最终态做校准(防止流途中早期 chunk 因 `MAXLEN=500` 被截掉)

---

## Part 3: 嵌套 Schema

### 3.1 `ArtifactRef` — 产物引用

```typescript
interface ArtifactRef {
  artifact_id: string;
  type: string;                          // "text" / "structured" / "image" / "video" / "audio" / "generic"
  reference: string;                     // "oss://bucket/path"
  extra_metadata: Record<string, any>;
}
```

```json
{
  "artifact_id": "8b2f1c4e-...",
  "type": "video",
  "reference": "oss://youle-prod/artifacts/.../video_compose.mp4",
  "extra_metadata": {
    "duration_s": 60,
    "resolution": [1080, 1920],
    "model_used": "moviepy-local"
  }
}
```

### 3.2 `StepResult` — 单步状态(完整)

> 任务详情 API 返回 `task.step_results[step_id]` 时的形态。

```typescript
interface StepResult {
  step_id: string;
  agent_id: AgentId;
  task_type: string;
  status: StepStatus;                    // 见 §6.2
  artifact_ref: string | null;
  artifact_type: string | null;
  artifact_metadata: Record<string, any>;
  duration_ms: number | null;
  cost_usd: number | null;
  model_used: string | null;
  error_detail: Record<string, any> | null;
  started_at: string | null;             // ISO8601
  completed_at: string | null;
  critique: CritiqueDict | null;         // 见 §3.3
}
```

```json
{
  "step_id": "script",
  "agent_id": "agent_1",
  "task_type": "long_writing",
  "status": "completed",
  "artifact_ref": "oss://youle-prod/.../script.txt",
  "artifact_type": "text",
  "artifact_metadata": {"version_count": 3},
  "duration_ms": 4230,
  "cost_usd": 0.0042,
  "model_used": "kimi-k2",
  "error_detail": null,
  "started_at": "2026-05-09T10:23:11.234567+00:00",
  "completed_at": "2026-05-09T10:23:15.464321+00:00",
  "critique": {
    "score": 0.88,
    "threshold_used": 0.7,
    "issues": [],
    "suggestion": "",
    "should_retry": false,
    "model_used": "claude-sonnet-4-6",
    "cost_usd": 0.0008,
    "duration_ms": 1200,
    "skipped_reason": null
  }
}
```

### 3.3 `CritiqueDict` — 评审结果

> 启用 Critic Loop 的创作 step 完成后,该字段会附在 `StepResult` 上。

```typescript
interface CritiqueDict {
  score: number;                         // 0..1
  threshold_used: number;                // 该 step 的阈值
  issues: string[];                      // 各 ≤ 300 字符
  suggestion: string;                    // ≤ 600 字符
  should_retry: boolean;
  model_used: string;
  cost_usd: number | null;
  duration_ms: number | null;
  skipped_reason: string | null;         // 非空 = 该评审跳过(如非文本产物);视为通过
}
```

**示例 — 通过**:

```json
{
  "score": 0.92, "threshold_used": 0.7,
  "issues": [], "suggestion": "", "should_retry": false,
  "model_used": "claude-sonnet-4-6",
  "cost_usd": 0.0008, "duration_ms": 1200, "skipped_reason": null
}
```

**示例 — 不通过**:

```json
{
  "score": 0.4, "threshold_used": 0.7,
  "issues": ["开头钩子缺乏冲突感", "案例缺少具体金额"],
  "suggestion": "改写为以一个真实数字开头",
  "should_retry": true,
  "model_used": "claude-sonnet-4-6",
  "cost_usd": 0.0009, "duration_ms": 1340, "skipped_reason": null
}
```

**示例 — 跳过(非文本产物)**:

```json
{
  "score": 1.0, "threshold_used": 0.7,
  "issues": [], "suggestion": "", "should_retry": false,
  "model_used": "unknown",
  "cost_usd": null, "duration_ms": null,
  "skipped_reason": "non-text artifact_type='image'"
}
```

### 3.4 `Plan` / `PlanStep`(动态规划路径)

> 动态规划开启时,Plan 元信息嵌入 `task.skill_yaml._planner_meta`,可在任务详情中展示。

```typescript
interface PlanStep {
  step_id: string;
  agent: AgentId;
  task_type: string;
  persona: StepPersona;                  // 见 §6.7
  depends_on: string[];
  timeout: number;                       // 秒
  prompt_template: string;
  inputs: Record<string, any>;
  parameters: Record<string, any>;
  routing_hints: Record<string, any>;
  mcp_tools: string[];                   // ["mcp://search/web_search", ...]
  hitl_gate: HITLGateSpec | null;
  budget_tokens: number | null;
  expected_artifact: string | null;
}

interface HITLGateSpec {
  type: string;
  timeout_seconds: number | null;
  actions: string[] | null;
  auto_approve_if_user_offline: boolean | null;
}

interface Plan {
  plan_id: string;
  rationale: string;
  steps: PlanStep[];
  primary_artifact: string | null;
  failure_handling: Record<string, any>;
  source: "planner" | "replanner";
  cognitive_model: string | null;
  estimated_cost_usd: number | null;
  estimated_duration_s: number | null;
}
```

```json
{
  "plan_id": "p-short-video-001",
  "rationale": "5 步:研究 → 脚本 → 图片 → 配乐 → 合成",
  "primary_artifact": "video_compose",
  "source": "planner",
  "cognitive_model": "claude-sonnet-4-6",
  "estimated_cost_usd": 0.05,
  "estimated_duration_s": 300,
  "failure_handling": {},
  "steps": [
    {
      "step_id": "research", "agent": "agent_1", "task_type": "web_search",
      "persona": "researcher", "depends_on": [], "timeout": 120,
      "prompt_template": "搜索 {{年份}} {{内容类型}} 案件 10 条",
      "inputs": {}, "parameters": {"source_profile": "short_video"},
      "routing_hints": {"primary": "deepseek-v4-pro"},
      "mcp_tools": ["mcp://search/web_search"],
      "hitl_gate": null, "budget_tokens": 8000,
      "expected_artifact": "案例表格"
    }
  ]
}
```

### 3.5 `InterruptPayload`(任务详情中的 raw HITL 数据)

> 通过任务详情 API 取 `task.hitl_decisions[step_id]` 上下文时可见;WS 事件中已被重新打包成 §1.6 形态,无需关心。

```typescript
interface InterruptPayload {
  kind: "hitl_gate";
  step_id: string;
  gate_type: HITLGateType;
  timeout_seconds: number | null;
  preview_artifact_ref: string | null;
  preview_artifact_type: string | null;
  preview_artifact_metadata: Record<string, any>;
  task_id: string;
  agent_id: AgentId;
  trace_id: string | null;
  orchestration_run_id: string | null;
}
```

---

## Part 4: 任务级状态(`/api/tasks/:id`)

> 主动拉取一个任务的完整状态。WS 事件流是增量,任务详情 API 是 snapshot。断线重连或刷新页面后用它对齐状态。

```typescript
interface TaskStateSnapshot {
  task_id: string;
  user_id: string;
  conversation_id: string;
  skill_id: string | null;                          // null = 动态 plan
  skill_version: string | null;
  skill_yaml: Record<string, any>;                  // 完整 Skill 定义,可能含 _planner_meta(动态 plan)
  collected_fields: Record<string, any>;            // 用户填写字段
  step_results: Record<string, StepResult>;
  hitl_decisions: Record<string, HITLDecision>;
  rollback_count: number;
  step_dispatch_counts: Record<string, number>;
  orchestration_run_id: string;
  trace_id: string;
  final_status: StepStatus | null;                  // null 表示还在跑
  failure_reason: string | null;
  primary_artifact_ref: string | null;
  primary_artifact_id: string | null;
  messages: any[];                                  // LangGraph 节点日志(展示前过滤)
}

interface HITLDecision {
  resolution: "approved" | "modify_request" | "rejected";
  feedback?: string;
  modify_request?: Record<string, any>;
}
```

---

## Part 5: 用户向智能体的回执

### 5.1 HITL 用户决议(前端 → 后端 → 智能体)

> 用户在 HITL gate 上点 approve / modify / reject 时,前端调后端 API,后端把决议传给智能体的 `runner.resume(...)`。
> 智能体接收的字段定义在 `decision` 参数(由后端组装),前端只需保证 API body 满足后端契约。

```typescript
interface HITLUserDecision {
  resolution: "approved" | "modify_request" | "rejected";
  feedback?: string;                  // ≤ 200 字符
  modify_request?: Record<string, any>; // resolution = "modify_request" 时附带
}
```

```json
{
  "resolution": "modify_request",
  "feedback": "钩子改强一点",
  "modify_request": {
    "section": "opening_hook",
    "instruction": "用真实数字开头,数字要醒目"
  }
}
```

---

## Part 6: 枚举值清单

### 6.1 WS 事件 type

```typescript
type WSEventType =
  | "step_started"
  | "step_completed"
  | "task_completed"
  | "task_failed"
  | "hitl_gate_opened"
  | "hitl_gate_closed"
  | "message_added"
  | "task_rolled_back"
  // 后端独立产生(非智能体侧):
  | "step_streaming"
  | "conversation_created"
  | "conversation_status_changed"
  | "clarification_required"
  | "mode_choice_required"
  | "work_mode_changed"
  | "brief_updated"
  | "quota_warning"
  | "agent_status_changed"
  | "pong";
```

### 6.2 Step 状态

```typescript
type StepStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "pending_external"      // 长任务异步等待中(如 video_compose)
  | "rolled_back";
```

### 6.3 Agent ID

```typescript
type AgentId = "agent_1" | "agent_2" | "agent_3" | "agent_4";
// agent_1 = 文字 / 调研员
// agent_2 = 文档专员
// agent_3 = 设计师
// agent_4 = 影音师
```

### 6.4 HITL Gate 类型

```typescript
type HITLGateType =
  | "version_select"
  | "quality_review"
  | "final_approval"
  | "content_review"
  | "final_review";
```

### 6.5 HITL 解决方案

```typescript
type HITLResolution =
  | "approved"
  | "modified"
  | "rolled_back"
  | "timeout"
  | "cancelled"
  | "rejected";
```

### 6.6 Persona(动态 plan 路径)

```typescript
type StepPersona =
  | "default"
  | "researcher"
  | "critic"
  | "fact_checker"
  | "art_director"
  | "editor"
  | "seo_specialist"
  | "compliance";
```

### 6.7 Artifact Type(loose,常见值)

```typescript
type ArtifactType =
  | "text"
  | "structured"
  | "markdown"
  | "json"
  | "csv"
  | "image"
  | "image_collection"
  | "video"
  | "audio"
  | "generic"
  | string;        // 其他 — handler 可自定义
```

---

## Part 7: 前端集成模式

### 7.1 端到端事件时序(短视频 happy path)

> 5 步短视频任务,启用 Critic Loop + 2 个 HITL gate。

```
T=0.00s   后端创建 task
T=0.01s   前端 WS 收 step_started {step_id: "research", agent_id: "agent_1"}
T=2.40s   前端 WS 收 step_completed {step_id: "research", artifact: {type: "structured", ...}}

T=2.41s   step_started {step_id: "script", agent_id: "agent_1"}
T=2.50s ──┬─ step_streaming {step_id: "script", chunk: "大家好,", seq: 0, done: "0"}
          ├─ step_streaming {chunk: "今天讲一个", seq: 1, done: "0"}
          ├─ ...(数十条)
          └─ step_streaming {chunk: "", seq: 47, done: "1"}
T=8.30s   step_completed {step_id: "script", artifact: {type: "text", ...}}
T=8.31s   hitl_gate_opened {gate: {step_id: "script", gate_type: "version_select", timeout_seconds: 600}, ...}

  [用户点 approve;前端 POST /api/tasks/:id/hitl_gates/:gate_id/approve]

T=15.20s  hitl_gate_closed {gate_id: "...", resolution: "approved"}

T=15.21s ─┬─ step_started {step_id: "image_process", agent_id: "agent_3"}  ┐
          └─ step_started {step_id: "bgm", agent_id: "agent_4"}              │ 并行
T=22.50s  step_completed {step_id: "image_process", ...}                    │
T=23.10s  step_completed {step_id: "bgm", ...}                              ┘

T=23.11s  message_added {message: {kind: "interaction", from_agent: "agent_3", to_agent: "agent_4", text: "设计师:图片好了,@影音师"}}
T=23.12s  step_started {step_id: "video_compose", agent_id: "agent_4"}

  [Celery 长任务 — 期间无 step_streaming]

T=305s    step_completed {step_id: "video_compose", artifact: {type: "video", ...}}
T=305s    hitl_gate_opened {gate: {step_id: "video_compose", gate_type: "final_review", timeout_seconds: 600}, ...}

  [用户点 approve]

T=310s    hitl_gate_closed {gate_id: "...", resolution: "approved"}
T=310s    task_completed {task_id: "...", primary_artifact: {reference: "oss://.../video.mp4"}}
```

### 7.2 WebSocket 重连 + 状态恢复

```typescript
class AgentWS {
  private ws?: WebSocket;
  private lastEventId?: string;       // 后端如支持 last_event_id 续推

  connect(token: string) {
    const url = `wss://api/ws?token=${token}` +
                (this.lastEventId ? `&last_event_id=${this.lastEventId}` : "");
    this.ws = new WebSocket(url);
    this.ws.onmessage = (e) => this.dispatch(JSON.parse(e.data));
    this.ws.onclose = () => setTimeout(() => this.connect(token), 1000);  // 自动重连
  }

  // 重连后立即对齐状态
  async reconcile(taskIds: string[]) {
    for (const id of taskIds) {
      const snapshot = await fetch(`/api/tasks/${id}`).then(r => r.json());
      // 1) 用 snapshot.step_results 重建步骤面板(以服务端为准)
      // 2) 用 snapshot.final_status 决定任务整体状态
      // 3) 检查 snapshot.hitl_decisions 是否有未关闭 gate(continued HITL UI)
      this.store.applyTaskSnapshot(id, snapshot);
    }
  }
}
```

### 7.3 错误兜底(loose `error_detail`)

```typescript
function describeError(stepResult: StepResult): string {
  const ed = stepResult.error_detail;
  if (!ed) return "未知错误";
  // 已知 reason 模板做友好文案,其他 fallback 到原 reason / 通用
  const reason = ed.reason || ed.error || ed.error_message;
  if (ed.type === "permanent_error") return "请求格式错误,请联系支持";
  if (ed.type === "max_retries_exceeded") return "多次重试失败,请稍后再试";
  if (typeof reason === "string" && reason.includes("timeout")) return "执行超时";
  return reason || "执行失败";
}
```

### 7.4 Skill 进度推导

```typescript
interface SkillProgress {
  total: number;
  completed: number;
  running: string[];       // 当前并行 running 的 step_id 集合
  failed: string[];
}

function deriveSkillProgress(taskSnapshot: TaskStateSnapshot): SkillProgress {
  const workflow = taskSnapshot.skill_yaml.workflow as { step_id: string }[];
  const total = workflow.length;
  const sr = taskSnapshot.step_results;
  return {
    total,
    completed: workflow.filter(s => sr[s.step_id]?.status === "completed").length,
    running:   workflow.filter(s => sr[s.step_id]?.status === "running").map(s => s.step_id),
    failed:    workflow.filter(s => sr[s.step_id]?.status === "failed").map(s => s.step_id),
  };
}
```

并行 fan-out 场景下(如短视频的 image_process + bgm)`running` 会同时出现多个 step_id;UI 应支持多 step 同时高亮,而非单线性进度条。

### 7.5 完整 `.d.ts`(可直接 copy 到 `frontend/lib/agent-events.d.ts`)

```typescript
// frontend/lib/agent-events.d.ts
export type AgentId = "agent_1" | "agent_2" | "agent_3" | "agent_4";

export type StepStatus =
  | "pending" | "running" | "completed" | "failed"
  | "pending_external" | "rolled_back";

export type HITLGateType =
  | "version_select" | "quality_review" | "final_approval"
  | "content_review" | "final_review";

export type HITLResolution =
  | "approved" | "modified" | "rolled_back"
  | "timeout" | "cancelled" | "rejected";

export type StepPersona =
  | "default" | "researcher" | "critic" | "fact_checker"
  | "art_director" | "editor" | "seo_specialist" | "compliance";

export interface ArtifactRef {
  artifact_id: string;
  type: string;
  reference: string;
  extra_metadata: Record<string, any>;
}

export interface CritiqueDict {
  score: number;
  threshold_used: number;
  issues: string[];
  suggestion: string;
  should_retry: boolean;
  model_used: string;
  cost_usd: number | null;
  duration_ms: number | null;
  skipped_reason: string | null;
}

export interface StepResult {
  step_id: string;
  agent_id: AgentId;
  task_type: string;
  status: StepStatus;
  artifact_ref: string | null;
  artifact_type: string | null;
  artifact_metadata: Record<string, any>;
  duration_ms: number | null;
  cost_usd: number | null;
  model_used: string | null;
  error_detail: Record<string, any> | null;
  started_at: string | null;
  completed_at: string | null;
  critique: CritiqueDict | null;
}

export interface HITLDecision {
  resolution: "approved" | "modify_request" | "rejected";
  feedback?: string;
  modify_request?: Record<string, any>;
}

export interface TaskStateSnapshot {
  task_id: string;
  user_id: string;
  conversation_id: string;
  skill_id: string | null;
  skill_version: string | null;
  skill_yaml: Record<string, any>;
  collected_fields: Record<string, any>;
  step_results: Record<string, StepResult>;
  hitl_decisions: Record<string, HITLDecision>;
  rollback_count: number;
  step_dispatch_counts: Record<string, number>;
  orchestration_run_id: string;
  trace_id: string;
  final_status: StepStatus | null;
  failure_reason: string | null;
  primary_artifact_ref: string | null;
  primary_artifact_id: string | null;
  messages: any[];
}

// ─── WS 事件 ───
interface WSEventBase { type: string }

export interface StepStarted extends WSEventBase {
  type: "step_started";
  task_id: string;
  step_id: string;
  agent_id?: AgentId;
}

export interface StepCompleted extends WSEventBase {
  type: "step_completed";
  task_id: string;
  step_id: string;
  artifact: {
    artifact_id: string | null;
    type: string | null;
    reference: string | null;
    metadata: Record<string, any>;
  } | null;
}

export interface TaskCompleted extends WSEventBase {
  type: "task_completed";
  task_id: string;
  primary_artifact: { reference: string } | null;
}

export interface TaskFailed extends WSEventBase {
  type: "task_failed";
  task_id: string;
  step_id?: string;
  artifact?: object | null;
  primary_artifact?: object | null;
}

export interface HITLGateOpened extends WSEventBase {
  type: "hitl_gate_opened";
  task_id: string;
  gate: {
    id: string;
    step_id: string;
    gate_type: HITLGateType;
    timeout_seconds: number;
  };
  preview_artifact: {
    artifact_id: string | null;
    type: string | null;
    reference: string | null;
    metadata: Record<string, any>;
  };
}

export interface HITLGateClosed extends WSEventBase {
  type: "hitl_gate_closed";
  task_id: string;
  gate_id: string;
  resolution: HITLResolution;
}

export interface MessageAdded extends WSEventBase {
  type: "message_added";
  conversation_id: string;
  message: {
    id: string;
    conversation_id: string;
    role: AgentId;
    kind: "interaction";
    text: string;
    from_agent: AgentId;
    to_agent: AgentId;
  };
}

export interface TaskRolledBack extends WSEventBase {
  type: "task_rolled_back";
  task_id: string;
  target_step_id: string;
  cleared_steps: string[];
  rollback_count: number | null;
}

export interface StepStreaming extends WSEventBase {
  type: "step_streaming";
  task_id: string;
  step_id: string;
  chunk: string;
  done?: "0" | "1";
  seq?: number;
}

export type AgentWSEvent =
  | StepStarted
  | StepCompleted
  | TaskCompleted
  | TaskFailed
  | HITLGateOpened
  | HITLGateClosed
  | MessageAdded
  | TaskRolledBack
  | StepStreaming;

// ─── 前端 → 后端 用户回执 ───
export interface HITLUserDecisionPayload {
  resolution: "approved" | "modify_request" | "rejected";
  feedback?: string;
  modify_request?: Record<string, any>;
}
```

### 7.6 事件分发样例

```typescript
import type { AgentWSEvent } from "./agent-events";

function dispatchAgentEvent(event: AgentWSEvent, store: AgentStore) {
  switch (event.type) {
    case "step_started":
      store.markStepStarted(event.task_id, event.step_id, event.agent_id);
      break;
    case "step_streaming":
      store.appendChunk(event.task_id, event.step_id, event.chunk, event.done === "1");
      break;
    case "step_completed":
      store.markStepCompleted(event.task_id, event.step_id, event.artifact);
      break;
    case "task_completed":
      store.markTaskCompleted(event.task_id, event.primary_artifact);
      break;
    case "task_failed":
      store.markTaskFailed(event.task_id, event.step_id, event);
      break;
    case "hitl_gate_opened":
      store.openHITLGate(event);
      break;
    case "hitl_gate_closed":
      store.closeHITLGate(event.task_id, event.gate_id, event.resolution);
      break;
    case "message_added":
      store.appendMessage(event.conversation_id, event.message);
      break;
    case "task_rolled_back":
      store.applyRollback(event.task_id, event.target_step_id, event.cleared_steps);
      break;
  }
}
```

---

## 附录:Schema 定义索引

| 文件 | 关键 schema |
|---|---|
| [agents/_common/protocol.py](../../agents/_common/protocol.py) | `ArtifactRef` |
| [agents/orchestrator_agent/langgraph_runner/state.py](../../agents/orchestrator_agent/langgraph_runner/state.py) | `StepResult`, `TaskState` |
| [agents/orchestrator_agent/langgraph_runner/critic_node.py](../../agents/orchestrator_agent/langgraph_runner/critic_node.py) | `CritiqueResult` |
| [agents/orchestrator_agent/langgraph_runner/runner.py](../../agents/orchestrator_agent/langgraph_runner/runner.py) | WS 事件 emit 入口 |
| [agents/orchestrator_agent/hitl_gate.py](../../agents/orchestrator_agent/hitl_gate.py) | `hitl_gate_opened` 事件源 |
| [agents/orchestrator_agent/interaction.py](../../agents/orchestrator_agent/interaction.py) | `message_added`(`kind: interaction`)事件源 |
| [agents/orchestrator_agent/planner/plan_schema.py](../../agents/orchestrator_agent/planner/plan_schema.py) | `Plan`, `PlanStep`, `HITLGateSpec` |
| `app/schemas/ws.py`(backend) | `WSEventType` enum + Pydantic 子类 |
