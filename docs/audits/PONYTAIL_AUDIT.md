# Whole-repository simplicity and debt audit

Date: 2026-07-22

## Outcome

The canonical runtime is one backend, one combined Agent worker, one frontend, PostgreSQL, and Redis. Optional production infrastructure is isolated under `deploy/production/`; there is no second application implementation.

## Deleted

- The second frontend real-time client (`lib/ws.ts`) and its duplicate protocol/store path.
- Four fake HITL/share components and fake conversation/message/settings/profile/upload actions.
- Hard-coded Agent execution groups, durations, progress, and mojibake mock execution types.
- Retired topic-specific Skill copies, fixtures, E2E scripts, prompts, copy, and stale business-positioning documents.
- Four large legacy business/positioning decision documents whose examples contradicted the current product; six still-relevant Agent ADRs were retained and updated to the canonical Skill.
- Root startup orchestration that required many independent workers and optional services for a demo.
- Unused frontend dependency/config entries found during frozen install and build repair.

## Kept deliberately

- LangGraph checkpoint, interrupt, replay, and time-travel code: it is the selected workflow kernel and is exercised by tests.
- Redis: it is both the lightweight Agent queue and the cross-process event bus; removing it would require a second local-only architecture.
- PostgreSQL: it stores application state, durable user events, and LangGraph checkpoints in one service.
- Production-only MCP, object storage, vector search, LiteLLM, Kubernetes, and split workers: retained as optional configuration, not started by the core profile.
- Explicit mock data behind `NEXT_PUBLIC_MOCK_MODE`: retained for isolated frontend development; production mode defaults off.

## Deferred, explicit debt

- The legacy WebSocket endpoint remains a compatibility transport over the same event bus. The canonical frontend uses SSE; remove WebSocket only after confirming no external SDK client depends on it.
- Next.js development mode uses more memory than a production build. Server deployment must use `pnpm build` + `pnpm start`, not the local `dev` command.
- Several backend SDK/operations APIs intentionally have no demo UI. They are listed in the full-stack matrix instead of being represented by non-functional controls.

## Measured gain

Relative to the branch base, the cleanup removes 9,045 lines while adding 1,552 lines of fixes, tests, startup tooling, and documentation. Net: -7,493 lines, with one duplicate real-time architecture and multiple fake UI surfaces eliminated. Core startup uses 2 containers instead of the optional full infrastructure stack, and 1 Agent worker instead of 4 independent worker processes.

`net: -7,493 lines, -10 frontend dependencies.`
