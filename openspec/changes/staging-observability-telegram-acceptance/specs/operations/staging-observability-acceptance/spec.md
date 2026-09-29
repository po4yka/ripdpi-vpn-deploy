## Purpose

Define the exact-host bootstrap and bounded live proof required for the
disposable control-plane, dead-man, canary, and Telegram subset before the
separate full staging matrix, fleet rollout, or authoritative paging cutover.

## ADDED Requirements

### Requirement: REQ-STG-OBS-TOPOLOGY — Staging uses independent disposable failure domains

The staging acceptance topology MUST contain one observability control plane,
one independent dead-man, and one canary telemetry agent. The dead-man MUST use
a provider distinct from the control plane; all three nodes MUST use distinct
failure domains and MUST NOT run on a production VPN node. Administrative
interfaces MUST remain private; any public ingress MUST be limited to the
declared authenticated write-only or heartbeat contract. Before provider plan
or apply, every selected `staging` state MUST be empty or already bound to this
task's immutable manifest; unrelated pre-existing state MUST fail closed.

#### Scenario: Independent staging placement is valid

- **WHEN** the operator renders and validates the selected staging inventory
- **THEN** it identifies exactly one control plane, one dead-man, and one canary
  agent, proves distinct control/dead-man failure-domain labels, and exposes no
  public Prometheus, Alertmanager, exporter, dashboard, or lifecycle interface.

#### Scenario: Control plane and dead-man share a provider or failure domain

- **WHEN** the selected staging inventory places both components at the same
  provider or in the same declared failure domain
- **THEN** validation fails before deployment and no acceptance drill starts.

#### Scenario: A selected staging state already belongs to unrelated work

- **WHEN** preflight finds a non-empty selected provider state that is not bound
  to this task's immutable manifest
- **THEN** it refuses before plan, apply, inventory rendering, or any external
  mutation and reports only a redacted scope conflict.

### Requirement: REQ-STG-OBS-BOOTSTRAP — Fresh observability hosts receive the hardened exact-host baseline

Before component deployment, each fresh control-plane and dead-man host MUST be
converged through a repository-owned exact-host surface that applies the
baseline, unattended security updates, guest firewall, required loopback host
monitoring, and source manifest. The firewall MUST reconcile the host class's
exact provider listener contract and source-restricted SSH without enabling VPN
transport roles. Check mode, initial deployment, idempotence, disable/cleanup,
and failure rollback MUST be covered by focused tests.

#### Scenario: A fresh control-plane host is prepared

- **WHEN** the operator runs the reviewed bootstrap against the exact selected
  staging control-plane alias
- **THEN** the hardened baseline, updates, guest firewall, loopback monitoring,
  and source manifest converge before the control-plane role, while no VPN
  transport or undeclared public listener is installed.

#### Scenario: Listener or SSH ownership disagrees

- **WHEN** the provider listener contract, effective SSH port/source, inventory
  host class, or expected source identity differs from the bootstrap request
- **THEN** bootstrap refuses before firewall mutation or component deployment.

### Requirement: REQ-STG-OBS-AUTHORIZATION — Every external mutation has exact separate authority

Provider creation, component deployment, service fault injection, provider
host/network fault injection, Telegram token revocation, rollback, component
removal, and provider disk destruction MUST each require an approved private
execution record naming the exact technical target, action, restoration action,
deadline, cancellation condition, and authorized window. Approval of planning
artifacts or an earlier row MUST NOT authorize a later external mutation.

#### Scenario: A fault row has complete authority

- **WHEN** the operator starts an approved staging fault row
- **THEN** the controller binds the request to the exact target and recorded
  restore action, enforces its deadline and stop condition, and emits only a
  redacted categorical receipt.

#### Scenario: Exact authority is absent

- **WHEN** a provider, credential, fault, rollback, removal, or destructive-data
  action lacks its exact current approval record
- **THEN** the action refuses before external or host mutation.

### Requirement: REQ-STG-OBS-OPERATOR — Staging acceptance actions are bounded and reproducible

The repository MUST expose staging-only exact-host commands for fresh metric
queries, critical primary reminder lifecycle, component service faults,
control-plane host/network loss, dead-man service loss, baseline restoration,
primary-route authority-loss detection, and categorical old-material rejection.
Commands MUST reject production, groups, wildcards, ambiguous targets, missing
restore authority, unsafe input files, debug output, and overlong deadlines.
Every action MUST produce a bounded redacted receipt suitable for requirement
mapping without containing endpoints, identifiers, request bodies, or secrets.

#### Scenario: A bounded staging row completes

- **WHEN** the operator invokes one allowed action with its private exact-target
  authority and the expected independent observation occurs before the deadline
- **THEN** the action restores or confirms the declared healthy state and emits
  only the allowlisted categorical result, times, technical aliases, and source
  or generation digests.

#### Scenario: A caller requests a production or arbitrary fault

- **WHEN** a command targets production, a group, a wildcard, an unsupported
  unit/provider action, or a caller-chosen remote command
- **THEN** it refuses before SSH, provider API, Telegram API, or Ansible access.

### Requirement: REQ-STG-OBS-SOURCE — Deployment is bound to one protected-main revision

Every staging component MUST be rendered and deployed from the same exact
protected-main Git revision. Installed generation metadata and digest-bound
manifests MUST identify that revision without containing credentials or private
endpoints. A mixed, dirty, unprotected, or unverifiable source revision MUST
block acceptance.

#### Scenario: All components match the selected revision

- **WHEN** the operator queries deployed status after convergence
- **THEN** the control plane, dead-man, and canary agent report generations and
  manifests derived from the same selected protected-main revision.

#### Scenario: One component differs from the selected revision

- **WHEN** installed status or a retained manifest resolves to a different or
  unverifiable revision
- **THEN** acceptance remains incomplete and failure injection, rotation, and
  cutover conclusions are blocked.

### Requirement: REQ-STG-OBS-CLEANUP — Every staging provider has guarded identity-bound destruction

The repository MUST implement guarded cleanup for the selected UpCloud,
Hetzner, and Scaleway staging roots. A private immutable manifest MUST bind the
provider account or project, environment, Terraform state path and digest,
complete set of Terraform addresses, every separately addressable provider
resource identity, selected source revision, approval, and expiry. Before
destruction, the guard MUST validate that the reviewed plan deletes exactly the
complete bound set and contains no create, update, replace, or unrelated delete.
After destruction, separately authenticated provider-specific queries MUST
prove absence of every addressable resource before the guard emits a redacted
completion receipt or permits local capability retirement. Provider resources
whose lifecycle is implicit in another resource MUST be covered by that owning
resource's absence check; in particular, Hetzner primary storage is covered by
server absence, while separately addressable storage MUST be checked directly.

#### Scenario: Guarded cross-provider cleanup succeeds

- **WHEN** the rollback/retention window is closed, exact destructive-data
  approval is current, manifest/state identities still match, and the reviewed
  plan deletes exactly the complete bound managed resource set
- **THEN** cleanup destroys that complete set, independently proves
  provider-specific absence of every addressable resource, and publishes a
  redacted identity-bound completion.

#### Scenario: Cleanup scope or provider state drifts

- **WHEN** account/project, manifest, state path/digest, resource identity,
  expiry, approval, or delete-only plan differs from the frozen request
- **THEN** cleanup refuses before destruction and retains local recovery
  capability and provider state for diagnosis.

### Requirement: REQ-STG-OBS-METRICS — The canary proves fresh authenticated telemetry

The canary agent MUST publish only the declared bounded metric and label
allowlist through its unique authenticated write identity. The control plane
MUST expose query evidence that the canary's samples and producer freshness
advance after deployment. Unknown, cross-node, revoked, plaintext, query, and
administrative requests MUST be rejected without logging secret material.

#### Scenario: Fresh canary telemetry advances

- **WHEN** the deployed canary completes at least two expected collection and
  remote-write intervals
- **THEN** the private control plane returns advancing timestamps for the
  canary's required metric families and reports no stale or identity mismatch.

#### Scenario: Old sender material is replayed

- **WHEN** revoked canary sender material attempts its former write path after
  successful rotation
- **THEN** ingestion rejects it before storage while the replacement identity
  continues to publish fresh samples.

### Requirement: REQ-STG-OBS-PRIMARY — Primary Telegram delivery has human-observed lifecycle evidence

The staging primary route MUST deliver a clearly labelled, redacted firing,
bounded reminder, and resolved lifecycle to the intended private Telegram
chat/topic. Acceptance MUST record the operator's human observation separately
from Alertmanager, relay, or Telegram API success. A transport success without
human receipt MUST NOT satisfy this requirement.

#### Scenario: Primary alert lifecycle succeeds

- **WHEN** the approved staging drill injects a labelled primary incident and
  later resolves it
- **THEN** machine evidence records bounded delivery attempts and the operator
  separately confirms the firing, reminder, and resolved messages in the
  intended private destination.

#### Scenario: Telegram accepts but the operator cannot observe receipt

- **WHEN** the relay records a successful Telegram API response but no human
  observation is available for the intended chat/topic
- **THEN** primary Telegram acceptance remains incomplete and no fleet or
  production paging claim is made.

#### Scenario: The active primary Telegram authority fails

- **WHEN** a separately authorized staging revocation makes the active primary
  canary fail and fresh healthy primary status is no longer publishable
- **THEN** advancing control-plane pulses stop, the independent dead-man emits a
  human-observed secondary authority-loss incident, and recovery is withheld
  until a replacement primary canary succeeds and fresh pulses advance.

### Requirement: REQ-STG-OBS-DEADMAN — Independent dead-man detects and recovers control-plane loss

The dead-man MUST authenticate advancing pulses and reverse-health input using
material distinct from telemetry ingestion and the primary Telegram route. It
MUST deliver control-plane loss, bounded reminders, and stable recovery through
a distinct secondary Telegram authority. Replayed, future, expired, invalid,
or regressing pulses MUST NOT produce a healthy or recovery state.

#### Scenario: Control-plane pulses stop and recover

- **WHEN** an approved drill stops control-plane pulses long enough to exceed
  the declared missing-pulse threshold and then restores fresh advancing pulses
- **THEN** the secondary route delivers human-observed loss, reminder, and
  stable recovery messages and the dead-man state advances accordingly.

#### Scenario: A stale pulse attempts to clear the incident

- **WHEN** a replayed, expired, future, invalidly authenticated, or
  sequence-regressing pulse arrives during a firing dead-man incident
- **THEN** it is rejected and cannot emit or record recovery.

### Requirement: REQ-STG-OBS-FAILURE — The controlled failure matrix preserves truthful state

The staging acceptance MUST separately exercise declared control-plane service
loss, control-plane host or network loss, primary delivery failure, dead-man
service loss, and recovery paths within an approved window. Each path MUST have
a bounded timeout, expected independent alert source, refusal condition, exact
restoration action, and restoration check. Control-plane service or host loss
MUST be observed through the secondary dead-man route after the configured five
missed pulses. Dead-man service loss MUST be observed through the primary route
after reverse health becomes stale. No local process state or API success MAY
substitute for the required end-to-end observation.

#### Scenario: A controlled component failure is injected

- **WHEN** the operator executes one approved failure row
- **THEN** the expected independent path fires within its bound, recovery is
  emitted only after fresh evidence returns, and unrelated schedules and
  retained data remain intact.

#### Scenario: A failure row exceeds its safety bound

- **WHEN** the expected independent alert or restoration state is absent at the
  row's stop condition
- **THEN** the drill aborts, restores the last known safe state, records the row
  as failed, and does not proceed to a more destructive row.

#### Scenario: Control-plane service or host connectivity is lost

- **WHEN** the exact authorized service fault and the separate provider
  host/network fault are exercised serially
- **THEN** the independent dead-man route fires within ten minutes, restoration
  returns strict host access and fresh advancing pulses, and stable secondary
  recovery is observed before another row starts.

#### Scenario: The independent dead-man service is lost

- **WHEN** the exact authorized dead-man service fault stops reverse-health
  publication
- **THEN** the primary route fires within ten minutes, restoration returns
  fresh reverse health, and resolved delivery follows the configured recovery
  stability before another row starts.

### Requirement: REQ-STG-OBS-ROTATION — Staging authorities rotate without dual authority

Acceptance MUST rotate one canary sender identity, the primary Telegram bot
authority, and the secondary dead-man Telegram bot authority one at a time. For
each rotation, the candidate MUST be validated before activation, the new
authority MUST work before old material is revoked, and old material MUST be
rejected after revocation. Telegram token revocation MUST be a separately
authorized operator/BotFather action; a bounded checker MUST read the old token
only from a private file, send no body to evidence output, and record only the
categorical upstream rejection. A failed candidate MUST restore the exact prior
working generation without leaving duplicate active schedules or routes.

#### Scenario: One authority rotation succeeds

- **WHEN** the candidate credential passes its preflight and is activated
- **THEN** the replacement path works, old material is revoked and demonstrably
  rejected, and exactly one authoritative sender or notification route remains.

#### Scenario: Candidate activation fails

- **WHEN** the candidate cannot pass its bounded live validation
- **THEN** the exact prior generation is restored, old working authority remains
  valid, candidate material is inactive, and the rotation is not accepted.

#### Scenario: Revoked Telegram material remains valid

- **WHEN** the bounded post-revocation checker reports `still-valid` for an old
  primary or secondary Telegram token
- **THEN** the checker exits non-success, rotation and cleanup acceptance remain
  blocked, prior recovery material is retained, and no rejection evidence is
  credited until upstream revocation is repeated and observed.

### Requirement: REQ-STG-OBS-ROLLBACK — Last-known-good rollback is exact and non-destructive

The control-plane rollback MUST use a reviewed, digest-bound private rollback
manifest and retained generation. It MUST restore exact prior configuration,
authority state, and schedules without deleting telemetry storage, exposing
secrets, or creating duplicate jobs. Missing, mismatched, or unreviewed rollback
material MUST fail closed.

#### Scenario: Candidate generation is rolled back

- **WHEN** the operator invokes rollback with the reviewed manifest for the
  immediately prior accepted generation
- **THEN** status and private health prove the exact prior generation is active,
  one schedule set exists, retained telemetry remains, and staging alert paths
  return to their prior working state.

#### Scenario: Rollback manifest does not match retained state

- **WHEN** a manifest digest, generation identity, or authority snapshot is
  missing or differs from retained state
- **THEN** rollback refuses before mutation and reports a redacted blocker.

### Requirement: REQ-STG-OBS-EVIDENCE — Acceptance evidence is redacted, attributable, and cleaned up

The task MUST record exact source revision, host-role and failure-domain aliases,
installed generation digests, fresh metric observations, each drill result,
human Telegram observations, rotation and old-material rejection, rollback, and
provider cleanup. Evidence MUST exclude credentials, private keys, chat IDs,
tokens, public endpoints, private inventory, and plaintext secret-derived
values. Component removal MUST preserve the control-plane TSDB. Provider
destruction of the complete manifest-bound managed resource set MUST occur only
after all evidence is captured, the rollback/retention window is explicitly
closed, and a separate destructive-data approval is recorded. Without that
approval, the resources MUST be retained in their last safe state and cleanup
acceptance remains blocked. After approved destruction, absence of every
separately addressable provider resource MUST be verified independently before
local temporary secret material is retired; provider-owned implicit storage is
covered by its owning server absence check.

#### Scenario: Staging acceptance completes

- **WHEN** all required deployment, metrics, Telegram, dead-man, failure,
  rotation, and rollback checks have passed
- **THEN** verification records their redacted evidence, removes disposable
  resources, proves provider absence, and states that fleet rollout,
  two-vantage VPN proof, and production paging cutover remain unaccepted.

#### Scenario: Required access or observation is unavailable

- **WHEN** provider access, required credentials, an approved failure window,
  or human Telegram observation is unavailable
- **THEN** the affected requirement remains explicitly blocked rather than
  being inferred from source, fixture, CI, or API-only evidence.
