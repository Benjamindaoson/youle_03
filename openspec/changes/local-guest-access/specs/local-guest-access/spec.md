## ADDED Requirements

### Requirement: Explicit local guest session

The system SHALL expose a local guest session only when both the backend is running in dev/test and `LOCAL_GUEST_ACCESS=true`. It SHALL provision a stable local user and return a normal JWT usable by protected APIs. It MUST reject the request when local guest access is disabled.

#### Scenario: Local core session is issued

- **WHEN** a dev/test backend has `LOCAL_GUEST_ACCESS=true` and the frontend requests a guest session
- **THEN** the response contains a JWT and user identity that can call protected workspace APIs

#### Scenario: Guest access is disabled by default

- **WHEN** `LOCAL_GUEST_ACCESS` is false
- **THEN** the guest session endpoint returns a forbidden response and does not create a user

### Requirement: Direct local workspace entry

The frontend SHALL bootstrap the local guest session only when `NEXT_PUBLIC_LOCAL_GUEST_ACCESS=true`. It MUST otherwise preserve the existing authentication flow.

#### Scenario: Local core opens the workspace

- **WHEN** the local core launcher starts the frontend and a visitor opens the root URL
- **THEN** the visitor is authenticated as the local guest and is not sent to the OTP login page

#### Scenario: Production authentication remains active

- **WHEN** the public local guest flag is absent or false
- **THEN** an unauthenticated workspace visitor is sent to the login page
