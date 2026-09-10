# Consolidation Decision

Decision: delete `youle-agno-cursor` after preserving non-runtime reference
assets.

Why:

- `haole` is the canonical repository for the multi-agent work platform.
- `haole/docs/migration/MIGRATION_MATRIX.md` already audited the predecessor
  Agno line and records that EventBus, SSE, OTP, persistent event replay,
  Skill lifecycle, HITL, frontend coverage, and related tests were either
  migrated into `haole` or deliberately rejected.
- Importing the predecessor runtime would create a second orchestrator, second
  backend root, duplicate SkillRunner, duplicate task system, and direct LLM SDK
  paths. That conflicts with the canonical architecture.

Assets preserved here:

- Product/API documentation that remains useful for traceability.
- Safe Markdown extracts of macro workbook values.
- The Xiaohongshu evaluation JSONL sample.

Assets intentionally not preserved:

- `Agno官方参考/`: third-party framework reference docs.
- Agno runtime source under `src/`: covered by the migration matrix and
  intentionally not part of active `haole`.
- Macro workbook binaries: extracted to Markdown instead.
- Media/binary/generated artifacts.
