## Purpose

Define the observable evidence and safety contract for completing the remaining
Critical and High deployment work across protected source, dry-run, isolated
staging, live fleet, current clients, alert delivery, recovery, and cleanup.

## ADDED Requirements

### Requirement: REQ-EPC-1788891270457728-001 — Bind external execution to protected source

The operator workflow MUST accept an external acceptance run only when it names
a clean commit already present on protected main, the corresponding deployable
source digest, and successful required hosted checks for that exact commit.

#### Scenario: Unpublished or dirty source is refused

- **GIVEN** the checkout is dirty or its commit is absent from protected main
- **WHEN** an operator attempts a dry-run, staging, live, or client acceptance
- **THEN** the workflow refuses before any provider, host, network, or client mutation
- **AND** it records source identity as the blocking boundary

#### Scenario: Exact protected source is retained in evidence

- **GIVEN** required hosted checks passed for a clean protected-main commit
- **WHEN** an external acceptance phase completes
- **THEN** its private evidence records that commit and deployable digest
- **AND** evidence from a different source cannot satisfy the phase

### Requirement: REQ-EPC-1788891270457728-002 — Preserve evidence-category boundaries

The acceptance record MUST track local, remote CI, dry-run, staging, live,
client, and artifact evidence independently and MUST NOT infer one category from
success in another category.

#### Scenario: Source checks do not close live work

- **GIVEN** local and hosted checks pass but no live command was observed
- **WHEN** completion is evaluated
- **THEN** live and client categories remain required or blocked
- **AND** the portfolio task cannot enter a terminal done state

### Requirement: REQ-EPC-1788891270457728-003 — Guard isolated staging from creation through cleanup

The staging workflow MUST bind one provider account, environment, state,
resource identity, owner-approved cost ceiling, expiry, and cleanup evidence
path before apply, and MUST prove provider-confirmed resource absence after the
run.

#### Scenario: Missing staging capability fails before apply

- **GIVEN** a credential, account match, clean state, cost approval, expiry,
  cleanup reservation, or unique staging identity is missing or ambiguous
- **WHEN** staging is requested
- **THEN** the workflow refuses before resource creation
- **AND** the exact missing capability is recorded without exposing secrets

#### Scenario: Staging cleanup is verified

- **GIVEN** a manifest-bound staging resource was created and exercised
- **WHEN** the staging window ends or an intermediate phase fails
- **THEN** cleanup targets only the manifest-bound resource and dependent storage
- **AND** provider reads after destruction prove absence before cleanup passes

### Requirement: REQ-EPC-1788891270457728-004 — Prove serial fleet dry-run and convergence

The deployment workflow MUST execute the canonical precheck, dry-run, serial
deployment or reconvergence, verification, security verification, and
source-drift gates against every configured Critical or High fleet target.

#### Scenario: One target fails closed

- **GIVEN** a target is unreachable, its SSH context is missing, a precheck
  fails, or deployed state differs from the exact source digest
- **WHEN** the serial fleet sequence reaches that target
- **THEN** the sequence stops before advancing to the next target
- **AND** it records the failing target and last completed gate

#### Scenario: Fleet acceptance succeeds

- **GIVEN** all required private inputs and targets are available
- **WHEN** the canonical sequence runs from the exact protected source
- **THEN** every target reports zero failed and unreachable tasks
- **AND** verification, security verification, and source drift all pass

### Requirement: REQ-EPC-1788891270457728-005 — Preserve SSH recovery and VPN reachability

Restricted management changes MUST be rehearsed on isolated staging with a
custom SSH listener, pinned algorithms, verified recovery access, and unchanged
required VPN paths before any serial live rollout.

#### Scenario: Recovery proof fails

- **GIVEN** the replacement management path works but the emergency path,
  effective listener, firewall contract, or required VPN path cannot be proven
- **WHEN** promotion is evaluated
- **THEN** live promotion is refused
- **AND** staging is rolled back or destroyed through its guarded lifecycle

### Requirement: REQ-EPC-1788891270457728-006 — Require current-client four-transport traffic

Client acceptance MUST use a current signed RIPDPI artifact and invocation-bound
handoff to prove authenticated REALITY, XHTTP, Hysteria2, and AmneziaWG traffic
from the required independent vantage points.

#### Scenario: Partial transport evidence remains incomplete

- **GIVEN** one or more profiles pass but any required profile, vantage,
  correlation, source identity, or traffic observation is missing
- **WHEN** client acceptance is evaluated
- **THEN** the client category remains incomplete
- **AND** the passing profiles are retained only as partial evidence

### Requirement: REQ-EPC-1788891270457728-007 — Require fresh recurring AmneziaWG evidence

Recurring AmneziaWG acceptance MUST bind a fresh nonce, current protocol
revision, source and artifact identities, real traffic, recovery outcome, and
cleanup outcome to each invocation.

#### Scenario: Infrastructure is unavailable after a valid pass

- **GIVEN** a prior valid PASS exists and a later invocation cannot acquire its
  provider, executor, signer, relay, or current client input
- **WHEN** recurring status is published
- **THEN** the prior PASS remains historical rather than becoming a new PASS
- **AND** the new invocation reports infrastructure unavailable with its blocker

#### Scenario: Replay is refused

- **GIVEN** evidence contains an old nonce, substituted source, stale artifact,
  unknown protocol revision, or reused traffic correlation
- **WHEN** the recurring verifier evaluates it
- **THEN** the invocation fails closed and cannot update the current PASS

### Requirement: REQ-EPC-1788891270457728-008 — Prove primary and independent alert recovery

Observability acceptance MUST deploy the expected target set and prove fresh
exact-source metrics, controlled failure detection, primary alert delivery,
independent dead-man delivery, recovery notification, rotation, rollback, and
removal of the superseded direct delivery path.

#### Scenario: One alert authority is unavailable

- **GIVEN** metrics are fresh but either primary or independent delivery cannot
  be observed end to end
- **WHEN** the alert drill is evaluated
- **THEN** observability remains incomplete
- **AND** direct legacy delivery is not removed

### Requirement: REQ-EPC-1788891270457728-009 — Prove isolated offsite restore

Backup acceptance MUST observe an initial offsite copy and a restore into an
isolated destination without pruning or mutating retained backup data.

#### Scenario: Offsite account or restore target is unavailable

- **GIVEN** the storage account, credential, copy, or isolated restore target is
  unavailable
- **WHEN** backup acceptance is evaluated
- **THEN** the task remains open with the exact unavailable capability
- **AND** local backup configuration is not credited as offsite restore proof

### Requirement: REQ-EPC-1788891270457728-010 — Isolate credentials and private evidence

Provider, fleet, client, alert, and offsite credentials MUST enter only through
their documented environment or encrypted-input interfaces, while private
evidence MUST be owner-only, redacted, identity-bound, and excluded from Git.

#### Scenario: Unsafe credential or evidence input is rejected

- **GIVEN** a credential arrives through a command-line make value or plaintext
  repository file, or an evidence path has unsafe ownership, mode, link, or
  parent-directory identity
- **WHEN** an external acceptance controller opens the input
- **THEN** it refuses before external action
- **AND** diagnostics reveal no secret value or private target address

### Requirement: REQ-EPC-1788891270457728-011 — Keep externally blocked work active

The portfolio record MUST remain active whenever a required external account,
credential, target, signer, relay, current client artifact, or human executor is
unavailable, and MUST name the exact blocker and last completed safe boundary.

#### Scenario: External blocker persists

- **GIVEN** every safe source and preflight action is complete but a required
  external capability remains unavailable
- **WHEN** task status is updated
- **THEN** the task transitions to blocked rather than done or dropped
- **AND** no unperformed acceptance is marked passed or not applicable

### Requirement: REQ-EPC-1788891270457728-012 — Reconcile predecessor obligations before closure

Final closure MUST map every unfinished Critical and High predecessor
requirement to current exact evidence or an explicit superseding requirement,
and MUST pass task, OpenSpec, source, hosted, staging, live, client, artifact,
rollback, and cleanup validation applicable to that requirement.

#### Scenario: A predecessor obligation lacks proof

- **GIVEN** any unfinished requirement from a named predecessor has neither
  scope-matching current evidence nor a documented superseding requirement
- **WHEN** terminal closure is requested
- **THEN** archive readiness and closure fail
- **AND** the missing obligation remains visible in the active task
