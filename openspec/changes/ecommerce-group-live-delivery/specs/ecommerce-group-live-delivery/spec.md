## ADDED Requirements

### Requirement: Ecommerce professional group membership

The system SHALL run ecommerce detail-image delivery in a group containing the CEO assistant, Agent 1, Agent 3 and Agent 2. It MUST NOT include Agent 4, HR or the finance manager in that professional group.

#### Scenario: Create an ecommerce group

- **WHEN** a user starts ecommerce detail-image work in a group
- **THEN** the group exposes only the required ecommerce roles

### Requirement: Confirm every image invocation

The system SHALL create no image-model task until the user confirms its exact image quantity in the group. Regeneration and additional images MUST create a new confirmation.

#### Scenario: Confirm planned images

- **WHEN** the CEO assistant proposes a quantity of images
- **THEN** the system dispatches exactly that quantity only after the user approves

#### Scenario: Decline planned images

- **WHEN** the user has not approved or declines an image confirmation
- **THEN** no image-model request is dispatched

### Requirement: Chinese-model default delivery

The system SHALL use DeepSeek for ecommerce text and Seedream for ecommerce images by default. It MUST report provider failures to the group rather than automatically switching providers or retrying an image call.

#### Scenario: Provider fails

- **WHEN** the configured image provider fails
- **THEN** the group receives the failure and no unconfirmed replacement request is made
