## ADDED Requirements

### Requirement: Single active product identity
The system MUST use `haole` in tracked runtime code, configuration, package metadata, tests, current documentation, Compose defaults, and user-visible frontend text.

#### Scenario: Identity guard
- **WHEN** the tracked-file identity test runs
- **THEN** it reports no retired product marker in any UTF-8 file path or content.

#### Scenario: Canonical repository
- **WHEN** a developer opens the canonical GitHub repository
- **THEN** its repository name is `haole`.

### Requirement: Renamed local defaults
The system MUST create development database, storage, and Compose resources associated with `haole`.

#### Scenario: Fresh core setup
- **WHEN** core setup runs without existing local data
- **THEN** its generated environment and Docker resources use `haole`.
