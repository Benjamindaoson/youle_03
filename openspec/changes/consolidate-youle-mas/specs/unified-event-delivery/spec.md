## ADDED Requirements

### Requirement: Single business event publisher
The backend SHALL expose one transport-neutral user event publisher, and business services MUST NOT choose SSE, WebSocket, or Redis directly.

#### Scenario: Publish task completion
- **WHEN** a task completion service publishes a user event
- **THEN** the same event ID and payload are available to every active transport subscriber

### Requirement: Bounded multi-subscriber delivery
The event bus SHALL support multiple queues per user and SHALL drop the oldest queued event when a subscriber queue is full.

#### Scenario: Queue reaches capacity
- **WHEN** a new event is published to a full subscriber queue
- **THEN** the oldest event is removed and the newest event is queued

### Requirement: Redis distribution with local fallback
The event bus SHALL distribute events across backend processes through Redis Pub/Sub and SHALL continue local delivery when Redis is unavailable.

#### Scenario: Redis publish fails
- **WHEN** Redis is unavailable during event publication
- **THEN** local subscribers still receive the event and a structured warning is recorded

### Requirement: Authenticated SSE with replay
The backend SHALL provide a Bearer-authenticated conversation SSE stream with ownership checks, heartbeat, stable event IDs, `Last-Event-ID` replay, reconnect support, and disconnect cleanup.

#### Scenario: Owner reconnects
- **WHEN** a conversation owner reconnects with a valid `Last-Event-ID`
- **THEN** events after that ID are replayed in order before live delivery resumes

#### Scenario: Different user requests stream
- **WHEN** an authenticated user requests another user's conversation stream
- **THEN** the backend returns HTTP 403 and emits no events

### Requirement: Shared SSE and WebSocket contract
SSE and WebSocket SHALL serialize the same Pydantic event contract and SHALL not maintain independent business event enumerations.

#### Scenario: Event type is generated for frontend
- **WHEN** the OpenAPI contract is generated
- **THEN** every supported user event type is represented in the frontend TypeScript type

