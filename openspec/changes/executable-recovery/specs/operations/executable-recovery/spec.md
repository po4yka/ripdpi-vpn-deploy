## Purpose

Recover an unavailable disposable node from canonical Git and encrypted secrets
while retaining exact authority and continuing safely after controller failure.

## ADDED Requirements

### Requirement: REQ-RECOVERY-PLAN — Explicit supported recovery scope

The implementation MUST admit only a private versioned UpCloud Path A manifest
binding source revision, provider account, replacement environment, hostname,
cohort, encrypted source and management/publication inputs. It MUST refuse
unsupported providers and root-restic paths before mutation.

#### Scenario: Reviewed positive recovery plan

- **WHEN** an owner supplies a valid manifest for a distinct replacement node
- **THEN** the controller creates a bounded review challenge for the exact saved
  Terraform plan without printing credentials, state or plan values.

#### Scenario: Unsupported or changed input

- **WHEN** a manifest is unsafe, the source changes or another provider is selected
- **THEN** no provider or guest mutation starts.

### Requirement: REQ-RECOVERY-PROVISION — Exact provisioning and reconciliation

The implementation MUST verify the authenticated account and exact saved plan
before apply. It MUST persist intent before apply and reconcile provider resources
and Terraform state after interruption. An orphan import MUST require an exact
resource review and cannot adopt a hostname match as sufficient authority.

#### Scenario: Apply acknowledgement lost

- **WHEN** provider creation succeeded but the controller did not record success
- **THEN** resume observes the actual resource and state, avoids duplicate creation,
  and either continues from verified state or requests exact import review.

### Requirement: REQ-RECOVERY-MANAGEMENT — Authenticated fresh-node admission

The implementation MUST execute canonical recovery installation, Tailnet bootstrap,
SSH ownership and deployment input admission. New host identity MUST be explicitly
authenticated before the first SSH contact; an interrupted bootstrap MUST reconcile
its existing transaction and never fabricate a handoff or socket context.

#### Scenario: New host key requires operator action

- **WHEN** a replacement resource exists without accepted host-key authentication
- **THEN** execution retains its resource intent and returns a concrete pin challenge
  that can be approved after independent host-key authentication.

### Requirement: REQ-RECOVERY-RESUME — Durable observed continuation

The implementation MUST lock one recovery, durably record each child-operation
intent before execution and recheck current postconditions on resume. It MUST
retain uncertain outcomes and sensitive diagnostics privately, refuse concurrent
runs, bound subprocess lifetime and output, and clean only owned plaintext.

#### Scenario: Process dies during a child operation

- **WHEN** a new controller invocation opens the same manifest and journal
- **THEN** it reconciles current external state, does not trust a completed phase
  flag alone, and continues the remaining positive workflow.

### Requirement: REQ-RECOVERY-CONVERGE — Real full-profile convergence

The implementation MUST run canonical full dry-run and reviewed deployment with
fresh failure sinks, then current verify, source-drift and authenticated smoke
checks. Interrupted deployment MUST use existing transaction recovery; failure
cannot become success through a stale journal or skipped check.

#### Scenario: Successful deployment lost its acknowledgement

- **WHEN** fresh source parity and node verification prove the requested generation
- **THEN** resume continues to current acceptance without reissuing credentials.

### Requirement: REQ-RECOVERY-DELIVERY — Existing-device continuity

The implementation MUST continue through the canonical device-migration contract
for a surviving dedicated publisher and require its final ready decision before
reporting service restored. It MUST preserve device identities, revocation and
stable subscription URLs. Destroyed co-located publication authority is outside
this supported topology and MUST remain explicitly unresolved.

#### Scenario: Publisher survives the unavailable source node

- **WHEN** target convergence succeeds and the migration's required device evidence
  and stable-origin checks pass
- **THEN** recovery reports restored with current exact target/source acceptance.

#### Scenario: Device acceptance incomplete

- **WHEN** the migration has outstanding required receipts or origin routing
- **THEN** the server remains available but recovery reports acceptance pending.
