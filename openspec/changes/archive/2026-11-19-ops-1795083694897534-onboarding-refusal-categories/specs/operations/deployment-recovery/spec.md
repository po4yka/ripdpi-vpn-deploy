## ADDED Requirements

### Requirement: REQ-DR-ONBOARDING-RECEIPT — Report the fixed promotion refusal in the receipt

In deploy mode, when recovery or cloud promotion finalization refuses with a category in the baseline controller's fixed reason set, the controller MUST publish that category as the failure receipt `reason`. It MUST publish `onboarding-refused` for any other onboarding failure.

#### Scenario: Known promotion refusal

- **WHEN** finalization refuses with `recovery-promotion-target-mismatch`
- **THEN** the baseline failure receipt reason is `recovery-promotion-target-mismatch`

#### Scenario: Unlisted promotion category

- **WHEN** finalization refuses with a category outside the fixed reason set
- **THEN** the baseline failure receipt reason is `onboarding-refused`

### Requirement: REQ-DR-ONBOARDING-PAYLOAD — Carry the emitter payload input category

The client emitter MUST report a failed input command (Terraform output or SOPS decrypt) or an exhausted payload deadline as `payload-input-unavailable` or `payload-deadline-exceeded`. The sentinel installer MUST map exactly those emitter lines to the same categories, and finalization MUST report them as `recovery-promotion-payload-input-unavailable` and `recovery-promotion-payload-deadline-exceeded`.

#### Scenario: Missing Terraform workspace data

- **WHEN** a deploy-mode cloud promotion runs in a checkout where `terraform-env.sh output` fails
- **THEN** the emitter prints only `client-payload: payload-input-unavailable`
- **AND** the baseline failure receipt reason is `recovery-promotion-payload-input-unavailable`

### Requirement: REQ-DR-ONBOARDING-PRIVATE — Keep unknown failure detail generic

Each layer MUST map an unknown failure to its existing generic category, and no receipt, error or stderr line MUST contain a path, address, alias, secret value or child output other than the fixed emitter refusal line.

#### Scenario: Private child stderr

- **WHEN** a child command fails with any other stderr, such as a message that names a path
- **THEN** the installer reports `command-failed` and finalization reports `recovery-promotion-finalization-refused`
- **AND** the child stderr text appears in no error or receipt
