## ADDED Requirements

### Requirement: Skill lifecycle states
The Skill API SHALL distinguish built-in, installed, uninstalled, enabled, and disabled states per user.

#### Scenario: User installs a public Skill
- **WHEN** a user installs an uninstalled published Skill
- **THEN** the Skill becomes installed and enabled for that user idempotently

#### Scenario: User disables an installed Skill
- **WHEN** a user disables an installed Skill
- **THEN** the Skill remains installed but is excluded from automatic matching

### Requirement: Skill metadata disclosure
Skill list and detail responses SHALL include version, permissions, required MCP tools, and required Agent types derived from the canonical YAML contract.

#### Scenario: User views Skill detail
- **WHEN** a user opens a published Skill detail page
- **THEN** the response shows lifecycle and requirement metadata without exposing executable prompt bodies

### Requirement: No untrusted marketplace execution
The marketplace MUST NOT execute uploaded code; execution SHALL only use validated canonical playbooks under `backend/skills/playbooks/` or their synchronized database representation.

#### Scenario: Unknown Skill has no playbook
- **WHEN** an installed marketplace record has no validated canonical playbook
- **THEN** it can be displayed but cannot be selected for execution

