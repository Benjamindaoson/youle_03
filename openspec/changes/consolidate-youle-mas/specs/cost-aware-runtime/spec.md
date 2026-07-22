## ADDED Requirements

### Requirement: LangGraph remains the orchestration kernel
The system SHALL use LangGraph as its only Agent workflow orchestration kernel in both core and production runtime profiles.

#### Scenario: Core task is submitted
- **WHEN** a user submits a supported task through the core runtime
- **THEN** the task is compiled and executed through the canonical LangGraph runner rather than a second workflow engine

### Requirement: Minimal runnable core profile
The repository SHALL provide a core profile containing the frontend, FastAPI backend, LangGraph orchestrator, Agent execution, database state, task transport, and SSE delivery with the fewest practical long-running processes. Qdrant, dedicated object storage, independent MCP sidecars, and independently scaled Agent workers SHALL NOT be required for the no-key demo.

#### Scenario: Contributor starts the no-key demo
- **WHEN** a fresh checkout is configured with the documented core command and no provider keys
- **THEN** login, conversation creation, task submission, Agent execution, progress events, and frontend completion work without starting optional production services

### Requirement: Paid model calls are explicit and bounded
Mock mode SHALL make zero external model calls. Live mode SHALL require explicit configuration and SHALL expose per-task call and token budgets without silently changing from mock to live.

#### Scenario: Mock demo runs
- **WHEN** `LITELLM_MOCK=true`
- **THEN** no script or runtime module overwrites it and the completed task reports zero paid provider calls

### Requirement: Production adapters are separately deployable
Optional production deployment configuration SHALL live under `deploy/production/` and SHALL reuse the same application interfaces. It MAY enable independent Workers, MCP sidecars, Redis scaling, object storage, vector search, and external model routing without duplicating the core business implementation.

#### Scenario: Production profile is selected
- **WHEN** an operator uses the production deployment configuration
- **THEN** production adapters replace or scale the core adapters at existing seams while frontend and backend contracts remain unchanged

### Requirement: Fresh checkout proof precedes repository deletion
The merged canonical repository SHALL be cloned to the local D: drive and verified from that checkout before any source GitHub repository is deleted.

#### Scenario: Retirement gate is evaluated
- **WHEN** the final default branch is available
- **THEN** frozen dependency installation, migrations, backend health, frontend load, Agent task execution, SSE completion, and browser flow pass from the D: drive checkout before deletion is allowed
