## Purpose

Define a reproducible, fail-closed security baseline for every repository-owned
GitHub Actions, Dependabot, and pre-commit definition without expanding access
to credentials or scanning unrelated third-party fixtures.

## ADDED Requirements

### Requirement: REQ-ZIZMOR-PIN — Use a repository-pinned analyzer

The repository MUST pin an exact stable `zizmor` version in its canonical local
toolchain and MUST use that version for both local and CI audits.

#### Scenario: Local and CI version parity

- **WHEN** a contributor runs the documented local target and CI runs the
  GitHub Actions security job for the same revision
- **THEN** both executions resolve the same exact `zizmor` version from
  repository-controlled configuration

#### Scenario: Analyzer version changes

- **WHEN** the pinned `zizmor` version is upgraded
- **THEN** the version change and all newly surfaced findings are reviewed and
  committed together or in an explicitly ordered commit sequence

### Requirement: REQ-ZIZMOR-SCOPE — Audit repository-owned definitions only

The security gate MUST collect supported inputs owned by the repository under
`.github/` and MUST NOT treat vendored or third-party test fixtures as
production CI definitions.

#### Scenario: Repository-owned input changes

- **WHEN** a workflow, action definition, Dependabot configuration, or
  pre-commit definition under the owned input scope is added or modified
- **THEN** the strict audit parses and evaluates that input

#### Scenario: Vendored workflow fixture exists

- **WHEN** a third-party fixture contains a nested `.github/workflows`
  directory outside the owned input scope
- **THEN** the production security gate does not collect or gate on that fixture

### Requirement: REQ-ZIZMOR-FAIL-CLOSED — Fail on findings and collection errors

The local and CI security gates MUST fail when the default audit persona emits
an unsuppressed finding or when a supported owned input cannot be collected and
parsed.

#### Scenario: Actionable finding is introduced

- **WHEN** an owned input produces any unsuppressed default-persona finding
- **THEN** the gate exits non-zero and identifies the audit rule and source span

#### Scenario: Owned input is malformed

- **WHEN** a supported owned input has a syntax or schema error
- **THEN** strict collection fails instead of silently skipping the input

### Requirement: REQ-ZIZMOR-ZERO-BASELINE — Remove existing actionable findings

Every default-persona finding in the owned input scope MUST be fixed at its
cause or documented with the narrowest available suppression when the value is
provably not attacker controlled.

#### Scenario: Safe structural remediation exists

- **WHEN** a finding can be removed by reducing credential persistence,
  permissions, or direct template expansion without changing intended behavior
- **THEN** the structural remediation is used instead of a suppression

#### Scenario: Finding is contextually safe

- **WHEN** a finding cannot be removed without losing required behavior and its
  input is demonstrably constrained by repository-owned configuration
- **THEN** a rule-specific, source-local suppression documents the safety
  argument and no audit is disabled globally

### Requirement: REQ-ZIZMOR-LEAST-PRIVILEGE — Avoid unnecessary online authority

The CI gate MUST run with the minimum permissions and network authority needed
for deterministic analysis of the checked-out repository.

#### Scenario: Pull request audit runs

- **WHEN** the security job executes for a pull request
- **THEN** it does not persist checkout credentials, expose a GitHub token to
  the analyzer, or request write permissions solely to report findings

#### Scenario: External audit enrichment is unavailable

- **WHEN** GitHub API access is unavailable or intentionally disabled
- **THEN** the deterministic offline rules and strict collection still run and
  enforce the repository baseline

### Requirement: REQ-ZIZMOR-CANONICAL-GATE — Expose one operator-facing command

The Makefile MUST expose one documented target that invokes the pinned analyzer
with the same owned scope and strictness used by CI, and the repository's
appropriate aggregate validation surface MUST depend on it.

#### Scenario: Contributor validates locally

- **WHEN** a contributor invokes the documented security target from the
  repository root
- **THEN** it audits the complete owned scope with no uncommitted file changes

#### Scenario: Tool is missing

- **WHEN** the pinned analyzer is not available through the configured
  toolchain
- **THEN** the command fails with an actionable prerequisite error rather than
  skipping the audit

### Requirement: REQ-ZIZMOR-ROLLBACK — Preserve a reversible enforcement path

The integration MUST be reversible by reverting its focused commits without
changing runtime infrastructure, secrets, or deployment state.

#### Scenario: Gate rollback is required

- **WHEN** an upstream analyzer regression blocks all repository validation
- **THEN** operators can revert the pinned integration commit while retaining
  the independently safe workflow remediations

### Requirement: REQ-SOLO-MAINTAINER-MERGE — Do not require self-approval

The default branch protection MUST allow the sole maintainer to merge a pull
request without an approving review while retaining required status checks,
strict up-to-date branches, admin enforcement, linear history, conversation
resolution, and force-push and deletion protection.

#### Scenario: Sole maintainer merges a validated pull request

- **WHEN** all required checks pass and all conversations are resolved
- **THEN** GitHub permits the maintainer to merge without an approving or Code
  Owner review

#### Scenario: Protection policy is reapplied

- **WHEN** the repository branch-protection workflow is run again
- **THEN** it preserves the no-required-review policy instead of restoring an
  impossible self-approval requirement

### Requirement: REQ-MOLECULE-IMAGE-CLEAN — Keep immutable test images scan-clean

Every Molecule platform image MUST remain digest-pinned, and the distinct
resolved images MUST pass the hosted HIGH/CRITICAL Trivy scan without adding a
vulnerability exception for findings fixed by an available upstream image.

#### Scenario: Upstream image refresh is available

- **WHEN** a pinned image accumulates fixed HIGH or CRITICAL findings
- **THEN** every reference is updated coherently to a verified immutable digest
  and the hosted image-scan matrix passes
