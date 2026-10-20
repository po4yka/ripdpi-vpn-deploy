# operations/deployment-recovery Specification

## Purpose
Keep deployment phases ordered and retain complete accepted VPN authority when
candidate publication fails, while preserving exact environment recovery state.
## Requirements
### Requirement: REQ-DR-ORDER — Run dependent phases in order

Blue-green MUST complete init, plan, apply, dry-run and deploy in dependency order
regardless of inherited Make parallel settings. A failed phase MUST stop later phases.

#### Scenario: Failed check with parallel Make settings

- **WHEN** dry-run fails while inherited Make controls request parallel work
- **THEN** deploy never starts and the command reports failure

### Requirement: REQ-DR-PREDICT — Honor dry-run intent

Blue-green MUST honor both DRY_RUN=1 and --dry-run without private-input access
or infrastructure mutation. Invalid explicit dry-run values MUST refuse.

#### Scenario: Environment-only prediction

- **WHEN** DRY_RUN=1 is set without SSH credentials
- **THEN** the command prints the planned sequence and exits successfully

### Requirement: REQ-DR-STATE — Bind backups to one exact environment

State retention and documented recovery MUST select only exact provider and
environment backups with complete supported timestamps. Existing valid backup
names MUST remain usable and unrelated backups MUST remain intact.

#### Scenario: Environment names share a prefix

- **WHEN** prod and prod-green backups coexist and prod retention or recovery runs
- **THEN** prod-green backups are neither removed nor selected as prod state

### Requirement: REQ-DR-FIREWALL — Preserve accepted transport policy

Firewall publication MUST remain coherent with its consumers. Failure before a
consumer's acceptance MUST restore the accepted firewall, and a tagged operation
MUST NOT commit unrelated changed AWG policy without its consumer reconciliation.

#### Scenario: Protected staging fails before AWG

- **WHEN** candidate peer claims change and protected staging then refuses
- **THEN** old AWG configuration and forwarding policy agree after compensation

#### Scenario: Unrelated tagged operation

- **WHEN** only Xray is selected while desired AWG authority differs
- **THEN** the run reconciles the required consumer or refuses before unsafe policy publication

### Requirement: REQ-DR-AWG — Retain complete AWG authority through acceptance

AWG upgrades MUST retain prior executable bytes, shared units, configuration and
activation state until all owned instances accept the candidate. Rejected
activation MUST restore that complete authority before restarting prior instances.
Check mode MUST remain predictive and foreign recovery state MUST refuse.

#### Scenario: Candidate executable or unit fails

- **WHEN** the new executable or unit cannot start a previously active instance
- **THEN** compensation restores the old executable, unit and configuration and recovers prior activation

### Requirement: REQ-DR-CHILD — Reclaim owned command descendants

CI subprocess control MUST retain safe process-group authority through cleanup and
reclaim surviving descendants before teardown, including when the command leader
has exited. Output MUST stay in private diagnostics without credential exposure.

#### Scenario: Exited leader leaves a descendant

- **WHEN** the leader exits with failure or a descendant retains output pipes beyond the deadline
- **THEN** the command fails and no descendant continues work after cleanup returns

#### Scenario: Successful leader leaves descendants

- **WHEN** a successful command leader exits while descendants are still active
- **THEN** success is returned only after owned descendants are reclaimed

### Requirement: REQ-DR-ENV-ISOLATION — Refuse the reserved default alias

Environment entrypoints MUST refuse `default` before Terraform execution or
private-input access. `prod` MUST retain its legacy default workspace. Blue-green
MUST require distinct admitted state identities before green provisioning.

#### Scenario: Production alias collision

- **WHEN** blue-green selects prod and default as its two environment names
- **THEN** it refuses before provisioning, decryption or state changes

### Requirement: REQ-DR-STATE-ATOMIC — Publish only complete state artifacts

Encrypted backup and state restoration MUST use private owned temporary files.
Failed encryption, decryption or state validation MUST preserve accepted outputs
and remove only the invocation's temporary data. Published backups MUST remain
distinct under concurrent or same-second calls and retain exact-environment selection.

#### Scenario: Interrupted encryption or invalid restoration

- **WHEN** encryption cannot finish or restoration receives truncated ciphertext
- **THEN** no incomplete final backup appears and the prior working state remains unchanged

### Requirement: REQ-DR-SHARE-READ — Limit published recipient read authority

Published share directories MUST permit traversal and listing only to their owner
and nginx group. Bundle files MUST permit reading only to that owner and group.
Convergence MUST repair old modes without changing recipient bytes.

#### Scenario: Existing publicly readable bundle

- **WHEN** an accepted share tree contains old world-readable files and directories
- **THEN** convergence retains its bytes, nginx can read it and an unrelated UID cannot list or read it

### Requirement: REQ-DR-HOPPING-ADMISSION — Refuse unsupported recipient hopping

RIPDPI export MUST refuse Hysteria port hopping before recipient publication.
Official sing-box export MUST retain supported hopping. Other existing format
and transport compatibility checks MUST remain effective.

#### Scenario: RIPDPI recipient selects a hopping profile

- **WHEN** a selected Hysteria profile has a nonempty port range and format ripdpi
- **THEN** generation fails without publishing a partial recipient artifact

### Requirement: REQ-DR-RESTORE-COMPLETE — Verify all selected restore inputs

The restore drill MUST validate every required artifact selected by the effective
backup profile, including subscription authority, auxiliary transports and topology
configuration. Missing or empty selected artifacts MUST preserve prior success
evidence and restored secret cleanup MUST precede successful publication.

#### Scenario: Snapshot contains baseline files only

- **WHEN** subscription-only, Naive or split-hop is selected but the snapshot lacks its required files
- **THEN** the drill fails, removes its owned restore tree and publishes no new success marker

### Requirement: REQ-DR-MIRROR-STOP — Retire disabled mirror execution

Changing mirror enabled from true to false MUST stop and disable its exact owned
execution units before other publication changes. It MUST preserve accepted payloads,
replay and revocation authority. Fresh disabled and repeated disabled convergence
MUST be safe and idempotent; check mode MUST not stop or delete runtime state.

#### Scenario: Enabled mirror becomes disabled

- **WHEN** the mirror toggle becomes false while subscription-host remains enabled
- **THEN** no future scheduled pull starts, including after restart, and retained delivery authority remains intact

### Requirement: REQ-DR-PROCEDURE — Include complete recovery prerequisites

Both recovery paths and the restore dry-run MUST include the current pinned SSH,
recovery foundation, management handoff and private deployment-input prerequisites
before deployment. Dependent Make phases MUST be separate ordered commands.

#### Scenario: Recovery on a fresh operator workstation

- **WHEN** the operator follows either documented recovery path
- **THEN** the procedure provides the complete prerequisite sequence and does not imply missing private inputs are generated automatically

### Requirement: REQ-DR-DHCPV6 — Preserve scoped address acquisition

The guest firewall MUST admit DHCPv6 UDP 547-to-546 replies and 546-to-547 requests
only on an admitted uplink with appropriate IPv6 scope. Exact configured IPv6
server addresses MAY support legacy unicast exchanges. Wrong interfaces, ports and
unapproved global sources MUST remain denied, including under strict egress.

#### Scenario: DHCPv6 bootstrap or rebind under strict policy

- **WHEN** an admitted uplink exchanges multicast discovery and a valid server reply
- **THEN** address acquisition succeeds while equivalent traffic on an unrelated interface or from an unapproved source is denied
