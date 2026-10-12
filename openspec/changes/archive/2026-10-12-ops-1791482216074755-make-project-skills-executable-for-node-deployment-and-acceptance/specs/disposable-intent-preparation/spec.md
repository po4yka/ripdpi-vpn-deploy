## Purpose

Prepare the existing disposable onboarding intent and exact-alias deployment mapping locally from explicit private inputs without creating credentials or contacting infrastructure.

## ADDED Requirements

### Requirement: REQ-INTENT-LOCAL — Assemble a validated intent

The Makefile MUST expose prepare-disposable-promotion-intent as a local operation consuming a predeployment JSON liveness configuration, client name, existing input-file paths and an existing empty private output directory. It MUST reuse disposable_promotion.validate_intent and produce the intent plus its exact inventory-alias mapping.

#### Scenario: Valid disposable target

- **WHEN** explicit inputs describe the supported single UpCloud ci-staging node and all four profiles
- **THEN** the resulting private intent is accepted by the existing validator, its mapping names only that target and no applied_at or acceptance receipt is invented.

### Requirement: REQ-INTENT-PRIVATE — Publish without clobbering

Preparation MUST reject symlinked, foreign-owned or insecure configuration/output ancestry, refuse nonempty output directories, publish mode-0600 files exclusively under the descriptor-bound mode-0700 directory and keep input credentials unopened. It MUST preserve existing directory permissions. Failures MUST expose categorical diagnostics only.

#### Scenario: Existing destination contents

- **WHEN** the selected output directory already contains files
- **THEN** preparation refuses without altering it or any input.

#### Scenario: Destination substitution during publication

- **WHEN** the output pathname is replaced after its directory descriptor was opened
- **THEN** preparation refuses success, preserves the replacement and retains any partial output only in the original directory.

#### Scenario: Invalid or overly broad configuration

- **WHEN** input names production, an unsupported provider, an applied epoch or aliased paths
- **THEN** preparation refuses before publication and prints no private configuration.

### Requirement: REQ-INTENT-MAKE-BOUNDARY — Preserve literal input handling

The Make entry MUST accept exactly one goal, consume its path/name inputs from the environment without Make expansion, and reject command-line variables before reading operator configuration.

#### Scenario: Make expression input

- **WHEN** an input or command-line variable contains a Make expression
- **THEN** no expression is executed and the preparation either treats the value literally or refuses it.
