## Purpose

Define the recovery, backup, patch-window and local-audit properties that the operations roles must hold on a managed node, so that a wedged transport is recovered without harm to a serving one, a backup failure is visible, and routine maintenance does not link or interrupt all nodes at once.

## ADDED Requirements

### Requirement: REQ-WATCHDOG-PROFILES — Single-transport profiles run the watchdog

The `vpn-p1-web` and `vpn-p2-udp` profiles MUST enable the watchdog role.

#### Scenario: XHTTP or UDP node

- **WHEN** a node of either profile converges
- **THEN** the watchdog timer is installed and probes the enabled transports of that profile

### Requirement: REQ-WATCHDOG-STATS-DIAGNOSTIC — A failed API query alone does not restart Xray

The watchdog MUST report a failed Xray StatsService query as a failed probe. It MUST NOT request Xray recovery for that failure unless an authenticated canary request, sent by the watchdog's own client through Xray, fails in the same run. A lost probe client or an occupied probe port MUST NOT count as that failure.

#### Scenario: API query fails while Xray serves

- **WHEN** the StatsService query fails and every authenticated round trip succeeds
- **THEN** the run is red and no recovery is requested

#### Scenario: API query and round trip fail together

- **WHEN** the StatsService query and an authenticated round trip fail in one run that reaches the failure threshold
- **THEN** the watchdog requests guarded Xray recovery

### Requirement: REQ-WATCHDOG-OUTAGE-BUDGET — Recovery stops when it does not end the outage

The watchdog MUST count recovery attempts since the last run in which no unit failed its diagnostics, and MUST withhold recovery when the count reaches `kicks_per_outage_max`. It MUST keep alerting within the alert limit. A run that selects no unit MUST reset the count. An unreadable or malformed count MUST withhold recovery.

#### Scenario: Recovery does not help

- **WHEN** the configured number of recovery attempts did not end the unit failure
- **THEN** later red runs report that recovery is withheld and request no restart

#### Scenario: Outage ends

- **WHEN** a run selects no unit after the budget was spent
- **THEN** the next outage can use the full budget again

### Requirement: REQ-WATCHDOG-RESOURCE-BOUNDS — The probe run is bounded

The watchdog service unit MUST set a memory limit and a CPU quota. The watchdog timer MUST add a random delay of at least half the default interval.

#### Scenario: Rendered units

- **WHEN** the watchdog units are rendered
- **THEN** the service contains `MemoryMax` and `CPUQuota` and the timer contains `RandomizedDelaySec=150`

### Requirement: REQ-BACKUP-START-DEADLINE — Backup oneshots cannot hang without limit

The backup service and the restore-drill service MUST set a finite `TimeoutStartSec`.

#### Scenario: Hung remote call

- **WHEN** a restic or rclone call does not return
- **THEN** systemd stops the unit at the deadline and the next timer run can start

### Requirement: REQ-BACKUP-REMOTE-IDENTITY — A sync never replaces another repository

Before the remote sync, the backup script MUST compare the remote repository `config` file with the local one. It MUST fail the remote stage without a sync when the bytes differ or when the remote listing fails. An absent remote copy MUST be treated as a first sync.

#### Scenario: Recreated node with a new repository

- **WHEN** the remote path holds a repository with a different `config` file
- **THEN** the script syncs nothing, publishes a failed remote stage and exits non-zero

#### Scenario: First sync

- **WHEN** the remote directory does not exist
- **THEN** the script syncs and verifies the repository

### Requirement: REQ-RESTORE-DRILL-WINDOW — Drill cadence and freshness windows agree

The restore drill MUST run weekly by default. Passive inspection and the health adapter default MUST treat restore evidence as stale after 15 days. Passive inspection MUST treat the restored snapshot as stale only when it is older than that window plus the 36-hour snapshot age that the drill admits.

#### Scenario: One missed drill

- **WHEN** the last successful drill is 14 days old
- **THEN** inspection reports the restore evidence and its snapshot as observed

#### Scenario: Two missed drills

- **WHEN** the last successful drill is more than 15 days old
- **THEN** inspection reports the restore evidence as stale

### Requirement: REQ-INSPECT-REBOOT-SIGNAL — A pending reboot is visible

The passive inspection report MUST contain a boolean `reboot_required` that is true when `/run/reboot-required` exists on the node. The field MUST NOT change the observation status.

#### Scenario: Package update needs a restart

- **WHEN** `/run/reboot-required` exists
- **THEN** the report has `reboot_required: true` and the controller accepts the report

### Requirement: REQ-UPGRADE-WINDOW-STAGGER — Unattended upgrades do not run on all nodes in one window

The package updates role MUST give the daily unattended-upgrade timer a delay of up to 12 hours that is fixed for each host. It MUST NOT change the calendar time of the timer or restart the timer.

#### Scenario: Converged host

- **WHEN** the role converges a host
- **THEN** the timer drop-in contains `RandomizedDelaySec=12h` and `FixedRandomDelay=true`, and no upgrade starts because of the deploy

### Requirement: REQ-TAILSCALED-NO-LOG-UPLOAD — tailscaled keeps its logs on the node

The Tailnet management role MUST configure tailscaled with log upload disabled, before the first daemon start on a new node. On an enrolled node it MUST NOT restart tailscaled to apply the setting.

#### Scenario: Enrolled node

- **WHEN** ordinary convergence runs on an enrolled node
- **THEN** the systemd drop-in with `TS_NO_LOGS_NO_SUPPORT=true` exists and tailscaled was not restarted

### Requirement: REQ-ACTIVATION-LOCK-DEADLINE — Runtime activation does not wait for a lock without limit

The runtime-release activation helper MUST refuse with an unsafe-state result when it cannot take the install-root lock within its wait limit.

#### Scenario: Lock held by a hung activation

- **WHEN** another process holds the install-root lock longer than the wait limit
- **THEN** the helper exits with the unsafe-state result and changes nothing

### Requirement: REQ-LYNIS-OFFLINE — The host audit makes no vendor query

The Lynis collector MUST run the scanner with its online version test disabled.

#### Scenario: Audit run

- **WHEN** the collector starts the scanner
- **THEN** the scanner receives a profile that contains `skip-upgrade-test=yes`
