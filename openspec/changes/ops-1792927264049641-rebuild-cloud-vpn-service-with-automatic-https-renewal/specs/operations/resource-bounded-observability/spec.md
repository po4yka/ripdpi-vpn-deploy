## Purpose

Keep bounded monitoring independent of personal devices and distinguish source evidence from the authorized cloud rollout.

## MODIFIED Requirements

### Requirement: REQ-IRBO-SCOPE — Source completion and deployment boundary

Source completion MUST require source gates, exact-revision hosted CI and isolated real-runtime positive acceptance. It MUST NOT by itself require or claim provider access, live deployment, external notification delivery, human receipts, live authenticated VPN performance or cutover. Completion MUST distinguish that source evidence from an authorized live deployment and client evidence. A future deployment MUST require exact-host capacity, private-path and backup admission, credential authority, matched VPN non-regression and explicit cutover approval. An independent cloud observer MAY be provisioned within a separately approved provider and cost bound; this MUST NOT restore the retired dedicated collector topology or raise existing monitoring resource limits. Production admission MUST be explicit. Notifications and human receipt MUST NOT be claimed without actual authority and observed delivery.

#### Scenario: Authorized cloud-only rollout

- **WHEN** an owner approves the exact cloud topology and costs and personal devices are excluded
- **THEN** an independent cloud observer can be admitted after its own checks, collector and agent limits remain unchanged, and local, live, client and notification results are reported separately.

#### Scenario: Source complete with no external infrastructure

- **WHEN** source, hosted and isolated runtime gates pass without external infrastructure
- **THEN** completion records that scope, keeps live categories not applicable from task creation and states that external deployment/notification acceptance has not occurred; planning, mocks alone and refusal-only behavior do not satisfy completion.

#### Scenario: Private collector ingress survives ordinary convergence

- **WHEN** the approved collector admits remote-write over Tailnet
- **THEN** the canonical guest firewall permits TCP/9443 only on `tailscale0`, to its observed Tailnet IPv4 address, from at most ten unique exact Tailnet IPv4 senders; invalid scope refuses before mutation in normal and check mode, and other nodes retain the disabled default.

#### Scenario: Full VPN convergence preserves the monitoring component

- **WHEN** an ordinary full VPN deployment runs on a host with an admitted agent
- **THEN** it MUST leave agent installation and removal to the exact-host observability lifecycle, preserving its accepted queue, credentials and node heartbeat.

### Requirement: REQ-IRBO-OBSERVER — Independent observer runtime

The implementation MUST provide a pinned private Uptime Kuma container with bounded resources, distinct monitor credentials, direct node and pipeline producers, restricted verified HTTPS push ingress, private administration, and encrypted quiesced backup with isolated restore. Observer placement MUST be independent of the collector before deployment. Notification-enabled mode MUST include the additional delivery producer and N+2 monitors. Explicit panel-only mode MUST use N+1 node/pipeline monitors, MUST NOT require external bot credentials, and MUST NOT fabricate a delivery heartbeat or message receipt.

#### Scenario: Missing signals and recovery

- **WHEN** isolated pinned Kuma receives qualified signals and later loses node/pipeline or delivery pushes
- **THEN** actual monitors detect missing and never-started signals within configured bounds, preserve monitor state through restart and recover from encrypted backup in an isolated instance with notifications disabled.

#### Scenario: Panel-only observer

- **WHEN** the owner selects panel-only monitoring without external notification credentials
- **THEN** node and pipeline monitors operate with distinct credentials and bounded resources, the panel exposes their state privately, and delivery remains explicitly disabled.

#### Scenario: Separate service profiles without external notification providers

- **WHEN** the separate P0, P1 and P2 service profiles converge
- **THEN** monitoring and backup remain enabled, restricted Tailnet management stays enabled, and the standalone ntfy/Pushover watchdog is disabled.

### Requirement: REQ-IRBO-DELIVERY — Honest relay evidence

Notification-enabled mode MUST distinguish fresh-message send from edit receipts and API acknowledgement from human receipt, require distinct primary/secondary notification authority, and withhold success for stale, invalid or failed canaries. Synthetic rule-to-relay receipts MUST be fresh and single-use. Both Telegram routes MUST disclose their common dependency. Panel-only mode MUST explicitly disable the relay and delivery heartbeat, without treating absent notification authority as successful external delivery.

#### Scenario: Stale or failed receipt

- **WHEN** an isolated relay/producer receives a stale receipt, failed canary or missing delivery authority
- **THEN** it refuses a healthy delivery heartbeat without logging credentials; actual Telegram delivery and human receipt remain unverified outside this task.

#### Scenario: Panel-only activation is rejected

- **WHEN** an existing notification-enabled collector changes to panel-only and candidate startup or readiness fails
- **THEN** its previous configuration, unit and credential authority remain available for rollback; notification retirement starts only after ready collector activation commits.

## ADDED Requirements

### Requirement: REQ-IRBO-SECURITY — Verified observer security updates

Observer image updates MUST use exact architecture digests and a locked package
set. CI MUST scan production runtime images, not only test images. Fixed
HIGH/CRITICAL dependency findings MUST be resolved before rollout; unfixed or
inapplicable findings MUST retain explicit evidence and restrictions. Updates
MUST preserve the private dashboard, monitor credentials and encrypted backup.

#### Scenario: Upstream version still contains fixed vulnerabilities

- **WHEN** a stable upstream observer image retains dependencies with available security fixes
- **THEN** the operator MUST build and verify the patched runtime before deployment, without hiding findings or weakening the scanner gate.

#### Scenario: Restricted dashboard tunnel

- **WHEN** observer management is hardened
- **THEN** only local TCP forwarding to the exact loopback dashboard is allowed, agent and remote forwarding are denied, and dual-path SSH recovery remains available.


#### Scenario: Private address appears after nginx boot starts

- **WHEN** the observer starts before its private listener address is assigned
- **THEN** nginx MUST wait for that exact address before the stock configuration test, within a finite startup bound; address or socket refusal MUST fail the unit, and the same private listener and source restrictions MUST remain.

### Requirement: REQ-IRBO-HOST-KERNEL — Independent observer kernel prerequisites

The observer MUST use an exact-host operator configuration for the approved IPv4
TCP IP-options guard and disabled MPTCP. It MUST stay outside the VPN inventory.
Kuma MUST NOT import VPN baseline or firewall roles. Changes MUST preserve foreign
rules, access grants, private monitoring authority and resource limits. Encrypted
recovery MUST include all prerequisite files, source bindings and validation.

#### Scenario: Add the independent observer guard

- **WHEN** the observer lacks the approved kernel mitigation
- **THEN** the operator MUST install one owned inet input guard at priority `-310` that drops IPv4 TCP packets with IP options, without a global ruleset flush or changes to other tables.
- **AND** an existing foreign table or unbound ruleset loader MUST refuse before kernel writes; the persistent guard MUST start after the admitted loaders and before network preparation, and normal loader reloads MUST retain it.

#### Scenario: Drain existing MPTCP socket owners

- **WHEN** the observer has existing MPTCP sockets
- **THEN** the operator MUST identify their exact native service owners and bind a bounded maintenance plan before changes; unknown owners MUST refuse maintenance.
- **AND** acceptance MUST require persistent and effective `net.mptcp.enabled=0`, zero remaining MPTCP sockets, restored previously running services, and fresh public and Tailnet SSH/SFTP.
- **AND** a rollback that restores MPTCP to `1` MUST reopen the security finding.

#### Scenario: Prove the kernel boundary and preserve private monitoring

- **WHEN** the observer guard is active
- **THEN** real packet checks MUST prove that IPv4 TCP IP options are dropped while ordinary TCP, TCP-header options, UDP including IPv4 IP options, and IPv6 retain their normal policy.
- **AND** the private panel, ingress and monitor authority MUST remain valid; boot ordering that has no observed reboot MUST be reported as structural verification, and this mitigation MUST NOT be reported as a kernel patch.
