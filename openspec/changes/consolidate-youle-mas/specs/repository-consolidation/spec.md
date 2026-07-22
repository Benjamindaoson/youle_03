## ADDED Requirements

### Requirement: Canonical generic video capability
The active product SHALL expose one generic `short_video` capability and SHALL NOT contain the retired topic-specific positioning in runtime code, MCP configuration, frontend copy, operational documentation, or canonical Skill data.

#### Scenario: Existing database upgrades
- **WHEN** migration `0007` is applied to a database containing the retired Skill row
- **THEN** that row is archived and private while `short_video` remains published and public

### Requirement: Bidirectional full-stack contract parity
Every production frontend REST request, SSE subscription, and WebSocket interaction SHALL resolve to a canonical backend route and compatible schema. Every user-facing backend capability SHALL either have a frontend consumer or be explicitly classified as backend-only with a reason.

#### Scenario: Contract audit runs
- **WHEN** the bidirectional contract matrix is generated
- **THEN** no production frontend call is missing a backend implementation and no required product surface is represented only in the frontend

### Requirement: Evidence-based debt removal
Dead or duplicate code SHALL be deleted only when reference analysis and regression tests prove that the canonical path does not depend on it.

#### Scenario: A cleanup candidate is removed
- **WHEN** a module, dependency, flag, or adapter is deleted
- **THEN** affected unit, contract, integration, build, and runtime checks still pass through the surviving interface

### Requirement: Safe source repository retirement
The project SHALL retain one target GitHub repository. Source repositories SHALL NOT be deleted before the target change is merged and the merged default branch passes installation, migration, test, build, and startup verification.

#### Scenario: Retirement gate passes
- **WHEN** the target PR is merged, the exact source repository list is confirmed, and merged-default verification succeeds
- **THEN** the three confirmed source repositories may be deleted and the target repository remains available
