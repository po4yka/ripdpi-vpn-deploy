## Context

The repository already has privacy-bounded signal producers but no durable
fleet-wide consumer. The `monitoring` role owns loopback node_exporter,
systemd/process/textfile collection, Xray counters, and local log retention. The
`watchdog` role owns process/listener/configuration checks, authenticated local
REALITY self-dial, and bounded restart. The canonical protocol-liveness
evaluator owns external multi-vantage REALITY/XHTTP/Hysteria2/AmneziaWG truth,
including direct-control, variant, profile, sentinel, freshness, quorum, and
rotation-candidate semantics. Backup owns restic/rclone and restore evidence;
honeypot/policy-ratelimit/burn-check own their detector outputs; node_manifest
owns deterministic deployed capability/source metadata.

The current alert paths are intentionally local/operator-side. node_exporter is
loopback-only. Watchdog and protocol-liveness send ntfy/Pushover directly, but
the watchdog suppresses notification transport failures and advances its alert
counter, so that counter is not delivery proof. Missing textfile updates can
look like zero events. A process/listener or self-dial cannot prove the client
path, and a dead central host cannot send its own Telegram alert.

The change therefore adds consumers and adapters around existing ownership
seams. It does not reimplement protocol probes, backup, recovery, security
detectors, or transport service management.

## Goals / Non-Goals

- Goal: provide one always-on, versioned, redacted fleet view and authoritative
  Telegram incident lifecycle for every expected server and VPN profile.
- Goal: make missing/stale/unknown evidence visible without converting it into
  healthy, blocked, or recovered state.
- Goal: retain strict separation among local supervision, central evaluation,
  external client-path evidence, paging, automatic recovery, and promotion.
- Goal: make the control plane, agent, ingress, rules, Telegram, dead-man,
  credential rotation, rollback, and live proof reproducible from Git + SOPS.
- Non-goal: forward raw journals, access logs, destinations, client/user
  identity, per-user traffic, IPs, camouflage targets, or credential-derived
  data.
- Non-goal: expose node_exporter, Prometheus, Alertmanager, or an admin panel on
  a public listener.
- Non-goal: use alerting to auto-restart services, change routes/firewalls,
  promote a spare, rotate credentials, or provision provider resources without
  a separately authorized operator action.
- Non-goal: replace the canonical protocol-liveness evaluator with blackbox
  probes or PromQL. Plain HTTP/TLS/DNS/TCP probes are supplementary only.
- Non-goal: deploy Grafana in the initial capability. Prometheus query/status
  views and operator commands are sufficient; Grafana requires separate
  dependency approval and remains behind the same private-access boundary.
- Non-goal: make a single TSDB highly available. The independent dead-man pages
  loss of the first control plane; a future HA/storage change can remove that
  single point of evaluation/storage.

## Decisions

### 1. Three explicit runtime roles

```text
managed VPN node                          external sentinel
┌──────────────────────────────┐          ┌──────────────────────┐
│ existing producers           │          │ canonical protocol   │
│ node_exporter 127.0.0.1:9100 │          │ liveness runner      │
│ watchdog/backup/manifest     │          └──────────┬───────────┘
│              │               │                     │ redacted result
│ observability_agent          │                     │
│ scrape + bounded WAL         │                     │
└──────────────┬───────────────┘                     │
               │ outbound remote_write               │
               ▼                                     ▼
┌──────────────────────────────────────────────────────────────┐
│ observability_control_plane                                  │
│ mTLS write-only ingress → Prometheus TSDB/rules              │
│ canonical liveness adapter → expected inventory              │
│ Prometheus → Alertmanager → primary Telegram                 │
│ query/status interfaces: loopback/restricted management only │
└──────────────────────────────┬───────────────────────────────┘
                               │ signed/secret-authenticated pulse
                               ▼
                   ┌─────────────────────────┐
                   │ observability_deadman   │
                   │ independent host/path   │
                   │ secondary Telegram bot  │
                   └─────────────────────────┘
```

`observability_agent` runs after `node_manifest` on monitored nodes so every
upstream role has converged before its adapter reads evidence. It scrapes
loopback node_exporter and exports bounded adapters for watchdog state, backup
markers, and node manifest. It never re-runs their producers.

`observability_control_plane` is a separate technical host profile and playbook,
not another branch of the VPN transport `site.yml`. It owns ingress, storage,
rules, Alertmanager, Telegram templates, expected inventory, private views, and
control-plane heartbeat. It self-scrapes its loopback node exporter and owned
systemd units so its CPU, memory, disk, inode, clock, network, process, and
source health use the same node rules as the VPN fleet.

`observability_deadman` runs in a different host/provider/power/network failure
domain and owns only heartbeat validation and a secondary Telegram route. It
receives no fleet credentials or metrics. Its loopback collector publishes a
bounded signed resource/unit/source summary inside the reverse-heartbeat
contract; the control plane validates and maps that summary into expected
inventory without granting the dead-man a general remote-write identity.

### 2. Prometheus server and Agent Mode; Alertmanager is authoritative

Use an exactly pinned Prometheus release in Agent Mode on each monitored node,
the same pinned release in server mode on the control plane with the remote
write receiver enabled, and an exactly pinned Alertmanager release. Verify
archive checksums and install through the repository's shared verified-release
idiom after the active runtime-pattern consolidation lane has landed or released
the relevant files. Do not install `latest`, pipe installers into root, or rely
on an unpinned container tag.

Prometheus Agent retains a bounded WAL when central ingestion is temporarily
unavailable. The node publishes sender queue/error/drop metrics locally. The
control plane uses bounded time and size retention. Alertmanager owns routing,
grouping, inhibition, finite reminders, silences, retries, and resolved delivery.

During migration, existing ntfy/Pushover remains one explicitly time-bounded
fallback. After central firing/recovery and dead-man proof, remove direct
delivery code, secret fields, tests, and schedules rather than maintain two
permanent paging implementations. Watchdog continues local recovery and emits
state only.

### 3. Public exposure is limited to authenticated write-only ingestion

The initial design does not depend on the still-active restricted management
network change. A hardened ingress proxy listens on the control-plane public
ingestion port and exposes only a node-specific remote-write path. It terminates
TLS, requires a repository-owned CA and unique client certificate per node,
maps the certificate subject to exactly one technical node path, applies request
size/concurrency/rate limits, rewrites only that path to Prometheus's loopback
receiver, and rejects all other methods and paths before forwarding a body.

Prometheus, Alertmanager, their metrics/debug/reload/query APIs, and private
status views stay on loopback or an approved restricted management address and
are absent from the public listener manifest. Public ingress is represented as
a technical listener in Terraform/inventory/firewall contracts and is not an
admin panel. Access logs are disabled or contain only bounded technical
credential/path/result fields; request bodies, auth headers, subjects with
secret values, and query strings are never logged.

Per-node configuration sets immutable technical `environment` and `node_id`
external label. mTLS prevents one credential from using another node's path,
but the reverse proxy intentionally does not decode or rewrite Remote Write
protobuf. The managed sender and node root are the payload-integrity trust
boundary; sender-side metric/label/cardinality validation happens before remote
write. Root compromise can forge that node's payload, including labels; an
untrusted validating ingestion gateway is outside this change and the residual
risk is explicit. Central expected-inventory/source checks bound practical
effect and credential revocation stops later submissions.

### 4. Expected inventory makes disappearance observable

A deterministic repository-generated `vpn_observability_expected_target`
series lists every enabled node, required component, sentinel, policy, and
profile. It derives from the explicit rendered inventory and deployment
profiles, not from currently arriving series. A disabled/retired target is
changed in expected inventory through a reviewed deployment; it cannot become
healthy merely by vanishing from scrape or remote write.

Rules join fresh producer evidence against expected inventory. `absent()` alone
is insufficient because it cannot name a target that never appeared or was
accidentally removed from sender configuration. Expected inventory, deployed
manifest evidence, and current samples have separate generation/source fields.

### 5. One metric contract and adapter boundary

Add a versioned metric manifest declaring every accepted family, owner, type,
unit, stable labels, maximum series, cadence, staleness, and allowed alert use.
Agent write relabeling drops all unlisted families/labels. Repository tests feed
a secret-shaped corpus and high-cardinality inputs through adapters, sender
rendering, rules, templates, status output, and logs.

The node adapter atomically writes bounded textfiles for:

- watchdog last run/result, consecutive failures, bounded restart counters,
  rate-limit state, and recovery result;
- backup local/remote source category and allowed timestamps from canonical
  markers, never snapshot ID or restic output;
- node manifest schema/source/deployable-digest match state and enabled
  technical capabilities, without changing schema 2 or copying endpoints;
- producer last-success/error/input-progress where current producers lack a
  dead-detector signal.

Adapters treat missing, malformed, future-dated, unsupported-version, and stale
input as explicit unknown/error metrics. They do not call restic, watchdog,
Ansible, provider APIs, probes, or service validators. Existing producer owners
remain responsible for atomic source artifacts and their semantics.

The backup role therefore gains a producer-owned, atomically replaced,
versioned status artifact for local backup, optional remote-copy, and integrity
attempt/result timestamps. The isolated restore workflow remains the owner of
its own source/completion artifact. The observability adapter only validates,
redacts, and exports those artifacts; it cannot infer success from timers,
repository configuration, or process exit state that was not durably published.

### 6. Protocol liveness is adapted, never recalculated

Run the existing canonical evaluator on the always-on control plane using its
approved sentinel configuration and schedule. Serialize access with its existing
lock. Convert only its redacted persisted result into an atomic metric set:

- one-hot evaluator/run state and timestamp;
- one-hot policy/sentinel/profile/variant verdict and evidence timestamp;
- evaluator-provided degraded/failure/quorum/rotation-candidate result;
- controller revision, runner generation/runtime compatibility booleans, not
  hashes of credentials or endpoint material.

The adapter never creates a second quorum engine. PromQL alerts on the canonical
one-hot status and freshness. `blocked` remains valid only with fresh direct
control; any endpoint variant keeps a logical profile alive; a sentinel fails
only when all required profiles are blocked; unknown/error/stale inhibits outage
and rotation. Automatic promotion remains OTP/operator-gated and outside alerting.

The active fleet-observation change owns the evaluator, installer, schema,
scripts, Makefile seam, and liveness documentation until it lands. Integration
with those shared files is serialized; this change consumes its published
result rather than forking it.

### 7. Default alert policy

Thresholds live in validated configuration and may be tightened per technical
profile without template edits. The initial defaults are:

| Signal | Default condition | Severity |
|---|---|---|
| expected node heartbeat missing | 5 minutes | critical |
| agent live, node_exporter unavailable | 3 minutes | critical |
| required systemd unit failed | 3 minutes | critical |
| required unit restart loop | 3 restarts / 15 minutes | warning |
| Xray collection failure | 2 minutes | warning |
| Xray collection age | greater than 3 minutes | warning |
| remote-write queue age | greater than 5 minutes | warning |
| remote-write dropped samples | any confirmed increase | critical |
| disk/inodes free | below 10% warning; below 5% critical with hold | warning/critical |
| clock/future evidence | immediate unknown, sustained warning | warning |
| canonical backup age | greater than 36 hours when marker exists | warning |
| offsite restore evidence | greater than 35 days | warning |
| certificate expiry | below 14 days warning; below 3 days critical | warning/critical |
| honeypot/probing events | configurable 60-minute threshold | warning |
| detector timestamp/input | producer cadence exceeded | warning |
| one profile blocked on one vantage | 2 evaluations | warning |
| one sentinel fails below quorum | sustained | warning |
| policy quorum failure | 3 consecutive 2-minute evaluations | critical |
| protocol control/evidence unknown | one evaluation, then hold | warning; never outage |
| control-plane heartbeat | 5 missed pulses | independent critical |

Low-traffic Xray counters never alert solely for being flat or zero. Backup
timer activity never supplies backup/restore success. Source drift compares a
node deployable digest with the centrally expected candidate digest, not with
other nodes that may all be stale.

### 8. Stable incidents, inhibition, and recovery

Alert fingerprints contain only stable allowlisted labels:
`alertname`, `environment`, `node`, `component`, `policy`, `profile`,
`vantage`, and `severity` where applicable. Values, timestamps, counts, errors,
and evidence summaries are annotations. This preserves one incident across
updates and allows firing/resolved delivery to correlate.

Warning and critical thresholds use distinct alert names with fixed severity.
The critical alert inhibits its warning counterpart; both carry the same
bounded `incident_family` annotation for operator correlation. Severity never
mutates inside one alert fingerprint, so each alert has an unambiguous
firing/reminder/resolved lifecycle.

Default Alertmanager routing uses `group_wait: 30s`, `group_interval: 5m`, and
repeat intervals of 1 hour for critical, 6 hours for warning, and 24 hours for
persistent informational/degraded state. Rules use `for` and an explicit
`keep_firing_for` at least as long as the missing-evidence detection window.

Inhibition is exact-label scoped:

- monitoring-control-plane down suppresses derivative pipeline/staleness storms;
- node telemetry missing suppresses service/resource/exporter alerts for that node;
- required service down suppresses its derivative collector alerts;
- protocol evidence unknown suppresses outage conclusions for that vantage;
- policy quorum outage suppresses lower-level profile/vantage noise;
- backup evidence stale does not suppress a confirmed backup run failure;
- Telegram delivery failure never suppresses the source incident.

All `equal` labels must be present on source and target so missing labels cannot
match as empty. A firing series that disappears does not resolve. Resolution
requires fresh authoritative healthy evidence for a recovery stability window;
the corresponding missing/stale incident overlaps long enough to prevent a
false Telegram recovery.

### 9. Telegram is a notification sink, not an authority surface

Alertmanager receives its primary bot token through a systemd
`LoadCredential=` file. The numeric chat ID and optional numeric
`message_thread_id` are validated into a root-readable generated route
configuration because the native
Telegram receiver requires an integer configuration value. None of those values
is emitted in Git, logs, metrics, status, or evidence artifacts. Critical and
warning may route to different Telegram
topics but share stable templates. The bot is not a group administrator and no
callback handler is installed. Telegram cannot create silences, restart,
promote, rotate, deploy, or mutate infrastructure.

Templates render an allowlist of stable aliases, state, start/duration, bounded
evidence class, source generation, and repository runbook path. The selected
parse mode is escaped. Message bytes and alert count are capped; overflow is
sorted deterministically and ends with an omitted count. Raw errors, endpoints,
IPs, SNI/domains, tokens, chat IDs, and credential-derived data cannot enter
labels, annotations, URLs, or logs.

Alertmanager notification metrics and logs establish API attempt/outcome, not
human receipt. Live acceptance separately observes a clearly labelled synthetic
firing/resolved pair in the intended Telegram topic. A Telegram-wide outage is
an explicit residual risk shared by primary and dead-man bots.

### 10. Dead-man verifies the pipeline, not merely the host

Prometheus continuously evaluates a synthetic watchdog rule. Alertmanager must
route it to a loopback receipt-producing canary receiver. The control plane
publishes a short-lived authenticated pulse only
when Prometheus and Alertmanager configurations are loaded/valid, rule
evaluation is current, the canary receiver has freshly observed the watchdog
notification, and the low-frequency primary Telegram canary has a fresh
successful API-level outcome. This detects an invalid token or route before a
real incident, but does not prove human receipt; live acceptance proves Telegram
separately. The pulse contains only schema,
generation, monotonically advancing sequence, issued/expiry time, and health
bits; it is authenticated with dead-man-only material.

The external dead-man rejects replay, invalid authentication, future time,
expired pulses, or sequence rollback and alerts after five missed pulses using a
different bot token and Telegram destination/topic. It emits bounded reminders
and one recovery after fresh stable pulses. Its own last delivery state is
testable locally. It publishes a signed reverse heartbeat to a dedicated
write-only control-plane receiver. The reverse message also carries an
allowlisted bounded summary of dead-man CPU, memory, disk, inode, clock,
network, required-unit, collector, and deployed-source state; raw samples and
diagnostics are rejected. Missing reverse pulses or unhealthy fresh summaries
alert through the primary route. Low-frequency, clearly labelled primary- and
secondary-route canaries prove API-level reachability of each configured
Telegram destination before an incident; canaries are rate-bounded and visually
distinct from incidents. Staging explicitly stops the dead-man to exercise both
signals. It has no Prometheus query, fleet SSH, VPN, provider, or primary
Telegram credentials. Correlated control-plane/dead-man or Telegram-platform
failure remains observable only from retained local state and is a declared
residual risk.

### 11. Silences and maintenance are finite

Silences are created only through a narrow authenticated enforcement gateway on
the private management path. The gateway requires owner, reason, exact
stable-label matchers, start, and finite expiry under a configured maximum TTL,
then calls Alertmanager with a constrained service credential. Operators and
public clients have no direct writable Alertmanager API. Broad regex-only,
indefinite, unknown-label, and over-TTL silences fail before submission.
Maintenance suppresses notification only; metrics,
verdicts, incident starts, and health remain unchanged. Silence expiry resumes
the same incident without inventing recovery. Create/delete/expiry audit records
are retained without credentials.

The gateway uses the existing alert label `node`; producer `node_id` remains a
metric/identity field and is not a second silence matcher alias. Every scope
requires the configured exact `environment` and at least one exact `node` or
`policy`. The default maximum TTL is 14,400 seconds and is explicitly bounded
by deployment policy. An authenticated token determines the owner; a supplied
owner field is rejected. Reasons are bounded technical slugs, not free text.

The fixed loopback gateway is `127.0.0.1:19094`, under a separate service UID.
Alertmanager remains at `127.0.0.1:9093` with dedicated mutually authenticated
TLS (including IP SAN verification). Only the gateway owns its backend client
key. Prometheus uses a separate sender bearer token for alert ingestion,
readiness and metrics; operator tokens authorize maintenance and explicit
staging drills. Direct Alertmanager writes and raw silence API forwarding are
unavailable. This gateway is mandatory when control-plane alerting is enabled.
All these authorities remain separate from telemetry ingestion and Telegram.

The canonical operator surface reads the selected owner's fixed root-owned
mode-0600 token through strict SSH, never through local argv or environment.
`observability-silence-create` forwards a bounded private JSON document with
schema_version, reason, starts_at, ends_at and exact matchers. The gateway's
POST `/v1/silences` returns only a UUID; DELETE `/v1/silences/<UUID>` requires
the creating owner. Responses are bounded and validated before categorical
operator output. Create/delete operations are explicit confirmations; neither
runs Ansible nor changes source health. Native Alertmanager expiry remains
authoritative even if gateway audit bookkeeping is temporarily unavailable.

### 12. Generation-based publication and rollback

Agent and control-plane configuration are rendered into private immutable
generation directories. Before activation, run version/config/rule/template,
metric-contract, topology, listener, TLS, and secret-structure validators.
Activation changes one `current` symlink and reloads/restarts the owned unit.
Readiness must prove the complete generation; failure restores the previous
symlink and confirms its readiness. No partial mix of rules, templates,
expected inventory, or Telegram routes is allowed.

Rollback never deletes TSDB, Alertmanager state, SOPS source, historical
evidence, or another role's artifacts. Removing those is a separate destructive
operation. Agent disable removes only agent-owned units/config/credentials and
preserves loopback node_exporter and watchdog. Credential rotations retain the
old credential until the new path is live; failure restores the old authority.
Paging rollback restores exactly one authoritative route and removes duplicate
schedules from the failed candidate.

## Contracts and ownership

### Terraform and inventory

- Reuse provider roots and canonical outputs. Add explicit technical cohorts
  `vpn-observability-control` and `vpn-observability-deadman`; provider/region
  selection remains operator input and is never encoded in slugs.
- `scripts/render-inventory.sh` owns deterministic control/dead-man groups and
  expected technical node identities. `vpn_service_address` remains separate
  from management and ingestion addresses.
- The control-plane public write-only listener joins the Terraform listener and
  firewall contract. All query/admin ports are forbidden from that manifest.
- Live provisioning is separately authorized; source work and plan tests do not
  create provider resources.

### Ansible

- New `ansible/roles/observability_agent/`: adapter, metric manifest, pinned
  Prometheus Agent, WAL, remote-write config, sender credential, hardening,
  enable/disable convergence, Molecule, and three-section `CLAUDE.md`.
- New `ansible/roles/observability_control_plane/`: ingress proxy, pinned
  Prometheus server, expected inventory, TSDB, rules/tests, Alertmanager,
  Telegram files/templates/routes, private status views, generation/rollback,
  loopback self-health, heartbeat, Molecule, and `CLAUDE.md`.
- New `ansible/roles/observability_deadman/`: pulse verifier, secondary Telegram
  delivery, bounded reverse-health summary, state/rate limits, hardening,
  Molecule, and `CLAUDE.md`.
- `site.yml` applies `observability_agent` after `node_manifest`; separate
  `observability-control-plane.yml` and `observability-deadman.yml` preserve
  one-playbook-per-intent.
- Modify monitoring/watchdog only at their owned seams: monitoring stays
  loopback/textfile owner; watchdog gains bounded machine-readable state and
  later loses direct notification. Backup/honeypot/node_manifest keep their
  current semantic owners; adapters read their outputs.
- Every new systemd unit follows the repository hardening floor, bounded
  timeouts/resource limits, least-privilege users, explicit read/write paths,
  no ambient credentials, and idempotent enable/disable behavior.

### Scripts and operator surface

- Add a bounded adapter and expected-inventory generator rather than parse
  Prometheus exposition in shell.
- Add `observability-render`, `observability-validate`,
  `observability-status` (read-only), scoped deploy goals, explicit Telegram and
  dead-man tests, staging-only failure drills, credential rotation, rollback,
  and removal commands.
- Existing `protocol-liveness*` remains authoritative. Add an adapter at its
  published result boundary; serialize shared Makefile/schema/docs edits with
  `TST-1787850553468536`.
- No new `vpnd` public subcommand is required. A later CLI wrapper can consume
  the Make/operator contract without changing observability semantics.

### Secrets and configuration

- Break `watchdog_secrets` into probe/canary-only material after migration.
- Add `observability_secrets` for server TLS, receiver trust, exact per-node
  sender credentials, primary Telegram bot/chat/topic routing, and private UI
  access if used.
- Add separately scoped `observability_deadman_secrets` for pulse
  authentication and secondary bot/chat/topic routing. It never reaches VPN
  nodes or the control plane beyond pulse publication material.
- Update schema, example, coverage, sample fixtures, SOPS round-trip, duplicate
  credential rejection, and runtime modes. Prefer systemd credentials when the
  pinned host versions support the required contract; the supported systemd
  baseline MUST provide `LoadCredential=` and deployment fails closed when it
  does not. Alertmanager, agent, ingress and dead-man read only their own
  credential-directory entries. There is no root-owned-file fallback and no
  reason to run these daemons as root. Never pass credentials through argv, general environment,
  inventory, Terraform state, reports, or diffs.
- Version metric manifest, alert policy, topology, and status/evidence schemas.
  Reject unknown versions; do not add a silent compatibility parser.

### Documentation

- Add a central observability architecture/operator guide, metric catalog,
  alert catalog, Telegram onboarding/rotation guide, private access guide,
  staging drill runbook, incident runbook mappings, migration/cutover/rollback,
  storage/retention, and proof-boundary documentation.
- Update architecture, quickstart, testing, secrets, deployment status, role
  tiering, incident and rollback docs without hand-editing changelog.
- Repository documentation uses technical aliases and contains no live
  endpoint, provider credential, chat ID, bot token, or external knowledge-store
  reference.

### Serialized active-change lanes

- `tst-1787850553468536-fleet-observation` owns protocol-liveness scripts,
  report/schema, Makefile seam, passive inspector, backup evidence, and their
  docs until integrated. Consume its published result and serialize edits.
- `tst-1786299293097217-complete-recurring-amneziawg-live-acceptance` owns AWG
  recurring scheduling/evidence; observability alerts on its result only.
- `vpd-1787497252303967-vpnd-probe-matrix-robust-evidence` owns probe-matrix
  schema/version semantics; do not accept that output without a versioned
  adapter and do not call it canonical liveness.
- `ans-1787497148207353-runtime-pattern-consolidation` owns shared install,
  unit-hardening, group_vars/listener, and watchdog template lanes. Rebase after
  or explicitly serialize the shared files.
- `tst-1787497001212692-verification-truthfulness` owns verify/full-stack and
  testing-document lanes; preserve its fixture/staging/live distinctions.
- `sec-1787916931540401-restricted-admin-network-rollout` owns management path,
  firewall/inventory/secrets rollout. Initial public write-only mTLS ingestion
  avoids a hidden dependency; private query access integrates only after its
  contract is available.
- Active denylist, backup hardening, and secrets-perimeter changes share
  firewall/group_vars/systemd/secrets files and must integrate sequentially.

### Validation and evidence

- Local: schema/render/secret/redaction/cardinality tests, adapter state tables,
  atomic generation/rollback tests, Prometheus rule/config tests, Alertmanager
  config/template tests, expected-inventory/absent-series tests, static
  hardening/listener checks, and diff checks.
- Hosted Linux: separate agent/control/dead-man Molecule convergence,
  idempotence, disable, failure, mTLS rejection, retry, bounded-message, sandbox,
  and two-host remote-write integration; exact candidate SHA only.
- Full repository: targeted tests first, `make validate`, `make ci-fast`,
  affected Molecule roles, full-stack/syntax/schema/security gates under the
  repository heavy-build policy.
- Dry-run: exact staging hosts and rendered candidate only; not deployment,
  ingestion, notification, or client proof.
- Staging: controlled service/exporter/node/remote-write/protocol/control/deadman
  failures, recovery, grouping/inhibition/silence, credential rotation, invalid
  reload, WAL recovery/loss, and rollback. Never alter production routes or
  firewall to simulate failure.
- Live: exact-source control-plane/agent generations; a central query for every
  expected node; two-vantage authenticated traffic for all required profiles;
  visibly observed primary Telegram firing/resolved and secondary dead-man
  loss/recovery; rotation and rollback results.
- Artifact: exact source SHA, installed generation/config/rule/metric-manifest
  digests, redacted expected inventory and rule/route inventory. Queued work,
  fixtures, API 2xx, dashboards, timers, one vantage, push, or deployment do not
  substitute for the named boundary.

## Risks / Trade-offs

- One control plane remains a TSDB/rule-evaluation SPOF → dead-man makes the
  loss visible; HA is a future capability, not an implicit completeness claim.
- Primary and dead-man Telegram routes share the Telegram API → two credentials
  do not eliminate a platform-wide outage; retain local state and expose the
  delivery gap.
- The dead-man and control plane can fail correlatively despite reverse pulses
  and canaries → place them in distinct failure domains and retain local delivery
  state; do not claim two hosts eliminate a platform-wide or operator-wide loss.
- A public ingestion endpoint adds a fingerprinted surface → expose only
  write-only mTLS, bind credentials to paths, bound requests, isolate backend
  APIs, and test the public listener denylist.
- Remote-write outage can exceed the bounded WAL and lose samples → alert on
  queue age/drop and preserve missing evidence as unknown, never recovery.
- Root compromise on a sender can forge its own payload → unique identity/path,
  allowlists, expected inventory, source evidence, and revocation contain future
  access but do not cryptographically validate the `node_id` inside every sample.
- Sentinels may fail correlatively → require distinct technical path signatures
  and report actual vantage; two labels alone are not independence proof.
- Clock skew can invalidate otherwise correct evidence → export synchronization
  state and classify future timestamps unknown.
- Telegram and metrics reveal limited technical topology → bounded aliases and
  private chats reduce but do not remove this disclosure.
- No raw log forwarding improves privacy but slows diagnosis → alerts point to
  local runbooks and scoped on-host inspection.
- Local watchdog may repair a brief failure before central `for` → export restart
  and recovery counters so the event remains observable without paging every
  transient.
- TSDB is intentionally not a durable accounting ledger → retain configuration
  and incident evidence separately; historical metric loss is not current health.
- Optional Grafana would improve visualization but adds maintenance/security
  surface → defer until separately approved; core monitoring and paging do not
  depend on it.

## Migration Plan

1. Rebase the dedicated implementation worktree onto the integration base and
   resolve/serialize ownership with the active fleet-observation,
   runtime-pattern, verification, restricted-management, firewall, backup, and
   secrets changes. No implementation begins from this planning branch.
2. Tests first: freeze metric/version/redaction/cardinality contracts, expected
   inventory, canonical liveness parity, rule state tables, stable fingerprints,
   stale/absent/no-false-recovery behavior, Telegram escaping/truncation,
   topology/listener/security, and generation rollback.
3. Implement adapters and `observability_agent` behind an explicit disabled
   toggle. Prove local scrape, mTLS rendering, WAL behavior, idempotence, and
   convergent disable without sending production telemetry.
4. Implement the control-plane and dead-man roles/playbooks in source. Validate
   pinned artifacts, ingress isolation, rules/templates, expected inventory,
   private status, heartbeat, secrets, and last-known-good rollback.
5. Provision or select an approved independent staging control host and dead-man
   host only after the owner chooses provider/failure domains and authorizes
   external effects. Create primary and secondary private Telegram bots/chats or
   topics with no admin rights; store credentials through SOPS.
6. Deploy staging control plane in shadow/non-authoritative mode and dead-man
   first. Connect one staging agent. Prove rejection of invalid credentials and
   paths, central arrival, expected-target loss, WAL recovery/loss, synthetic
   Telegram firing/resolved, and control-plane loss/recovery.
7. Run the complete staging fault matrix: exporter/service/node loss, local
   watchdog repair, detector/backup staleness, one profile/vantage degradation,
   full sentinel failure below quorum, quorum failure for three evaluations,
   direct-control unknown, restored profile, missing-series while firing,
   grouping/inhibition, finite silence expiry, invalid reload, credential
   rotation, and rollback.
8. Enable one production canary sender while direct ntfy/Pushover remains the
   bounded authoritative fallback. Compare central and local incident evidence;
   do not claim delivery from counters or Telegram API response alone.
9. Serially enable all expected fleet agents and canonical liveness scheduling.
   Query fresh exact-source metrics for every expected node and execute real
   two-vantage authenticated P0/P1/P2 profile acceptance.
10. After visibly observed primary firing/resolved and secondary dead-man
    firing/recovery, make Alertmanager authoritative and remove direct
    ntfy/Pushover code, secret fields, tests, and duplicate schedules in the same
    reviewed cutover. Re-run all gates and exact-SHA hosted checks.
11. Validate last-known-good rollback and one credential rotation with overlap;
    retain historical storage and old credentials until new authority is proven.
    Record exact local, hosted, staging, live, client, Telegram, and artifact
    evidence separately.
12. If any live prerequisite or proof is absent, leave the portfolio task open
    with source-complete or staging-complete detail. Never archive or close from
    fixtures, dry-run, a push, queued CI, green timers, one vantage, or API 2xx.
