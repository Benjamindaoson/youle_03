## ADDED Requirements

### Requirement: Core launcher availability
The supported core launcher MUST start the backend, combined Agent worker, and frontend in no-cost mock mode.

#### Scenario: Core smoke check
- **WHEN** `scripts/core.ps1 start` completes
- **THEN** its frontend URL returns HTTP 200 and `/ready` reports `ok`.
