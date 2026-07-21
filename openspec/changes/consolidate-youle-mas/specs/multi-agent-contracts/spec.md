## ADDED Requirements

### Requirement: Single orchestrated group pipeline
Group messages SHALL flow through the canonical backend message pipeline, LangGraph orchestrator, Skill matcher, AgentTask Redis stream, Agent Worker, MCP, AgentResult, unified event publisher, and frontend.

#### Scenario: Group task matches a Skill
- **WHEN** a user sends a group task that matches an enabled Skill
- **THEN** one canonical AgentTask is dispatched and its AgentResult returns through the unified event publisher

### Requirement: Safe mention and private chat routing
The backend SHALL support validated single @Agent mention routing and private Agent conversations without allowing Agent-to-Agent direct calls.

#### Scenario: User mentions an allowed Agent
- **WHEN** a user provides one allowed mention in a group message
- **THEN** the canonical message pipeline routes the user request to that Agent and records the response

### Requirement: Cross-module schema parity
Backend and Agent definitions of AgentTask and AgentResult SHALL remain structurally compatible, and frontend message/event types SHALL be generated or checked against backend schemas.

#### Scenario: Contract CI runs
- **WHEN** an AgentTask, AgentResult, Skill, or event schema changes
- **THEN** contract CI fails unless dependent schemas and generated frontend types are synchronized

### Requirement: No direct LLM or Agent cross-calls
Agent production code MUST use the common LLM Router and MCP client and MUST NOT import OpenAI/Anthropic SDKs or directly invoke another Agent module.

#### Scenario: Forbidden import is added
- **WHEN** an Agent file imports a direct model SDK or calls another Agent
- **THEN** agents CI fails

