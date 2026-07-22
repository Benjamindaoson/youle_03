## Context

The project is a Next.js, FastAPI, LangGraph, PostgreSQL, and Redis application. `scripts/core.ps1` is the supported local entrypoint and starts exactly two containers plus three application processes.

## Goals / Non-Goals

**Goals:** use `haole` as the only active identity; retain the existing runtime architecture; prevent retired markers from returning; prove the launcher serves the app.

**Non-Goals:** rename Git history or third-party attribution; preserve old local Docker volumes; change API paths or add dependencies.

## Decisions

- Apply a case-insensitive mechanical rename to tracked UTF-8 text, using Unicode escapes for Chinese literals so Windows command encoding cannot alter source syntax.
- Rename tracked paths after text replacement.
- Use one pytest guard based on `git ls-files`; it requires no new package and covers paths plus contents.
- Do not modify the launcher: the observed cause was no listener, and the existing launcher restored HTTP 200 and readiness.

## Risks / Trade-offs

- Fresh Compose defaults use fresh local development data → production is unaffected.
- Mechanical rename can touch an unexpected file → identity guard plus full lint/test/build checks are mandatory.
- Repository URL changes → GitHub redirects old URLs and local `origin` is updated.

## Migration Plan

1. Add and run a failing guard.
2. Apply the rename and regenerate lock metadata.
3. Run static, unit, build, API, and browser checks.
4. Rename the GitHub repository and update `origin`.
