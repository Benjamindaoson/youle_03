## 1. Audit and baseline

- [x] 1.1 Add the migration matrix and record repository commits, stacks, duplicate modules, dependency conflicts, tests, CI, and licensing findings.
- [x] 1.2 Create the repository-local Python environment, install backend and Agent development dependencies, and record exact tool versions.
- [x] 1.3 Run Ruff, pytest, compileall, Alembic, frontend-presence, and Docker baseline checks; classify each failure in `docs/migration/BASELINE_REPORT.md`.
- [x] 1.4 Commit the clean audit/OpenSpec/baseline phase separately.

## 2. Blocking CI and contracts

- [x] 2.1 Add a failing CI structure check for required root frontend and blocking backend/agents/frontend/contract/security jobs.
- [x] 2.2 Split root workflows into blocking jobs that run Ruff, compileall, backend pytest, agents pytest, Alembic, frozen frontend install, lint, typecheck, test, and build.
- [x] 2.3 Add Agent import, Skill YAML, AgentTask/AgentResult parity, direct LLM SDK, and cross-Agent call checks.
- [x] 2.4 Add OpenAPI/frontend type synchronization and Event/Skill contract checks.
- [x] 2.5 Add gitleaks, `.env`, high-risk secret, Python dependency, and Node dependency audit checks.

## 3. Unified event delivery

- [x] 3.1 Write failing unit tests for single/multiple EventBus subscribers, full-queue oldest eviction, unsubscribe, JSON-safe payloads, and Redis-unavailable local fallback.
- [x] 3.2 Implement the minimal bounded EventBus and lifecycle using the existing Redis client.
- [x] 3.3 Write failing model/repository tests for stable event IDs, user/conversation ownership, ordered replay, and `Last-Event-ID` cursor behavior.
- [x] 3.4 Add the `user_events` SQLAlchemy model and append-only Alembic migration, then implement the repository.
- [x] 3.5 Write failing SSE tests for Bearer authentication, 403 ownership, heartbeat, replay, live delivery, and client disconnect cleanup.
- [x] 3.6 Implement the conversation SSE route and unified `UserEvent` Pydantic schema.
- [x] 3.7 Route existing `ws_manager.publish` through the unified publisher and make WebSocket consume the same local EventBus without a second Redis channel.
- [x] 3.8 Generate/check frontend TypeScript event types and run event/backend regression tests.

## 4. OTP and Skill lifecycle

- [x] 4.1 Write failing OTP tests for send, login, refresh, wrong code, expiry, delivery failure cleanup, and concurrent one-time consumption.
- [x] 4.2 Implement atomic Redis OTP consumption and the smallest delivery-policy service while preserving existing routes and User/JWT models.
- [x] 4.3 Write failing Skill API tests for built-in, uninstalled, installed-enabled, installed-disabled, search, detail metadata, idempotent install, enable, and disable.
- [x] 4.4 Add the Skill lifecycle Alembic change and API/model behavior using canonical YAML metadata; keep subscribe endpoints as compatibility aliases.
- [x] 4.5 Ensure disabled or unvalidated Skills cannot be selected for automatic execution.

## 5. Canonical frontend

- [x] 5.1 Copy the `oye-mas` Next.js frontend into root `frontend/`, remove legacy/mock-only duplicates, normalize package scripts, and prove frozen install plus build before feature edits.
- [x] 5.2 Add a typed API client with JWT handling, error normalization, explicit `NEXT_PUBLIC_MOCK_MODE`, and generated backend types.
- [x] 5.3 Add failing frontend tests for login, conversation loading, group messages, private messages, API errors, and shared message state.
- [x] 5.4 Connect login, conversation list, group chat, private Agent chat, Agent/task status, and @Agent UI to canonical backend APIs.
- [x] 5.5 Add failing SSE client tests for delta aggregation, duplicate event IDs, reconnect, `Last-Event-ID`, and visible connection errors.
- [x] 5.6 Implement the SSE client/store integration and HITL/task/artifact updates.
- [x] 5.7 Add failing Skill marketplace tests and connect list/detail/install/enable/disable/search to real APIs.
- [x] 5.8 Migrate the non-duplicated `youle01` product landing page and useful group/private chat presentation details without importing its backend, conductor, or duplicate stores.
- [x] 5.9 Run frontend lint, typecheck, unit tests, build, and existing Playwright scenarios; repair failures.

## 6. End-to-end and data verification

- [x] 6.1 Add a no-key mock E2E covering login, group creation, Agent member, task, Skill match, AgentTask, Redis dispatch, mock AgentResult, SSE, and frontend completion.
- [x] 6.2 Verify every Agent service imports, accepts valid AgentTask, rejects invalid schema, uses Router/MCP, and returns structured timeout/retry errors.
- [x] 6.3 Upgrade a fresh PostgreSQL database through every Alembic revision and verify the final schema contains one model set.
- [x] 6.4 Start the core backend, combined worker, Redis, PostgreSQL, and frontend; check health/readiness and the primary browser user flow. Keep MCP sidecars in the optional production profile.

## 7. Documentation and delivery

- [x] 7.1 Add `THIRD_PARTY_NOTICES.md` preserving Hermes/Nous Research attribution and recording the missing root licenses in all four source repositories.
- [x] 7.2 Rewrite README and add CONTRIBUTING using only existing, verified functionality, commands, environment variables, architecture, events, Agents, Skills, MCP, and known limits.
- [x] 7.3 Complete `MIGRATION_REPORT.md` and `docs/migration/FINAL_VALIDATION_REPORT.md` with exact migrated/skipped modules, schema/API/UI changes, commands, results, failures, risks, and unverified items.
- [x] 7.4 Run the full Ruff, pytest, compileall, frontend, Alembic, Docker Compose, health, E2E, secret, dependency, and ship-readiness checks; repair any in-scope failure.
- [x] 7.5 Review the final diff for duplicate architectures, imports, secrets, env documentation, unnecessary dependencies, attribution, and intent alignment.
- [x] 7.6 Commit each verified phase, push `codex/youle-mas-consolidation`, and open a Draft PR targeting the default branch without merging it.

## 8. Full-stack parity and debt cleanup

- [x] 8.1 Replace the retired topic-specific video Skill, prompts, examples, MCP defaults, frontend copy, tests, and current documentation with the canonical `short_video` capability; archive the legacy database row by migration.
- [x] 8.2 Generate a bidirectional matrix of every production frontend REST/SSE/WS call and every backend route/event; classify unmatched surfaces and fix all user-facing gaps in scope.
- [x] 8.3 Verify the Agent architecture from message intake through LangGraph, Skill compilation, Redis AgentTask/AgentResult, Worker/MCP execution, unified events, and frontend consumption.
- [x] 8.4 Run a whole-repository over-engineering/dead-code audit; remove only findings proven unused by reference analysis and regression tests, and record deferred debt explicitly.
- [x] 8.5 Repeat targeted backend, Agent, frontend, browser, runtime, contract, and active-copy verification after cleanup; final full suites remain part of ship verification.

## 9. Single repository retirement

- [ ] 9.1 Commit and push the verified cleanup branch, open a PR against the target repository default branch, and merge only after required checks pass.
- [ ] 9.2 Verify the merged default branch can install, migrate, build, test, and start from a fresh checkout.
- [ ] 9.3 Confirm the final target repository identity and the exact three source repositories to retire.
- [ ] 9.4 Delete the three source GitHub repositories only after 9.1-9.3 pass, then verify the account exposes only the target repository for this project.

## 10. Cost-aware runtime profiles

- [x] 10.1 Add contract tests proving the default demo cannot force paid LLM mode and records the exact provider calls made.
- [x] 10.2 Define a minimal `core` runtime that retains FastAPI, LangGraph, frontend, Agent execution, SSE, and one database/queue path while minimizing Docker containers and Python processes.
- [x] 10.3 Provide one unified Agent worker entry point for the core runtime; retain independently scalable workers only in production configuration.
- [x] 10.4 Move optional production infrastructure and deployment settings under a separate `deploy/production/` directory without duplicating application code.
- [x] 10.5 Verify the core mock journey performs zero paid model calls and measure its two-container/three-application-process runtime.
- [ ] 10.6 Fresh-clone the merged canonical repository to the local D: drive and repeat install, migration, start, API, frontend, Agent, and browser verification before repository retirement.
