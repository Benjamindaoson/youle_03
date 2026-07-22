# Full-stack contract matrix

Date: 2026-07-22

## Result

Every REST operation called by the production Next.js client exists in FastAPI with the expected HTTP method. This is enforced by `backend/tests/unit/test_frontend_api_contract.py`. The browser-verified path is login → conversation → message/clarification → LangGraph task → Redis Agent worker → HITL approvals → completion artifact.

## Frontend features and backend contracts

| Frontend surface | Backend contract | Delivery to UI | Status |
| --- | --- | --- | --- |
| SMS login | `POST /api/auth/sms/send`, `POST /api/auth/login` | REST | Verified in Chrome |
| Conversation list/create/private chat | `GET/POST /api/conversations`, `POST /api/conversations/private-chat/{agent_id}` | REST + shared query store | Verified |
| Members and messages | `GET .../members`, `GET/POST .../messages` | REST, then durable events | Verified |
| Work mode | `POST .../switch-work-mode` | REST + `work_mode_changed` | Contract tested |
| Clarification | message POST while a clarification is pending | `clarification_required` replay + response message | Verified through three rounds |
| Live Agent execution | `GET .../events` | authenticated SSE with durable replay and `Last-Event-ID` | Verified after a fresh browser reconnect |
| HITL decisions | `POST /api/tasks/{task_id}/hitl_gates/{gate_id}/{approve,modify,cancel}` | `hitl_gate_opened/closed` | Verified with real UUIDs and HTTP 200 |
| Materials | `GET/POST /api/materials`, `DELETE /api/materials/{id}` | REST | URL metadata only; fake byte upload removed |
| Prompt library | `GET/POST /api/prompts`, `DELETE /api/prompts/{id}` | REST | Contract tested |
| Skill market/academy | list, mine, detail, install, enable, disable | REST | Contract tested |
| Results | `GET /api/artifacts` | REST invalidated by artifact/completion events | Verified |
| Profile and quota | profile read/update/stats and quota read | REST | Contract tested |

## User-event consumption

The frontend reducer consumes user-visible execution events: message start/delta, step start/stream/complete, clarification, task start/complete/fail, HITL open/close, artifact addition, Agent status, and work-mode changes. Backend events are persisted before live publication, scoped by user and conversation, and replayed on both first connection and reconnect. Transport/maintenance events such as `pong` do not require UI state.

## Backend-only surfaces

FastAPI also exposes task history/rollback/conflict resolution, brief/memory context, avatar signed upload, billing detail, support responses, Skill drafting, preference vectors, metrics, health, and readiness. These are intentional API/SDK or operations surfaces, not claims of existing frontend screens. They remain decoupled so production clients can adopt them without adding fake buttons to the demo UI.

## Browser evidence

- Conversation: `cf12e4b8-e85d-4571-b474-057d51f8cf1e`
- Task: `5a81f2f6-0c95-4d99-9450-90fccbe9e590`
- Two parallel HITL approval requests used the real task ID and returned HTTP 200.
- Final UI displayed `任务已完成` and `mock://5a81f2f6-0c95-4d99-9450-90fccbe9e590/video_compose`.
- Mock artifact metadata records `external_model_calls: 0`.
