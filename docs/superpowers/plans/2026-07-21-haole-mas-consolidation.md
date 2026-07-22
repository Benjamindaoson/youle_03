# haole MAS Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the four haole repositories into one runnable `haole-mas` project while preserving `haole_03` as the only backend and orchestration trunk.

**Architecture:** Keep `backend/` and `agents/` unchanged as the canonical FastAPI/LangGraph/Redis/MCP boundary, add one `frontend/`, and introduce one `UserEvent` publisher shared by PostgreSQL replay, Redis Pub/Sub, SSE, and WebSocket. Extend existing OTP and Skill models instead of importing alternative auth, Agno, or task systems.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy async, Alembic, PostgreSQL 16, Redis 7, LangGraph, pytest, Ruff, Next.js, React, TypeScript, pnpm, Vitest, Playwright, GitHub Actions.

## Global Constraints

- `haole_03@14815ee` is the only trunk; never copy `haole01/backend`, `oye-mas/haole/backend`, or `haole-agno/src` as a second runtime.
- The only formal roots are `backend/`, `agents/`, and `frontend/`.
- Every behavior change follows RED → GREEN → regression verification.
- Every database change is a new Alembic revision; never edit existing revisions or call `create_all` at startup.
- Agents never import provider SDKs, call another Agent directly, or bypass LiteLLM/MCP/AgentTask.
- Production frontend uses the real API unless `NEXT_PUBLIC_MOCK_MODE=true` is explicitly set.
- Real-provider model tests are optional; `LITELLM_MOCK=true` is the blocking CI path.
- Preserve Hermes/Nous Research MIT headers and record attribution.

---

### Task 1: Audit, isolated environment, and baseline

**Files:**
- Modify: `.gitignore`
- Create: `docs/migration/BASELINE_REPORT.md`
- Modify: `openspec/changes/consolidate-haole-mas/tasks.md`

**Interfaces:**
- Consumes: clean branch `codex/haole-mas-consolidation` and `docs/migration/MIGRATION_MATRIX.md`.
- Produces: reproducible local toolchain and an evidence-only baseline report.

- [ ] **Step 1: Protect the project-local environment**

Add exactly:

```gitignore
.venv/
```

- [ ] **Step 2: Create and populate the environment**

Run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]" -e ".\agents[dev]" -e ".\agents\mcp_servers"
```

Expected: all commands exit 0 without using the global Python package directory.

- [ ] **Step 3: Run baseline checks without hiding failures**

Run and record exit codes:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\python.exe -m compileall backend agents
Set-Location backend
..\.venv\Scripts\alembic.exe upgrade head
Set-Location ..
docker compose -f deploy/production/docker-compose.yml -f deploy/production/docker-compose.mock.yml config
```

Expected: actual results are copied to `BASELINE_REPORT.md`; missing frontend and unavailable Docker daemon are reported as baseline facts, not migration regressions.

- [ ] **Step 4: Commit the baseline phase**

```bash
git add .gitignore .codex openspec docs/migration docs/superpowers
git commit -m "chore: establish haole_03 consolidation baseline"
```

### Task 2: Blocking CI structure

**Files:**
- Create: `backend/tests/unit/test_ci_contract.py`
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/security.yml`
- Create: `backend/scripts/check-contracts.py`

**Interfaces:**
- Consumes: project commands from each manifest.
- Produces: `python backend/scripts/check-contracts.py` and blocking root workflows.

- [ ] **Step 1: Write the failing workflow contract test**

```python
from pathlib import Path


def test_ci_requires_all_blocking_jobs() -> None:
    workflow = Path("../.github/workflows/ci.yml").read_text(encoding="utf-8")
    for job in ("backend-ci:", "agents-ci:", "frontend-ci:", "contract-ci:"):
        assert job in workflow
    assert "continue-on-error" not in workflow
    assert "frontend/package.json" in workflow
    assert "pnpm install --frozen-lockfile" in workflow
```

- [ ] **Step 2: Verify RED**

Run: `.venv/Scripts/pytest.exe backend/tests/unit/test_ci_contract.py -q`  
Expected: FAIL because the current workflow uses `backend`, `agents`, `frontend`, and skips missing frontend.

- [ ] **Step 3: Implement the minimal blocking jobs**

Rename jobs to `backend-ci`, `agents-ci`, `frontend-ci`, `contract-ci`; remove detection/skip and shell fallbacks; add agents pytest, frontend test/build, compileall, Alembic, and `check-contracts.py`. Put gitleaks, pip-audit, pnpm audit, `.env`, and default-secret checks in `security.yml`.

- [ ] **Step 4: Verify GREEN and workflow syntax**

Run:

```powershell
.\.venv\Scripts\pytest.exe backend/tests/unit/test_ci_contract.py -q
.\.venv\Scripts\python.exe backend/scripts/check-contracts.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github backend/scripts backend/tests/unit/test_ci_contract.py
git commit -m "ci: make backend agents frontend and contract checks blocking"
```

### Task 3: Unified event model and bounded EventBus

**Files:**
- Create: `backend/app/schemas/events.py`
- Create: `backend/app/services/event_bus.py`
- Create: `backend/tests/unit/test_event_bus.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: `EventType`, `UserEvent`, `EventBus.subscribe(user_id)`, `EventBus.unsubscribe(user_id, queue)`, `EventBus.publish_local(event)`, `EventBus.start()`, and `EventBus.stop()`.

- [ ] **Step 1: Write failing EventBus tests**

The test module must assert one subscriber, two subscribers, unsubscribe, oldest eviction, UUID/datetime JSON serialization, and local fallback after Redis publish raises.

```python
@pytest.mark.asyncio
async def test_full_queue_drops_oldest() -> None:
    bus = EventBus(queue_size=2, redis_factory=None)
    queue = await bus.subscribe("user-1")
    await bus.publish_local(UserEvent(type=EventType.TASK_STARTED, user_id="user-1", payload={"n": 1}))
    await bus.publish_local(UserEvent(type=EventType.TASK_PROGRESS, user_id="user-1", payload={"n": 2}))
    await bus.publish_local(UserEvent(type=EventType.TASK_COMPLETED, user_id="user-1", payload={"n": 3}))
    assert (await queue.get()).payload == {"n": 2}
    assert (await queue.get()).payload == {"n": 3}
```

- [ ] **Step 2: Verify RED**

Run: `.venv/Scripts/pytest.exe backend/tests/unit/test_event_bus.py -q`  
Expected: import failure because the modules do not exist.

- [ ] **Step 3: Implement minimal schema and bus**

`UserEvent` uses UUID v4 IDs and UTC timestamps. `EventBus` keeps `dict[str, WeakSet[Queue[UserEvent]]]`, bounds every queue, and uses Redis channel `haole:events:{user_id}`. Redis failure calls `publish_local` and logs one warning.

- [ ] **Step 4: Add lifecycle and verify GREEN**

Start/stop the bus in FastAPI lifespan. Run the focused test and `ruff check backend/app/schemas/events.py backend/app/services/event_bus.py backend/tests/unit/test_event_bus.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests/unit/test_event_bus.py
git commit -m "feat: add unified event bus"
```

### Task 4: Persistent replay, SSE, and WebSocket compatibility

**Files:**
- Create: `backend/app/models/event.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260721_0005_user_events.py`
- Create: `backend/app/services/event_publisher.py`
- Create: `backend/app/api/streams.py`
- Modify: `backend/app/api/ws.py`
- Modify: `backend/app/ws/manager.py`
- Create: `backend/tests/unit/test_event_replay.py`
- Create: `backend/tests/unit/test_sse.py`

**Interfaces:**
- Produces: `publish_user_event(...) -> UserEvent`, `GET /api/conversations/{conversation_id}/events`, and a compatibility `ws_manager.publish()` delegate.

- [ ] **Step 1: Write replay and SSE failing tests**

Tests must cover missing token 401, non-owner 403, owner 200 with `text/event-stream`, heartbeat, two ordered replay events after a cursor, live event, and unsubscribe on disconnect.

- [ ] **Step 2: Verify RED**

Run: `.venv/Scripts/pytest.exe backend/tests/unit/test_event_replay.py backend/tests/unit/test_sse.py -q`  
Expected: FAIL because model, publisher, and route are missing.

- [ ] **Step 3: Add append-only event migration and repository**

Create `user_events(id UUID PK, user_id UUID FK, conversation_id UUID NULL FK, task_id UUID NULL, agent_id VARCHAR NULL, type VARCHAR NOT NULL, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL)` plus `(user_id, id)` and `(conversation_id, created_at)` indexes. Do not edit existing revisions.

- [ ] **Step 4: Implement publisher and SSE generator**

Persist best-effort, then publish through EventBus. SSE authenticates with `get_current_user_id`, verifies `Conversation.user_id`, replays after the cursor, emits `id/event/data`, sends heartbeat comments, and always unsubscribes.

- [ ] **Step 5: Unify WebSocket transport**

Make `ws_manager.publish()` delegate to `event_publisher.publish_user_event`. Make the WebSocket endpoint subscribe to EventBus and forward `UserEvent.model_dump(mode="json")`; remove its independent `haole.ws` Redis listener.

- [ ] **Step 6: Verify GREEN**

Run focused tests, all auth/conversation/message tests, Ruff, compileall, and Alembic upgrade/current.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat: add authenticated SSE delivery and replay"
```

### Task 5: OTP atomic consumption and Skill lifecycle

**Files:**
- Create: `backend/app/services/auth/otp.py`
- Modify: `backend/app/api/auth.py`
- Create: `backend/tests/unit/test_auth_api.py`
- Modify: `backend/app/models/skill.py`
- Modify: `backend/app/api/skills.py`
- Create: `backend/alembic/versions/20260721_0006_skill_lifecycle.py`
- Create: `backend/tests/unit/test_skill_marketplace.py`

**Interfaces:**
- Produces: `consume_otp(redis, phone, code) -> bool`; `POST /api/skills/{id}/install|enable|disable`; lifecycle fields in SkillCard/SkillDetail.

- [ ] **Step 1: Write OTP failing tests**

Cover send, correct login, incorrect code, missing/expired code, refresh, provider failure deletion, and two concurrent attempts where only one succeeds.

- [ ] **Step 2: Implement atomic compare-and-delete**

Use one Redis Lua script:

```lua
local value = redis.call('GET', KEYS[1])
if value == ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
```

Keep existing routes and User/JWT models.

- [ ] **Step 3: Write Skill lifecycle failing tests**

Assert built-in, uninstalled, installed-enabled, installed-disabled, search, metadata, idempotent install, enable, disable, and exclusion of disabled Skills from automatic selection.

- [ ] **Step 4: Implement the minimal lifecycle**

Reuse `UserSkillVisibility.relationship` values `installed_enabled` and `installed_disabled`; expose `installed`, `enabled`, `builtin`, `required_mcp_tools`, `required_agent_types`, and `permissions`. Compatibility subscribe calls install; unsubscribe removes user state.

- [ ] **Step 5: Verify and commit**

Run focused tests, Skill loader/matcher tests, Ruff, Alembic. Commit:

```bash
git commit -m "refactor: harden otp and skill lifecycle contracts"
```

### Task 6: Canonical frontend baseline and typed API client

**Files:**
- Create: `frontend/` from `source-oye-mas/haole/frontend/`
- Modify: `frontend/package.json`
- Modify: `frontend/lib/api.ts`
- Create: `frontend/lib/events.ts`
- Create: `frontend/lib/api.test.ts`
- Create: `frontend/lib/events.test.ts`

**Interfaces:**
- Produces: one `apiRequest<T>()`, one `subscribeConversationEvents()`, shared `Message` and `UserEvent` types, explicit mock flag.

- [ ] **Step 1: Copy only the canonical application**

Copy `app`, `components`, `stores`, `lib`, `public`, configs, lockfile, and existing `e2e`; exclude caches, `tsconfig.tsbuildinfo`, legacy archives, and backend files.

- [ ] **Step 2: Prove the imported baseline**

Run:

```powershell
Set-Location frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
Set-Location ..
```

Record source baseline failures before behavior edits.

- [ ] **Step 3: Write failing API/event tests**

Test Authorization header, non-2xx normalization, no implicit mock fallback, event ID dedupe, delta aggregation, and reconnect cursor persistence.

- [ ] **Step 4: Implement the minimal typed clients**

All components use `NEXT_PUBLIC_API_URL`; only `NEXT_PUBLIC_MOCK_MODE === "true"` selects mock. SSE uses `fetch` with Authorization so bearer tokens are not put in query strings.

- [ ] **Step 5: Verify and commit**

Run lint/typecheck/test/build and commit:

```bash
git add frontend
git commit -m "feat: migrate canonical frontend and typed api client"
```

### Task 7: Product flows, SSE UI, and haole01 product presentation

**Files:**
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/app/chat/[conversationId]/page.tsx`
- Create: `frontend/app/private/[agentId]/page.tsx`
- Modify: `frontend/app/market/page.tsx`
- Modify: `frontend/components/chat/*`
- Modify: `frontend/components/hitl/*`
- Modify: `frontend/stores/{conversation,task,hitl,ws}.ts`
- Create: `frontend/app/website/` from non-duplicated `haole01` product components
- Create: `frontend/app/login/page.test.tsx`
- Create: `frontend/components/chat/ChatPanel.test.tsx`
- Create: `frontend/components/hitl/ScriptApproval.test.tsx`
- Create: `frontend/app/market/page.test.tsx`
- Create: `frontend/stores/ws.test.ts`

**Interfaces:**
- Consumes: canonical REST and `UserEvent` clients.
- Produces: login, group/private chat, progress, HITL, market, materials/artifacts, reconnect UI.

- [ ] **Step 1: Write failing screen/store tests**

Cover login, conversations, group message, private message, task state, HITL action, Skill install/enable/disable, API failure, SSE reconnect, and delta rendering.

- [ ] **Step 2: Connect canonical APIs**

Remove `mock-data` production imports and component-level fetch calls. The browser submits user intent only; Agent/Skill selection returned by backend is rendered, not recomputed.

- [ ] **Step 3: Migrate unique haole01 presentation**

Bring the product landing page and useful visual chat elements into existing components; do not copy `chat-store.ts`, `store.ts`, legacy routes, direct conductor APIs, or default mocks.

- [ ] **Step 4: Verify frontend**

Run focused tests followed by lint, typecheck, all unit tests, build, and Playwright with mock backend.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: integrate group chat agent presence and skill marketplace"
```

### Task 8: Mock end-to-end and Agent contracts

**Files:**
- Create: `backend/tests/integration/test_mock_user_flow.py`
- Create: `agents/tests/unit/test_text_agent_contract.py`
- Create: `agents/tests/unit/test_document_agent_contract.py`
- Create: `agents/tests/unit/test_image_agent_contract.py`
- Create: `agents/tests/unit/test_av_agent_contract.py`
- Modify: `frontend/e2e/short-video-happy-path.spec.ts`
- Modify: `backend/scripts/check-contracts.py`

**Interfaces:**
- Produces: one no-key chain from OTP to frontend completion and per-Agent contract checks.

- [ ] **Step 1: Write failing backend mock flow**

Exercise login → group → member → message → enabled Skill → AgentTask → mock AgentResult → event row/SSE. Use real schemas and fake external boundaries only.

- [ ] **Step 2: Add per-Agent contract tests**

Each worker imports, parses valid AgentTask, rejects invalid schema, has no provider imports/cross-Agent calls, routes LLM/MCP, and structures timeout/retry errors.

- [ ] **Step 3: Implement only missing glue**

Reuse the existing dispatcher, Redis consumer, mock LLM, result stream, and publisher. Do not add an E2E-only production API.

- [ ] **Step 4: Verify and commit**

Run backend integration, all agents tests, contract script, and Playwright. Commit:

```bash
git commit -m "test: add mock multi-agent sse end-to-end coverage"
```

### Task 9: Documentation, full verification, and Draft PR

**Files:**
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `CONTRIBUTING.md`
- Create: `MIGRATION_REPORT.md`
- Create: `docs/migration/FINAL_VALIDATION_REPORT.md`
- Modify: `README.md`
- Modify: `openspec/changes/consolidate-haole-mas/tasks.md`

**Interfaces:**
- Produces: evidence-based handoff, commits, pushed branch, and Draft PR.

- [ ] **Step 1: Write factual documentation**

Document only commands and features proven during this branch. State that four source repositories have no root license and preserve all Hermes attribution. Mark real-provider and unavailable-environment checks `未验证` or `Blocked`.

- [ ] **Step 2: Run full verification**

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\python.exe -m compileall backend agents
Set-Location frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
Set-Location ..\backend
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\alembic.exe current
Set-Location ..
docker compose -f deploy/production/docker-compose.yml -f deploy/production/docker-compose.mock.yml config
docker compose -f deploy/production/docker-compose.yml -f deploy/production/docker-compose.mock.yml up -d --build
```

- [ ] **Step 3: Perform ship-readiness review**

Inspect `git diff --check`, duplicate roots, broken imports, secrets, env docs, dependency additions, generated types, Alembic heads, attribution, and each OpenSpec scenario.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md CONTRIBUTING.md MIGRATION_REPORT.md THIRD_PARTY_NOTICES.md docs openspec
git commit -m "docs: add migration report and update architecture"
```

- [ ] **Step 5: Push and open Draft PR**

```bash
git push -u origin codex/haole-mas-consolidation
gh pr create --draft --base main --title "Consolidate haole repositories into unified haole-mas platform" --body-file .github/PULL_REQUEST_TEMPLATE.md
```

Expected: Draft PR URL returned; do not merge.
