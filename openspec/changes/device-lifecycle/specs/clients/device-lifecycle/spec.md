## Purpose

Provide one reviewed, resumable device lifecycle across the complete declared
fleet, protocol authorities and subscription publishers without false completion.

## ADDED Requirements

### Requirement: REQ-DEVICE-OPERATION-PLAN — Exact fleet and authority review

The implementation MUST bind a private operation to its device, action, complete
declared inventory, independent encrypted node authorities, publishers, cohorts,
SSH pins, source revision and current private input fingerprints. The preview
MUST identify affected nodes, transports and grants without exposing credentials.

#### Scenario: An old source still retains a migrated device credential

- **WHEN** the registry now names a replacement but an earlier node still has a
  protocol credential for the requested device
- **THEN** discovery includes that earlier node in complete revocation.

#### Scenario: Incomplete or changed scope

- **WHEN** a managed inventory node lacks a declared authority, a publisher is
  unavailable, or inputs change after review
- **THEN** mutation refuses instead of silently omitting that authority.

### Requirement: REQ-DEVICE-OPERATION-ISSUE — Usable per-device issuance

The implementation MUST generate distinct credentials for a new device, prepare
every selected node's enabled transports, converge those nodes, publish a usable
subscription and create an explicit private recipient artifact. It MUST preserve
server keys and unrelated devices and retain original generated values on resume.

#### Scenario: One device uses multiple baseline and optional transports

- **WHEN** an approved enrollment selects nodes enabling REALITY, XHTTP,
  Hysteria2, AWG, Snell or Naive
- **THEN** each selected transport receives that device's own identity, runtime
  adoption is checked and the private recipient output contains usable access.

### Requirement: REQ-DEVICE-OPERATION-REFRESH — All current deliveries update

The implementation MUST update every active subscription grant for the device
from current admitted authority while retaining each grant's URL, format and
expiry. It MUST preserve exact committed bytes across a lost acknowledgement
and refuse competing issuance or revocation.

#### Scenario: Multiple URLs and an interrupted refresh

- **WHEN** a device has multiple active grants and the second publication loses
  its acknowledgement after committing
- **THEN** resume reconciles the same documents and completes all URLs without
  issuing replacement tokens or claiming partial publication is complete.

### Requirement: REQ-DEVICE-OPERATION-REVOKE — Complete runtime revocation

The implementation MUST remove the device from every declared protocol
authority and membership, revoke all discovered subscription hashes and update
registry lifecycle state. Completion MUST require exact-node runtime adoption,
old credential rejection for every retained credential preimage and publisher
revocation observed through the running access policy. Health/control failure
MUST remain unknown rather than being accepted as credential rejection.

#### Scenario: Source credentials were removed before subscription cleanup

- **WHEN** current node authorities have no remaining device row but an exact
  published grant still names the device
- **THEN** revocation adopts and verifies canonical runtime state on every node,
  denies all matching grants, and reports zero native credential profiles when
  no preimage remains; it does not claim that an old-key traffic probe ran.

#### Scenario: A node is unavailable midway

- **WHEN** two nodes adopt revocation and a third cannot be reached
- **THEN** the operation remains incomplete with the third node outstanding and
  resume verifies actual state before continuing.

#### Scenario: Last device or optional transport

- **WHEN** the device is the last user of an enabled transport or also has
  Naive/Snell authority outside the baseline profile
- **THEN** revocation includes that authority and verifies runtime denial,
  preserving the transport's established empty-user/disabled-service behavior.

### Requirement: REQ-DEVICE-OPERATION-RESUME — Durable monotonic execution

The implementation MUST store encrypted intent before cross-authority mutation,
serialize operations, fence every private/transport input and reconcile a lost
acknowledgement against exact expected state. Public output MUST be categorical.
Revocation MUST never automatically roll back to accepted old credentials.

#### Scenario: Partial local or remote commit

- **WHEN** the process stops after a target SOPS commit, runtime adoption,
  publication or private artifact write
- **THEN** resume recognizes exact ownership, retains unrelated changes and
  executes only the missing checks or actions for the approved generation.

#### Scenario: Unexpected external change

- **WHEN** a different operation changes a required credential, grant or host
- **THEN** resume refuses reconciliation rather than overwriting it or marking
  the operation complete.
