# operations/fleet-health-rotation Specification

## Purpose
Provide truthful fleet observations and preserve independently authenticated
survivor availability while continuing only an unchanged rotation plan.
## Requirements
### Requirement: REQ-FLEET-SSH — Inventory-bound passive status

Fleet status MUST select exact unique provider/environment pairs from the
existing admitted inventory and reuse strict inspection SSH transport, port,
key and host identity. It MUST validate all selected local inputs before SSH
and MUST NOT call Terraform, accept unknown host keys or trigger active probes.

#### Scenario: Tailnet transport with custom port

- **WHEN** a selected node has a Tailnet transport and a distinct public identity
- **THEN** collection uses the inventory transport and port with the existing
  public identity pin, ignores ambient SSH configuration and remains bounded.

#### Scenario: Invalid or ambiguous selection

- **WHEN** the selection, connection authority or known-hosts file is invalid
- **THEN** status refuses categorically before contacting any selected host.

### Requirement: REQ-FLEET-STATUS — Separate observation and client health

Fleet status MUST report source identity and categorical passive observations.
A healthy watchdog result MUST require a fresh successful completed invocation
and its active timer; a timer alone MUST NOT establish success. Unobserved
client-path health MUST remain unknown, including on UDP-only nodes.

#### Scenario: Timer survives a failed invocation

- **WHEN** the timer is active but the last watchdog invocation failed
- **THEN** the watchdog is unhealthy and client connectivity is not declared.

#### Scenario: Stale or absent success

- **WHEN** the completed result is absent, in progress, future-dated or too old
- **THEN** status reports unknown or stale rather than healthy.

#### Scenario: Successful passive collection

- **WHEN** all selected observations are valid and the watchdog has a recent
  successful completed invocation
- **THEN** the compact table and JSON retain those observations without calling
  a TCP listener reachable or blocked VPN access.

### Requirement: REQ-FLEET-MIN-ACTIVE — Authenticated survivor floor

Before each external rotation, the controller MUST count distinct surviving
nodes using current authenticated reports accepted by the canonical liveness
validator for every required profile. Plan nodes MUST bind exact inventory
provider/environment, alias and public service address to liveness targets.
The current rotation target and already-completed original targets MUST NOT
satisfy the survivor floor. Explicit nonrotating standby nodes MAY satisfy it.
Unknown, stale, wrong-target, unauthenticated, degraded or missing evidence
MUST NOT count. The controller MUST re-evaluate after operator confirmation.

#### Scenario: Healthy UDP-only survivor

- **WHEN** a survivor has fresh authenticated success for its required UDP
  profiles and no TCP/443 listener
- **THEN** it counts once toward the floor and rotation may proceed when enough
  survivors remain.

#### Scenario: Open socket without authenticated success

- **WHEN** TCP/443 is open but required protocol evidence is missing or failed
- **THEN** that node does not count and an unmet floor refuses before rotation.

#### Scenario: Evidence expires during confirmation

- **WHEN** earlier positive evidence expires before the operator confirms
- **THEN** the action requires a new accepted observation, not the old result.

### Requirement: REQ-FLEET-RESUME — Exact-plan progress

Rotation MUST validate a versioned plan and bind its private journal to the
canonical complete plan, ordered entries, survivor mapping and health-config
path. Resume MUST reject changed, legacy, malformed or inconsistent progress
before any external operation. Successful completed boundaries MUST resume
at exactly the next unfinished entry without repeating completed entries.

#### Scenario: Resume an unchanged plan

- **WHEN** one entry completed durably and the same plan is resumed
- **THEN** the completed entry is not rerun and the next entry retains its
  normal health and operator-review gates.

#### Scenario: Change entries under the same ID

- **WHEN** an entry, order, floor or health mapping changes without a new ID
- **THEN** resume refuses instead of skipping work or claiming completion.

### Requirement: REQ-FLEET-JOURNAL — Serialized durable transitions

The controller MUST hold an owner-controlled per-plan lock through orchestration
and atomically synchronize private progress before and after external steps.
It MUST retain an in-flight state on failed or interrupted external execution
and refuse automatic replay of an uncertain outcome. Dry-run MUST validate and
describe the plan without state publication, private health reads or host access.
Non-resume execution MUST NOT overwrite an existing journal.

#### Scenario: Concurrent execution

- **WHEN** another invocation owns the plan lock
- **THEN** the second invocation refuses without changing progress or starting
  a second rotation.

#### Scenario: Interruption or failed journal publication

- **WHEN** external execution or durable completion acknowledgement fails
- **THEN** the last complete journal remains recoverable, no later entry runs,
  and uncertain in-flight work requires operator reconciliation.

#### Scenario: Private state admission

- **WHEN** the state or lock is a symlink, unsafe file, foreign-owned file or
  malformed document
- **THEN** the invocation refuses without overwriting that authority.
