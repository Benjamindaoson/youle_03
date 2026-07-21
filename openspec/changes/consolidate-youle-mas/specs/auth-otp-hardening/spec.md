## ADDED Requirements

### Requirement: Preserve canonical authentication
The backend SHALL retain the existing User model, SMS OTP login routes, JWT access tokens, refresh route, and production/development delivery separation.

#### Scenario: Existing SMS client logs in
- **WHEN** a client calls the existing SMS send and login routes with a valid code
- **THEN** it receives a JWT for the canonical User without a second identity record

### Requirement: OTP is expiring and single-use
An OTP SHALL expire after its configured TTL and SHALL be consumed atomically no more than once.

#### Scenario: Concurrent verification
- **WHEN** two login requests verify the same valid OTP concurrently
- **THEN** exactly one succeeds and the other receives an authentication error

#### Scenario: Expired code
- **WHEN** a user submits an expired OTP
- **THEN** login is rejected without creating or updating a User

### Requirement: Safe OTP delivery failure
The backend SHALL remove a newly stored OTP when the delivery provider fails and SHALL rate limit sending and verification.

#### Scenario: SMS provider fails
- **WHEN** production SMS delivery raises a provider error
- **THEN** the stored code is deleted and the API returns a non-success response without logging the full code

