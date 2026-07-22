## Context

The local core command runs the real FastAPI API, PostgreSQL, Redis, worker, and frontend, but currently requires an OTP login before any protected API can be used. Frontend mock mode would avoid the login but also bypass the real backend and Agent path.

## Goals / Non-Goals

**Goals:**

- Let `scripts/core.ps1 start` enter a real authenticated workspace without SMS.
- Keep guest access impossible unless explicitly enabled in a dev/test backend and frontend runtime.
- Reuse the ordinary JWT and user model so protected API and event paths remain unchanged.

**Non-Goals:**

- Removing or weakening production OTP authentication.
- Adding anonymous multi-user access or changing the production deployment profile.

## Decisions

- Add `LOCAL_GUEST_ACCESS`, defaulting to false, and reject it outside dev/test. The endpoint returns a normal JWT for one stable local user. This keeps all existing authorization dependencies intact.
- Have the frontend call the endpoint only when `NEXT_PUBLIC_LOCAL_GUEST_ACCESS=true`; it persists the returned JWT and otherwise retains the current login redirect. This avoids silently turning API failures into mock data.
- Set both flags only in `scripts/core.ps1`. This is safer than making local guest mode the repository default.

## Risks / Trade-offs

- [A flag is accidentally enabled in deployment] → settings validation rejects it outside dev/test, and the launcher is the only default opt-in path.
- [Guest endpoint is unavailable] → frontend falls back to the existing login flow instead of presenting a broken workspace.
- [One local identity shares local data] → acceptable for a single-machine demo; production retains individual OTP identities.
