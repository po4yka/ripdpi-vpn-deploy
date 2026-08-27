# ci/credentialed-deploy-gating Specification

## Purpose
Define the approval and secret-handling contract for every repository-owned
workflow job that runs with cloud-provider credentials or CI key material, so
that a label, dispatch, or schedule event alone can never reach that material.
## Requirements
### Requirement: REQ-DEPLOY-GATE — Credentialed jobs require an approved deployment

Every workflow job whose environment carries cloud-provider credentials or CI
key material MUST reference a protected GitHub Environment, and the referenced
environment MUST exist with a required-reviewer protection rule in repository
settings.

#### Scenario: Label-triggered credentialed run

- **WHEN** a contributor adds the `ci-real-deploy` label to a pull request
- **THEN** the deployment jobs remain waiting until a required reviewer
  approves the deployment on the `ci-real-deploy` environment, and no step of
  the job executes before that approval

#### Scenario: Scheduled or dispatched credentialed run

- **WHEN** either credentialed workflow starts from its `schedule` or
  `workflow_dispatch` trigger
- **THEN** the same environment approval is required before any step runs

#### Scenario: Environment protection is absent

- **WHEN** the referenced environment does not exist or loses its
  required-reviewer rule in repository settings
- **THEN** `make check-ci-deploy-gate` fails and the gap must be remediated through the
  GitHub API before credentialed runs are trusted again

#### Scenario: Hosted protection cannot be inspected

- **WHEN** the GitHub API request fails, times out, or returns invalid data
- **THEN** the live gate verifier fails without claiming approval protection;
  offline workflow tests do not substitute for this hosted check

### Requirement: REQ-DEPLOY-GATE-SECRETS — No direct secret expansion into run blocks

Credentialed workflows MUST pass secret values to shell steps only through
step-level `env:` mapping consumed as quoted shell variables; direct
`${{ secrets.* }}` expansion inside `run:` text MUST NOT appear.

#### Scenario: Staging deploy key material

- **WHEN** a step writes the deploy SSH key or age identity to disk
- **THEN** the secret reaches the script through the step environment and the
  `run:` block contains no `${{ secrets.` interpolation

#### Scenario: New secret consumer is added

- **WHEN** a contributor adds a new step that consumes a secret in either
  credentialed workflow
- **THEN** the contract test fails unless the value flows through `env:`
  indirection

### Requirement: REQ-DEPLOY-GATE-DEFENSE — Fork short-circuit retained

The fork-refusal first steps in both credentialed workflows MUST be preserved
as defense in depth behind the environment gate.

#### Scenario: Fork pull request is labeled

- **WHEN** a fork PR receives the `ci-real-deploy` label and a reviewer
  approves its deployment
- **THEN** the fork short-circuit still fails the job before credentials are
  exposed to any subsequent step
