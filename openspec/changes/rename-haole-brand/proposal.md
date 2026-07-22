## Why

The active product has inconsistent naming across its full stack and repository. The supported local launcher was also not running, leaving the browser URL without a listener.

## What Changes

- **BREAKING** Rename the active product, repository, packages, configuration, Docker state, and UI identity to `haole`.
- Replace retired product markers in tracked text and paths.
- Add a dependency-free guard against reintroducing retired markers.
- Verify the existing mock-mode core launcher serves the frontend and backend.

## Capabilities

### New Capabilities

- `haole-brand-identity`: An enforceable, single active product identity.
- `core-launch-verification`: A reproducible local full-stack smoke check.

### Modified Capabilities

- None.

## Impact

Python and Node metadata, Docker defaults, development data names, frontend copy, current docs, tests, and the canonical GitHub repository are affected. API paths and LangGraph behavior are unchanged.
