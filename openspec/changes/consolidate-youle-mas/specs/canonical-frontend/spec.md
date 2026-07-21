## ADDED Requirements

### Requirement: One canonical Next.js application
The repository SHALL contain one Next.js application at `frontend/` and SHALL NOT keep nested or legacy frontend applications.

#### Scenario: Frontend CI starts
- **WHEN** the frontend CI job checks out the repository
- **THEN** `frontend/package.json` exists and frozen install, lint, typecheck, test, and build are executed

### Requirement: Required product surfaces
The frontend SHALL provide login, conversation list, group chat, private Agent chat, Agent/task status, HITL actions, Skill marketplace, artifact/material views, and visible error/reconnect state.

#### Scenario: User completes a mock task
- **WHEN** a logged-in user sends a group task in mock mode
- **THEN** the UI shows task progress, streamed Agent output, and the completed artifact

### Requirement: Real API is the production default
The frontend SHALL call the canonical backend REST and SSE endpoints by default, and mock behavior MUST require an explicit environment variable.

#### Scenario: Production build has no mock flag
- **WHEN** the frontend runs without `NEXT_PUBLIC_MOCK_MODE=true`
- **THEN** requests use `NEXT_PUBLIC_API_URL` and failures are shown instead of silently returning mock data

### Requirement: Unified client message state
Group and private chat SHALL use one message model; server data SHALL remain in the API/query layer and Zustand SHALL store only client interaction state.

#### Scenario: Message arrives over SSE
- **WHEN** a message delta event arrives for a known message ID
- **THEN** the existing message is updated without creating a duplicate or starting Agent orchestration in the browser

