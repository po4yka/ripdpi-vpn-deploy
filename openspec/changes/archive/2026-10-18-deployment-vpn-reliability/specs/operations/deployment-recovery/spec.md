## Purpose

Keep deployment phases ordered and retain complete accepted VPN authority when
candidate publication fails, while preserving exact environment recovery state.

## ADDED Requirements

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
