## Purpose

Provide a complete, privacy-bounded observability and Telegram incident path for
every managed server and supported VPN profile without confusing local process
state, missing telemetry, or one network vantage with authenticated client-path
availability.

## ADDED Requirements

### Requirement: REQ-OBS-TOPOLOGY — Monitoring survives a VPN node failure

The deployment MUST place the authoritative metrics/rule/alert control plane
outside every monitored P0/P1/P2 node and MUST identify its provider,
environment, host class, source revision, and failure domain without embedding
endpoints or credentials in repository artifacts. At least two approved
sentinels with distinct technical path signatures MUST remain separate from the
control plane and monitored nodes. A host MUST NOT monitor itself as the only
source of its availability verdict.

#### Scenario: A monitored VPN node disappears

- **WHEN** one P0, P1, or P2 node loses power or network reachability
- **THEN** the control plane and at least one external sentinel remain capable of
  evaluating the outage and delivering a redacted alert.

#### Scenario: Required independent placement is absent

- **WHEN** configuration places the control plane on a monitored VPN node or
  defines fewer than two approved sentinel path signatures
- **THEN** validation fails before provisioning, deployment, or scheduling.

### Requirement: REQ-OBS-HOST-CLASS — Control-plane and agent deployment is explicit and convergent

The deployment MUST define explicit observability-control-plane and
telemetry-agent host/profile configuration, feature toggles, role ordering,
resource limits, and supported provider outputs. Enabling MUST converge all
required units and validated configuration. Disabling MUST stop and remove
units, credentials, rules, dashboards, textfiles, and generated configuration
owned by the disabled component without removing historical storage or another
role's files unless an explicit destructive retention action is separately
authorized.

#### Scenario: Telemetry is disabled on one node

- **WHEN** the telemetry-agent toggle is changed from enabled to disabled and
  the node converges
- **THEN** its sender and owned credentials are absent, node_exporter remains
  loopback-only for local diagnostics, and central stale/retired inventory state
  cannot silently continue as healthy.

### Requirement: REQ-OBS-INGEST — Telemetry uses a write-only authenticated path

Every managed sender MUST scrape only explicitly allowlisted loopback metrics
and MUST send them outbound through a bounded Prometheus Remote Write endpoint.
The receiver MUST require TLS plus a unique revocable client identity per node,
bind that identity to one node-specific write path, accept only bounded
requests on that path, and reject unknown, revoked, cross-node, plaintext,
query, lifecycle, and administrative requests before forwarding the body.
Neither node_exporter nor Prometheus, Alertmanager, or dashboard interfaces MAY
be published as public administrative endpoints. The managed sender and its
root authority are the trust boundary for payload integrity: label/cardinality
validation MUST occur before remote write, while the ingress proxy MUST NOT
claim to inspect or rewrite the compressed protobuf body. Compromised-root
payload forgery is a declared residual risk rather than a falsely enforced
receiver guarantee.

#### Scenario: A node credential is reused for another identity

- **WHEN** a sender authenticates with a certificate or token assigned to a
  different inventory node or requests another node's write path
- **THEN** ingestion is rejected before the body reaches storage and a redacted
  security signal identifies the technical credential and requested aliases.

#### Scenario: The receiver is temporarily unavailable

- **WHEN** an authenticated sender cannot reach the remote-write receiver
- **THEN** it retains samples only for the configured bounded WAL window,
  exposes queue age/drop/error metrics locally, retries with backoff, and never
  redirects to an unauthenticated or public fallback.

### Requirement: REQ-OBS-METRICS — Metric schema is bounded, stable, and redacted

The system MUST publish a versioned allowlist of collected metric families,
labels, types, units, producer ownership, expected cadence, and staleness. It
MUST exclude UUIDs, keys, short IDs, passwords, bot tokens, chat IDs, IP
addresses, public camouflage targets, domains, client/user names, destinations,
raw log lines, process arguments, and secrets-derived hashes. Labels MUST use
bounded technical node, role, profile, policy, severity, and vantage aliases.
Renderer-owned evidence-state metrics MAY additionally use the finite
contract-declared state enum; unbounded values MUST be rejected before remote
write.

#### Scenario: A producer emits a forbidden label or excessive cardinality

- **WHEN** validation encounters a secret-shaped, endpoint-shaped, unknown, or
  unbounded label/value or the configured per-producer series ceiling is crossed
- **THEN** the offending family is rejected or dropped with an observable
  collector error, and its raw value is absent from logs, metrics, dashboards,
  alerts, and Telegram.

### Requirement: REQ-OBS-FRESHNESS — Silence and stale evidence are not health

Every non-self-describing producer MUST export collection success and last
completed collection time. Rules MUST distinguish healthy, degraded, firing,
stale, unknown, disabled, and retired states. Missing series, future timestamps,
failed collectors, remote-write backlog beyond policy, and evidence older than
its declared cadence MUST become stale or unknown and MUST NOT be evaluated as
zero events or successful availability.

#### Scenario: A textfile producer stops updating

- **WHEN** its last-success timestamp exceeds the declared staleness window
  while the node continues sending other metrics
- **THEN** a detector-stale alert fires and downstream zero-valued detector
  rules are inhibited rather than reporting a quiet healthy interval.

### Requirement: REQ-OBS-NODE — Every managed server has actionable health coverage

The rule set MUST cover node heartbeat, boot/reboot, CPU saturation, memory and
swap pressure, disk space and inode exhaustion, filesystem errors when exposed,
clock synchronization, network errors, process/resource pressure, required
systemd unit failure and restart loops, exporter health, telemetry queue health,
and deployed-source evidence. Thresholds, durations, exclusions, and severity
MUST be declared in validated configuration rather than hidden in templates.
This coverage MUST include VPN nodes, the observability control plane, and the
dead-man host. The control plane MUST self-scrape only loopback exporters; the
dead-man MUST publish a bounded signed resource/unit summary with its reverse
heartbeat without receiving fleet credentials.

#### Scenario: A node is reachable but a required transport unit fails

- **WHEN** fresh node metrics report a required VPN service in failed state for
  longer than its configured grace period
- **THEN** one service alert identifies the technical node and role, includes a
  repository runbook reference, and does not claim external VPN unavailability
  without matching client-path evidence.

### Requirement: REQ-OBS-VPN — VPN availability requires authenticated multi-vantage evidence

The system MUST ingest the redacted output of the canonical protocol-liveness
evaluator for every required REALITY, XHTTP, Hysteria2, and AmneziaWG logical
profile and endpoint variant. PromQL and the telemetry adapter MUST NOT
recompute or weaken the evaluator's variant, profile, direct-control, freshness,
sentinel, or quorum semantics; they MUST export and alert on its authoritative
one-hot verdict and evidence timestamps. A policy MAY become critical only after the
configured minimum number of distinct approved vantages report sustained
authenticated failure while their direct controls succeed. Unknown/error
evidence MUST inhibit a blocking or rotation conclusion. Local sockets,
processes, self-dial, bare TLS, ICMP, TCP connect, or traffic counters MUST NOT
substitute for client-path completion.

#### Scenario: One sentinel path fails

- **WHEN** one approved vantage reports all variants of a required profile
  blocked but the configured quorum is not met
- **THEN** the policy is degraded with a warning, remains below critical, and
  preserves the per-vantage evidence and freshness.

#### Scenario: Sustained quorum failure occurs

- **WHEN** the required number of distinct vantages report authenticated policy
  failure for three consecutive two-minute evaluations with healthy controls
- **THEN** one critical VPN-policy incident fires without automatic traffic
  promotion or credential rotation.

### Requirement: REQ-OBS-WATCHDOG — Recovery and paging remain separate contracts

Local systemd/watchdog supervision MUST retain bounded transport-specific
restart behavior and MUST export its last run, result, consecutive failures,
restart attempts, rate-limit state, and recovery outcome without credentials or
raw diagnostics. Central monitoring MUST observe but MUST NOT invoke watchdog,
restart services, promote a spare, mutate firewall/provider state, or treat a
successful restart as outside-in recovery.

#### Scenario: Local watchdog recovers a process

- **WHEN** bounded local recovery restarts a failed service successfully
- **THEN** the incident records the local recovery and may resolve the service
  alert only after fresh service evidence, while any client-path alert remains
  firing until authenticated external probes recover.

### Requirement: REQ-OBS-DETECTORS — Security and reachability detectors prove they are alive

Honeypot, policy-ratelimit, burn/reachability, certificate, Xray diagnostics,
and probing-summary producers MUST expose success, last-run, input progress, and
error state in addition to event counters. Alert rules MUST cover both threshold
events and dead/stale detector paths. An absence of events MUST NOT imply that a
detector consumed current input.

#### Scenario: A detector reads no new input after rotation

- **WHEN** its event counter remains zero but input-progress or last-success
  evidence stops advancing
- **THEN** the detector-health alert fires and no "no probing observed" health
  conclusion is emitted.

### Requirement: REQ-OBS-BACKUP — Backup alerts use recovery evidence, not timer state

Backup monitoring MUST separately represent local backup completion, optional
remote copy completion, repository integrity check, isolated restore source and
completion, and their timestamps. Timer/service activity or successful remote
configuration MUST NOT count as a copy, integrity, or restore result. Missing,
local-only, stale, malformed, future-dated, or fallback evidence MUST remain
explicitly unknown or degraded under configurable retention-aware thresholds.

#### Scenario: Backup timer is green but remote restore evidence is stale

- **WHEN** the scheduled unit is active while the latest approved offsite
  isolated restore proof exceeds its policy window
- **THEN** a recovery-readiness alert fires and the message does not claim that
  the backup is corrupt or absent without corresponding evidence.

### Requirement: REQ-OBS-RULES — Alert semantics are versioned and tested

Every alert MUST declare a stable name, owned signal, expression, severity,
pending duration, optional keep-firing duration, grouping keys, reminder
interval, inhibition relationships, expected resolution, runbook, and test
cases for firing, non-firing, stale, recovery, and absent-series behavior.
Each warning and critical condition MUST be a distinct alert with fixed severity;
critical alerts MUST inhibit their warning counterpart and both MAY share a
stable `incident_family` annotation for human correlation without changing either
alert's fingerprint. Alert fingerprints MUST use only stable allowlisted labels
such as environment, node_id, component, policy, profile, vantage, and severity;
timestamps, counts,
current values, and error details belong only in bounded annotations.
Critical host loss MUST inhibit derivative local service alerts; critical VPN
policy failure MUST group endpoint variants; monitoring pipeline faults MUST
inhibit unsupported healthy or event-rate conclusions without hiding known
independent incidents. Stale, missing, future-dated, or unknown evidence MUST
NOT produce a resolved transition; resolution requires fresh authoritative
healthy evidence for the configured recovery stability window.

#### Scenario: A node disappears with several failed services

- **WHEN** node freshness expires and its last systemd sample listed multiple
  failed required units
- **THEN** Telegram receives one grouped node-unreachable incident and the
  derivative service alerts are inhibited until node evidence returns.

### Requirement: REQ-OBS-TELEGRAM — Telegram carries a complete redacted incident lifecycle

Alertmanager MUST route firing, reminder, and resolved notifications
to validated private Telegram chat/topic destinations according to severity.
The bot MUST require no administrative privileges. Each bot token MUST be
materialized from SOPS through a systemd credential file; the numeric chat ID
and optional numeric topic ID MUST be validated into a root-readable generated
route configuration. None MAY appear in argv, general environment, logs, Git,
metrics, alert labels, or rendered evidence artifacts. Messages MUST contain
only technical aliases, state, start/duration, bounded evidence summary,
runbook link, and control-plane source identity; Telegram delivery failure MUST
be observable through an independent path. Templates MUST render only
allowlisted annotations, escape the selected Telegram parse mode, enforce a
bounded message/alert count, and truncate deterministically with an omitted
count. Firing and resolved messages MUST use the same stable label identity;
links MUST NOT contain tokens, endpoints, IP addresses, SNI values, or
credential-derived data.

#### Scenario: Telegram API rejects a notification

- **WHEN** a firing or resolved message is rejected, rate-limited, times out, or
  cannot be rendered
- **THEN** Alertmanager applies bounded request timeouts, backoff, and routing
  rate while retaining its native retry semantics, exposes the
  notification failure, preserves the incident, and does not log the token,
  chat ID, full request body, or sensitive alert data.

#### Scenario: An incident recovers

- **WHEN** its source evidence returns healthy for the configured recovery
  stability window
- **THEN** the same grouped incident produces one resolved Telegram message
  with recovery time and evidence class instead of silently disappearing.

### Requirement: REQ-OBS-DEADMAN — Loss of the monitoring plane pages independently

The authoritative control plane MUST emit a periodic heartbeat consumed outside
its host, provider failure domain, storage, Alertmanager, and primary Telegram
credential. A valid pulse MUST prove that Prometheus loaded the validated
configuration and evaluated rules, Alertmanager accepted the synthetic watchdog
incident, a local receipt-producing canary receiver observed the notification,
and the most recent low-frequency primary Telegram canary has a successful
API-level delivery outcome within policy. This proves the internal notification
path and primary API attempt, but not human Telegram receipt. Host process
liveness alone is insufficient. An independent minimal sender with a distinct revocable Telegram
credential MUST alert on missing or future-dated heartbeat and on recovery. The
dead-man path MUST contain no fleet secrets, MUST itself expose a testable
last-delivery result, MUST publish a reverse heartbeat consumed by the primary
control plane, and MUST send a low-frequency clearly labelled secondary-route
canary. The primary route MUST likewise send a low-frequency clearly labelled
canary so a revoked bot token or invalid route is detected before a real
incident. Loss of the dead-man heartbeat MUST alert through the primary route;
correlated loss of both paths remains a declared residual risk.

#### Scenario: The control plane loses power

- **WHEN** no valid heartbeat arrives for the configured deadline
- **THEN** the independent sender delivers one monitoring-plane critical alert
  and bounded reminders even though Prometheus and Alertmanager are unavailable.

### Requirement: REQ-OBS-PRIVATE-UI — Query and status-view access remains private

Prometheus, Alertmanager, and any dashboard UI/API MUST bind only to loopback or
an approved restricted management interface, use authenticated operator access,
and be absent from Terraform's public listener manifest. The minimum private
Prometheus/operator views MUST cover fleet overview, per-node resources,
per-profile multi-vantage liveness, detector/backup freshness, alert delivery,
and monitoring pipeline health while respecting the same metric allowlist and
redaction contract. Grafana or another dashboard dependency is optional and
MUST require separate dependency approval without weakening this boundary.

#### Scenario: A public listener would expose an admin surface

- **WHEN** rendered infrastructure or runtime configuration includes a public
  Prometheus, Alertmanager, dashboard, node-exporter, or agent listener
- **THEN** pre-convergence listener/security validation fails before any
  firewall or service change.

### Requirement: REQ-OBS-MAINTENANCE — Silences are bounded and non-authoritative

Every silence MUST have an authenticated owner, reason, explicit stable-label
scope, start time, and finite expiry within a configured maximum TTL. Indefinite
or over-broad silences MUST be rejected by a narrow authenticated silence
gateway that is the only writable silence interface. Direct write access to the
Alertmanager API MUST be unavailable to operators and public clients. Maintenance MUST suppress delivery
without changing source metrics, verdicts, incident timestamps, or health;
silence creation, expiry, and deletion MUST be auditable without secrets.
Telegram messages and bot callbacks MUST NOT grant authority to create a
silence, restart a service, promote a spare, mutate a provider/firewall, or
rotate credentials.

#### Scenario: A maintenance silence expires during an outage

- **WHEN** a scoped finite silence expires while its fresh authoritative source
  remains firing
- **THEN** normal notification resumes for the existing incident without a
  false recovery, changed fingerprint, or source-state mutation.

### Requirement: REQ-OBS-RETENTION — Storage is bounded and is not a usage ledger

The control plane MUST declare time and size retention, disk reserve, compaction
resource limits, backup policy for alert/rule configuration, and behavior when
storage approaches its limit. Per-user metrics and raw logs MUST remain absent;
traffic counters MUST be treated as resettable diagnostics rather than billing,
identity, or durable usage evidence. Loss of historical samples MUST NOT erase
the current alert state or be reported as current health.

#### Scenario: Metrics storage reaches its reserve threshold

- **WHEN** projected or actual TSDB usage crosses the configured warning or
  critical reserve
- **THEN** an alert fires before filesystem exhaustion and retention remains
  bounded without deleting configuration, secrets, or unrelated host data.

### Requirement: REQ-OBS-SECRETS — Observability credentials are least-privilege and rotatable

The SOPS schema and coverage checks MUST distinguish per-node remote-write
identity, receiver trust, Telegram routing, dead-man Telegram, and optional UI
access material. Credentials MUST be unique by authority, root-owned at runtime,
redacted under Ansible no-log, absent from generated inventory/state/reports,
and rotatable one authority at a time with overlap only for a bounded validated
window. A failed rotation MUST restore the prior working identity without
revoking it or publishing plaintext.

#### Scenario: One node identity is compromised

- **WHEN** the operator revokes that sender's credential
- **THEN** other nodes continue ingesting, the revoked node is reported stale,
  and the credential cannot reach any write path. The sender/root boundary is
  still trusted for sample `node_id` integrity; revocation does not retroactively
  prove that payloads sent before revocation were truthful.

### Requirement: REQ-OBS-CONFIG — Invalid configuration fails before runtime mutation

Repository validation MUST check inventory identity, topology independence,
metric allowlists, rule syntax/tests, Alertmanager routing/templates, Telegram
destination types, secret structure/coverage, TLS trust, unit hardening,
retention bounds, dashboards, and cross-file references before Ansible mutates a
host. Runtime publication MUST stage and validate complete generations, reload
only after validation, retain a private last-known-good generation, and restore
it if readiness checks fail.

#### Scenario: A new alert rule or template is invalid

- **WHEN** rule or Alertmanager validation rejects a candidate generation
- **THEN** deployment fails before reload, the currently running generation and
  notification path remain unchanged, and no partial rule/template set is live.

### Requirement: REQ-OBS-MIGRATION — Migration avoids duplicate or missing paging

Migration MUST proceed through a staging control plane, one canary sender, all
senders, sentinels, shadow rule evaluation, Telegram delivery drills, and only
then authoritative cutover. Direct ntfy/Pushover paging MUST remain enabled
during a bounded, documented overlap and be removed only after equivalent
firing and recovery evidence is observed centrally. Rollback MUST restore the
last-known-good central generation and previous paging authority without
leaving duplicate schedules or credentials.

#### Scenario: Central Telegram cutover fails

- **WHEN** staged central alerts evaluate correctly but real Telegram firing or
  resolved delivery is not observed
- **THEN** per-node paging remains authoritative, production cutover is refused,
  and the result is reported as partial rather than complete.

### Requirement: REQ-OBS-OPERATIONS — Operator actions are explicit and bounded

The Makefile/operator surface MUST provide separate commands for configuration
validation, control-plane deployment, agent deployment, passive status, rule
tests, one-shot protocol evaluation, Telegram delivery test, dead-man test,
staging fault drills, credential rotation, rollback, and removal. Commands MUST
require explicit host/environment scope, preserve host-key and source identity,
avoid implicit provider/deploy/repair actions, redact output, and document
whether they read, mutate, notify, or inject failure.

#### Scenario: An operator requests a Telegram test

- **WHEN** the explicit test command targets a configured staging destination
- **THEN** it sends a clearly labelled synthetic firing and resolved pair,
  records delivery evidence without secrets, and performs no deploy, service
  restart, provider mutation, or production fault injection.

### Requirement: REQ-OBS-ACCEPTANCE — Completion requires real end-to-end evidence

Completion MUST include tests-first unit/contract coverage, role convergence and
idempotence, strict config/rule/template validation, full repository gates,
hosted CI at the exact candidate SHA, staged failure injection for every root
incident lifecycle and inhibition path, deterministic rule-state proof for
every alert class, exact-source control-plane and agent deployment,
fresh metrics from every managed host, authenticated external traffic for every
required VPN profile from at least two vantages, observed real Telegram firing
and resolved messages, dead-man loss/recovery, credential rotation, and rollback.
Fixtures, queued jobs, a green timer, a successful push, or one-vantage traffic
MUST NOT substitute for the corresponding live evidence.

#### Scenario: Source and fixture gates pass without live delivery

- **WHEN** local and hosted validation pass but approved live hosts, sentinels,
  Telegram credentials, or a staging failure window are unavailable
- **THEN** implementation may be reported as source-complete while the feature
  remains open with the exact missing live acceptance steps.
