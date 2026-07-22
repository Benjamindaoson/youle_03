## Why

The local core demo currently starts the complete stack but routes an unauthenticated user to SMS OTP, which prevents the intended no-cost local evaluation flow from reaching the real backend and Agent system.

## What Changes

- Add an explicitly opt-in local guest session endpoint that provisions a stable local user and returns an ordinary JWT.
- Make the frontend bootstrap that session and enter the workspace when the corresponding public local flag is enabled.
- Enable the two flags only from the local core launcher; production authentication remains unchanged.

## Capabilities

### New Capabilities

- `local-guest-access`: Local core demo can enter the real workspace without SMS authentication while preserving production authentication.

### Modified Capabilities

- None.

## Impact

Backend authentication settings and route, frontend authentication bootstrap/client, the local launcher, tests, generated OpenAPI types, and local-start documentation.
