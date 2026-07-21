## 1. Audit and baseline

- [x] 1.1 Add the migration matrix and record repository commits, stacks, duplicate modules, dependency conflicts, tests, CI, and licensing findings.
- [x] 1.2 Create the repository-local Python environment, install backend and Agent development dependencies, and record exact tool versions.
- [x] 1.3 Run Ruff, pytest, compileall, Alembic, frontend-presence, and Docker baseline checks; classify each failure in `docs/migration/BASELINE_REPORT.md`.
- [x] 1.4 Commit the clean audit/OpenSpec/baseline phase separately.

## 2. Blocking CI and contracts

- [x] 2.1 Add a failing CI structure check for required root frontend and blocking backend/agents/frontend/contract/security jobs.
- [x] 2.2 Split root workflows into blocking jobs that run Ruff, compileall, backend pytest, agents pytest, Alembic, frozen frontend install, lint, typecheck, test, and build.
- [x] 2.3 Add Agent import, Skill YAML, AgentTask/AgentResult parity, direct LLM SDK, and cross-Agent call checks.
- [ ] 2.4 Add OpenAPI/frontend type synchronization and Event/Skill contract checks.
- [x] 2.5 Add gitleaks, `.env`, high-risk secret, Python dependency, and Node dependency audit checks.

## 3. Unified event delivery

- [x] 3.1 Write failing unit tests for single/multiple EventBus subscribers, full-queue oldest eviction, unsubscribe, JSON-safe payloads, and Redis-unavailable local fallback.
- [x] 3.2 Implement the minimal bounded EventBus and lifecycle using the existing Redis client.
- [x] 3.3 Write failing model/repository tests for stable event IDs, user/conversation ownership, ordered replay, and `Last-Event-ID` cursor behavior.
- [x] 3.4 Add the `user_events` SQLAlchemy model and append-only Alembic migration, then implement the repository.
- [x] 3.5 Write failing SSE tests for Bearer authentication, 403 ownership, heartbeat, replay, live delivery, and client disconnect cleanup.
- [x] 3.6 Implement the conversation SSE route and unified `UserEvent` Pydantic schema.
- [x] 3.7 Route existing `ws_manager.publish` through the unified publisher and make WebSocket consume the same local EventBus without a second Redis channel.
- [ ] 3.8 Generate/check frontend TypeScript event types and run event/backend regression tests.

## 4. OTP and Skill lifecycle

- [x] 4.1 Write failing OTP tests for send, login, refresh, wrong code, expiry, delivery failure cleanup, and concurrent one-time consumption.
- [x] 4.2 Implement atomic Redis OTP consumption and the smallest delivery-policy service while preserving existing routes and User/JWT models.
- [x] 4.3 Write failing Skill API tests for built-in, uninstalled, installed-enabled, installed-disabled, search, detail metadata, idempotent install, enable, and disable.
- [x] 4.4 Add the Skill lifecycle Alembic change and API/model behavior using canonical YAML metadata; keep subscribe endpoints as compatibility aliases.
- [x] 4.5 Ensure disabled or unvalidated Skills cannot be selected for automatic execution.

## 5. Canonical frontend

- [x] 5.1 Copy the `oye-mas` Next.js frontend into root `frontend/`, remove legacy/mock-only duplicates, normalize package scripts, and prove frozen install plus build before feature edits.
- [ ] 5.2 Add a typed API client with JWT handling, error normalization, explicit `NEXT_PUBLIC_MOCK_MODE`, and generated backend types.
- [ ] 5.3 Add failing frontend tests for login, conversation loading, group messages, private messages, API errors, and shared message state.
- [ ] 5.4 Connect login, conversation list, group chat, private Agent chat, Agent/task status, and @Agent UI to canonical backend APIs.
- [ ] 5.5 Add failing SSE client tests for delta aggregation, duplicate event IDs, reconnect, `Last-Event-ID`, and visible connection errors.
- [ ] 5.6 Implement the SSE client/store integration and HITL/task/artifact updates.
- [ ] 5.7 Add failing Skill marketplace tests and connect list/detail/install/enable/disable/search to real APIs.
- [ ] 5.8 Migrate the non-duplicated `youle01` product landing page and useful group/private chat presentation details without importing its backend, conductor, or duplicate stores.
- [ ] 5.9 Run frontend lint, typecheck, unit tests, build, and existing Playwright scenarios; repair failures.

## 6. End-to-end and data verification

- [ ] 6.1 Add a no-key mock E2E covering login, group creation, Agent member, task, Skill match, AgentTask, Redis dispatch, mock AgentResult, SSE, and frontend completion.
- [ ] 6.2 Verify every Agent service imports, accepts valid AgentTask, rejects invalid schema, uses Router/MCP, and returns structured timeout/retry errors.
- [ ] 6.3 Upgrade a fresh PostgreSQL database through every Alembic revision and verify the final schema contains one model set.
- [ ] 6.4 Start backend, workers, MCP, Redis, PostgreSQL, and frontend; check health/readiness and the primary user flow when local services are available.

## 7. Documentation and delivery

- [ ] 7.1 Add `THIRD_PARTY_NOTICES.md` preserving Hermes/Nous Research attribution and recording the missing root licenses in all four source repositories.
- [ ] 7.2 Rewrite README and add CONTRIBUTING using only existing, verified functionality, commands, environment variables, architecture, events, Agents, Skills, MCP, and known limits.
- [ ] 7.3 Complete `MIGRATION_REPORT.md` and `docs/migration/FINAL_VALIDATION_REPORT.md` with exact migrated/skipped modules, schema/API/UI changes, commands, results, failures, risks, and unverified items.
- [ ] 7.4 Run the full Ruff, pytest, compileall, frontend, Alembic, Docker Compose, health, E2E, secret, dependency, and ship-readiness checks; repair any in-scope failure.
- [ ] 7.5 Review the final diff for duplicate architectures, imports, secrets, env documentation, unnecessary dependencies, attribution, and intent alignment.
- [ ] 7.6 Commit each verified phase, push `codex/youle-mas-consolidation`, and open a Draft PR targeting the default branch without merging it.
