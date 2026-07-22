## Context

The application already has one LangGraph orchestrator, group chat, a canonical ecommerce detail-image Skill, and specialist Agents. Its local core worker intentionally returns mock artifacts; the canonical Skill currently batches five images before a user-specific per-call confirmation is enforced.

## Goals / Non-Goals

**Goals:**

- Keep ecommerce delivery inside one group chat and the existing orchestration path.
- Use DeepSeek for text, Seedream for images, and local image concatenation.
- Make every image-model call explicitly quantity-confirmed by the user.

**Non-Goals:**

- New ecommerce UI surface, a second orchestrator, video delivery, provider auto-fallback, or automatic image retries.

## Decisions

- Use the existing `ecommerce_detail_image` Skill as the only canonical ecommerce entry point.
- Represent confirmation as a durable HITL gate attached to each planned image invocation; only an approved gate dispatches an image task.
- Use group membership to express specialization: CEO assistant, Agent 1, Agent 3 and Agent 2 only.
- Report provider failures in the group and require a new user decision; never spend again implicitly.

## Risks / Trade-offs

- Per-invocation confirmation adds clicks. It is intentional because the user prioritizes cost control over unattended batch generation.
- Provider integration needs real credentials and pricing validation. Live calls stay opt-in and cannot be claimed complete from mock tests.
