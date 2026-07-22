# Production profile

The repository defaults to the low-cost core profile. Production infrastructure is optional and
kept outside the runtime core:

- `docker-compose.yml`: PostgreSQL, Redis, MinIO and Qdrant.
- `docker-compose.celery.yml`: independently scalable Agent, Celery and MCP workers.
- `k8s/`: Kubernetes manifests for the backend, frontend, Agents, MCP, data stores and migration job.
- `litellm/`: LiteLLM gateway policy and model routing.
- `Dockerfile.*`: production image boundaries; application code remains in `backend/`, `agents/` and `frontend/`.

The backend and Agent contracts are the same in both profiles. Production services can be enabled
through environment variables without changing the frontend API. Do not start this profile for the
local no-key demo; it uses more containers and processes by design.

Validate the optional Compose profile without starting it:

```bash
docker compose -f deploy/production/docker-compose.yml \
  -f deploy/production/docker-compose.mock.yml \
  -f deploy/production/docker-compose.celery.yml config --quiet
```

Live mode is never enabled by the core script. Configure provider credentials server-side, set
`LITELLM_MOCK=false` explicitly, and keep `STEP_PERSONA_MAX_BUDGET_TOKENS` at a cost-appropriate
hard ceiling before starting production workers.

## E-commerce live delivery

Copy `.env.ecommerce.example` to a private server-side environment file and provide only
`DEEPSEEK_API_KEY` and `ARK_API_KEY`. The e-commerce group uses DeepSeek for copy, Volcengine Ark
Seedream for images, and local Pillow for long-image composition. Seedream calls are one-shot:
there is no automatic retry and no fallback to overseas models.

Every image invocation pauses with the exact requested count and price estimate. A person must
approve that count in the existing group chat before the request is sent. `scripts/core.ps1 start`
is still the no-key mock demo; it cannot spend provider credits. Production smoke tests also skip
e-commerce images by default, and never auto-approve an image confirmation.
