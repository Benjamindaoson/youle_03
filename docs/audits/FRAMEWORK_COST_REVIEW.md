# Agent workflow framework cost review

Date: 2026-07-22

## Decision

Keep LangGraph as the workflow kernel, as confirmed by the project owner. Framework weight is controlled at the runtime boundary: the default core profile uses FastAPI, LangGraph, one combined Agent worker, PostgreSQL, Redis, SSE, and the Next.js frontend. Qdrant, MinIO, LiteLLM proxy, LangSmith, MCP sidecars, Kubernetes, and independent Agent workers are optional production facilities under `deploy/production/`.

PocketFlow remains a useful reference for keeping nodes small and explicit, but replacing the verified LangGraph checkpoint/HITL/resume path would add migration risk without reducing token charges. Neither framework itself generates model-token cost.

## Evidence

- LangGraph and PocketFlow are both MIT-licensed, so their open-source framework license cost is zero: [LangGraph license](https://github.com/langchain-ai/langgraph/blob/main/LICENSE), [PocketFlow license](https://github.com/The-Pocket/PocketFlow/blob/main/LICENSE).
- LangGraph can run with in-memory persistence and offers file-backed SQLite for local development; PostgreSQL is not mandatory for every deployment: [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).
- PocketFlow describes itself as a 100-line, dependency-free graph abstraction. It does not supply persistence, recovery, queues, observability, or model services: [PocketFlow repository](https://github.com/The-Pocket/PocketFlow).
- Neither framework inherently creates token charges. Token spend is determined by model choice and by the application's node, retry, planner, critic, and reflection calls.

## Cost-first boundaries

The shipped core starts only PostgreSQL and Redis as containers, uses deterministic Skill routing, defaults to mock LLM execution, and uses one worker process for all four Agent queues. A verified mock short-video journey made zero external model calls. Enable real models, critic/reflection loops, vector search, dedicated object storage, MCP sidecars, or independently scaled workers only after measuring a concrete need.
