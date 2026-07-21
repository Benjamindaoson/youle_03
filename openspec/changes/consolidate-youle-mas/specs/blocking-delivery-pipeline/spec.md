## ADDED Requirements

### Requirement: Blocking subsystem CI
Pull requests SHALL run blocking backend, agents, frontend, contract, and security checks from root `.github/workflows/`.

#### Scenario: Frontend directory is missing
- **WHEN** frontend CI runs without `frontend/package.json`
- **THEN** the job fails rather than skipping

#### Scenario: Agents test fails
- **WHEN** an independent Agent pytest fails
- **THEN** the agents job fails

### Requirement: Mock end-to-end path
CI SHALL provide a deterministic `LITELLM_MOCK=true` path covering login, group creation, Agent membership, task submission, Skill matching, AgentTask dispatch, mock execution, AgentResult, SSE, and frontend completion display.

#### Scenario: No provider API keys exist
- **WHEN** the end-to-end test runs without real model credentials
- **THEN** the complete mock path passes without network calls to model providers

### Requirement: Evidence-based reports
The repository SHALL record exact baseline and final commands, exit results, environment blockers, migration decisions, and unverified external-key behavior.

#### Scenario: Docker daemon is unavailable
- **WHEN** Docker verification cannot connect to the daemon
- **THEN** the final validation report marks Docker and dependent checks as blocked rather than passed

### Requirement: Source attribution is preserved
The repository SHALL preserve third-party file headers and SHALL list copied or adapted modules and licenses in `THIRD_PARTY_NOTICES.md`.

#### Scenario: Hermes-derived file is migrated
- **WHEN** a Hermes-derived file is modified or moved
- **THEN** its Nous Research MIT attribution remains present and the notice lists the module
