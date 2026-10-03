# Resource-bounded observability on existing hosts

The active topology is schema 2: one to ten VPN nodes, exactly one also with
`collector` capability, and a typed `uptime-kuma` observer on an independent
existing host. The observer is not a Terraform fleet node. No new server,
volume, paid monitoring account, public DNS or public monitoring listener is
part of this workflow.

The tracked `observability_contract.enabled_environments` still contains only
`staging`; production is not implicitly enabled. Inventory derives scope from
`HOSTS` and rejects mixed enabled/disabled environments before provider access.
Strict secret checks require explicit `--environment` values.

This runbook does not authorize host access, deployment, new credentials,
service interruptions or cutover. Preserve any working old alarm route until
the replacement has positive acceptance. The old dedicated topology and
`OBSERVABILITY_HOST_CLASSES` / `OBSERVABILITY_SENTINELS_JSON` are rejected.
The `deadman` operator component and dedicated host bootstrap are retired.
Old task receipts and retained encrypted credentials do not accept this design.

Rollout remains on hold pending replacement acceptance. The previous Prometheus
Agent 3.14.0 failed to deliver unsent pre-restart samples in the real outage
drill. The approved replacement is vmagent 1.153.0 with a byte-bounded persistent
queue, not a one-hour WAL. Retained files and replay logs do not prove delivery:
require actual historical samples after clean and abrupt restarts, measured
queue overhead, and the unchanged resource and live acceptance gates.

## Current contract and task history

When an older monitoring task or archived proposal leads here, use the
[resource-bounded requirements](../openspec/changes/resource-bounded-observability/specs/operations/resource-bounded-observability/spec.md)
and [design](../openspec/changes/resource-bounded-observability/design.md) in
the active change for the replacement contract. The machine-readable topology is
[schema 2](../contract/observability-topology.schema.json); the tracked environment
allowlist is in [all.yml](../ansible/group_vars/all.yml). This runbook describes
the current operator workflow. Archived specifications describe their source
revision and do not override these inputs.

| Task | Relationship to the current contract | Evidence and next step |
|---|---|---|
| [TST-1787850553468536 — fleet observation](../openspec/changes/archive/2026-09-06-tst-1787850553468536-fleet-observation/proposal.md) | Passive inspection and authenticated external client probes are separate evidence producers, consumed by monitoring. | Keep client-path provenance, freshness and quorum separate from host health; see [evidence boundaries](#metric-and-alert-contracts) and the [historical verification](../openspec/changes/archive/2026-09-06-tst-1787850553468536-fleet-observation/verification.md), which records cancellation (`dropped`), not passed acceptance. |
| [MON-1788008977760206 — centralized observability](../openspec/changes/archive/2026-09-06-mon-1788008977760206-centralized-observability-telegram-alerting/proposal.md) | Historical collection and alerting foundation; its dedicated control-plane/dead-man topology is superseded. | The [historical verification](../openspec/changes/archive/2026-09-06-mon-1788008977760206-centralized-observability-telegram-alerting/verification.md) records cancellation (`dropped`), not passed acceptance. Prior source/CI results do not establish replacement host admission or live acceptance. |
| [MON-1790650904289505 — dedicated staging acceptance](tasks/issues/staging-observability-telegram-acceptance.md) | Open earlier work whose three-host deployment intent is replaced. Retained resources still use [guarded cleanup](#retained-dedicated-staging-cleanup-only). | Its outstanding checks remain outstanding; do not resume retired deployment commands or transfer receipts to the replacement topology. |
| [MON-1790835036464962 — resource-bounded observability](tasks/issues/resource-bounded-observability.md) | Active replacement owner: existing VPN capacity, private collector and independent Uptime Kuma observer. | Follow its [execution tasks](../openspec/changes/resource-bounded-observability/tasks.md) and [verification](../openspec/changes/resource-bounded-observability/verification.md) for remaining admission, VPN non-regression, real alerts, observer recovery and cutover gates. |

Source/CI success and an archived task are not deployment or human receipt
proof. Apply the [migration and acceptance](#migration-and-acceptance) gates to
the replacement topology; preserve the historical records as historical evidence.

## Inputs and exact-host authority

For an authorized fleet inventory refresh supply one capability and failure
domain per existing node, plus the independent observer's technical identity:

```sh
export OBSERVABILITY_CAPABILITIES="vpn+collector,vpn,vpn"
export OBSERVABILITY_FAILURE_DOMAINS="node-a,node-b,node-c"
export OBSERVABILITY_OBSERVER_ALIAS="observer-a"
export OBSERVABILITY_OBSERVER_DOMAIN="observer-a"
```

Every fleet host remains in `vpn`; the collector additionally has membership
in `vpn-observability-control`, without redefining its SSH identity. The
observer uses a separately maintained exact-host inventory section
`[observability-kuma]`, `observability_observer_kind=uptime-kuma`, an explicit
environment, and the same topology binding. Do not import VPN baseline or
firewall roles onto the observer. Observer alias and failure domain must not
equal any fleet identity; actual host/network independence still needs admission.

Select `agent`, `control-plane`, or `kuma`:

```sh
export OBSERVABILITY_INVENTORY="/owner/private/path/inventory.ini"
export OBSERVABILITY_HOST="node-a"
export OBSERVABILITY_ENVIRONMENT="staging"
export OBSERVABILITY_COMPONENT="control-plane"
export OBSERVABILITY_KNOWN_HOSTS="/owner/private/path/known_hosts"
export OBSERVABILITY_SECRETS_FILE="/owner/private/path/runtime.secrets.yml"
export OBSERVABILITY_VARS="/owner/private/path/component-vars.yml"
```

Private vars and materialized SOPS inputs must be same-owner, mode-0600 regular
files below owner-controlled non-symlink paths. The vars file contains the
complete selected role mapping with `enabled: true`, plus its producer
configuration. Defaults describe the current contract; they are deliberately
inert, not a ready deployment. Pin the real vmagent, Prometheus and Alertmanager
archives and digests independently. Use distinct sender certificates and one
Kuma token per monitor.
`observability_kuma_secrets` holds observer TLS, N+2 monitor bindings, a distinct
secondary Telegram credential, and the existing backup recipient.

The controller binds capabilities, provider/environment and source revision to
the canonical topology. It isolates one literal host and disables ambient
Ansible discovery, SSH configuration/proxies/multiplexing, debug and diff.
It never runs `site.yml` or prints secret values or rendered secret content.

## Command effects

| Command | Effect and authority |
|---|---|
| `make observability-render` | In-memory local template render; no SSH or host facts, no rendered secrets on stdout. Host admission remains unverified. |
| `make observability-validate` | Ansible syntax validation; no host contact. |
| `make observability-check` | Explicit authorized host access using Ansible check mode; not runtime acceptance. |
| `make observability-status` | Read-only exact-host service/readiness inspection; not client or notification proof. |
| `make observability-deploy` | Initial selected-role installation; refuses an existing primary unit. |
| `make observability-rotate` | Authorized selected-role convergence with replacement private inputs. |
| `make observability-rollback` | Collector only: exact retained generation and digest-bound previous vars/secrets. |
| `make observability-remove` | Disable only the selected monitoring component using its private deployment snapshot; retain data and secrets. |
| `make observability-drill` | Explicit staging notification injection; requires human observation separately. |
| `make observability-silence-create` / `delete` | Finite scoped suppression through the authenticated gateway. |
| `make observability-pki-prepare` | Explicit local generation of new private IP-SAN PKI, encrypted to the approved age recipient. No host or notification access. |

The CLI check verb additionally requires `--confirm-host-access`; Make supplies
it only for the explicitly selected check target. Other lifecycle confirmations
remain mandatory.

## Private PKI preparation

Create a private JSON configuration with exactly `schema_version: 1`,
`collector_address`, `observer_address`, `node_ids` and `recipient`.
Addresses must be distinct literal RFC1918/CGNAT IPv4 addresses, node IDs
must be the exact one-to-ten topology identities, and the recipient must be
the approved existing age public recipient. Configuration and output parent
must be private; output must not exist.

```sh
make observability-pki-prepare \
  OBSERVABILITY_PKI_CONFIG="/owner/private/path/pki-config.json" \
  OBSERVABILITY_PKI_OUTPUT="/owner/private/path/pki.sops.yaml"
```

The encrypted bundle separates `runtime` fields from `authorities`. Merge
only runtime fields into the existing SOPS document; it is a PKI fragment,
not complete runtime credentials. Keep authority keys and CA database state
encrypted on the controller, never deploy them. The collector certificate
uses the collector IP SAN, Kuma uses its own IP SAN and separate CA, and each
node receives a distinct clientAuth identity. Certificates expire within
90 days; plan an approved rotation before expiry. Verify new certificates and
the updated CRL before activation; never disable verification or reuse keys.

## Admission and resource boundaries

The collector's Prometheus, Alertmanager, relay, adapters, gateway and private
ingress share `observability-collector.slice`: MemoryMax 512 MiB, CPUQuota 20%
of one CPU, low IO weight. Ingress uses an isolated master of the already
installed nginx binary in that slice. Its config, PID, credentials and private
9443 listener are separate from the public VPN nginx; unrelated sites and
80/443 listeners are not edited.

The local agent and heartbeat jobs share `observability-agent.slice`: 192 MiB
and 10% of one CPU. The collector host therefore budgets 704 MiB and 30% in
total. Agents use 60-second scrapes, at most 2,000 samples across local jobs,
one vmagent remote-write worker and no fresh-data bypass workers. The persistent
queue setting is 512 MiB; the pinned upstream minimum rounds it to 512 MiB plus
128 bytes. This limits pending data by size, not age or total allocated blocks.
Admission reserves 2 GiB for segment overhead plus the filesystem reserve.
Queue saturation discards oldest unsent blocks and must be reported as delivery
loss. VPN units stay outside both slices.
`ObservabilityAgentDeliveryLoss` reports queue/HTTP discards and native label-limit
rejections after their counters reach the collector. It means incomplete telemetry,
not a VPN failure; a disconnected collector cannot report the event immediately.

The queue is bound to its single receiver before activation. A changed receiver
or populated unbound queue refuses before mutation; do not delete it or the
retired Prometheus WAL automatically. Retained WAL is not replayable by vmagent.
Resolve a receiver migration with explicit offline data-handling authority.
vmagent uses `/opt/observability-vmagent`; the retired Prometheus release root
is retained separately so its public binary link remains usable for rollback.
Status uses vmagent's loopback `/ready`; readiness is not backlog delivery.
Activation and recovery additionally require the managed process to own the
loopback listener, with unchanged process identity before and after HTTP
readiness. A successful response from another process cannot accept a cutover.

Before mutation require the configured private address locally, at least
1 GiB MemAvailable, and free filesystem space for 2 GiB monitoring data plus
max(5 GiB, 20% filesystem size) reserve and measured burst/stop headroom.
Blocks retain at most seven days/1 GiB; this is not a total filesystem quota.
The total data high-water mark is 2 GiB. The five-second reserve guard latches
receiver/ingress off on pressure; its watchdog also bounds a hung guard.
Headroom must exceed twice measured peak write rate times the watchdog plus
measured shutdown bound. On a shared filesystem, admission counts both the
collector's 2 GiB and the sender's 2 GiB allowances; the reserve guard also
protects the sender's remaining allowance. A synthetic value is not a measured
admission result.
After pressure, inspect the filesystem and perform explicit recovery; restarting
a receiver must not bypass the latch.

Admit Kuma only on the approved independent host with existing Docker, nginx,
age, private connectivity and separate backup storage. It needs 768 MiB
MemAvailable, 3 GiB data allowance plus the same host reserve. Its pinned
rootless container is capped at 512 MiB and 0.25 CPU; no Docker socket,
privileged mode, public port or new runtime installation is allowed.

Failed resource or load tests stop deployment. Do not automatically increase
limits, resize hosts, install missing infrastructure, or purchase capacity.

## Metric and alert contracts

The authoritative family allowlist is
`contract/observability-metric-manifest.example.json`; the expected-node/profile
set is `contract/observability-expected-inventory.example.json`. Treat those as
versioned contracts, not examples to extend ad hoc on a host. A new family,
label, state, or cardinality bound requires a reviewed source change and its
schema/redaction tests. Never forward journals, request destinations, peer
addresses, SNI values, client identity, user traffic, or credential-derived
values as metrics or annotations.

| Contract group | Owned evidence | Truth boundary |
|---|---|---|
| `vpn_observability_adapter_*` and `vpn_observability_node_manifest_identity` | adapter completion and deployed source identity | local collection and identity comparison only |
| `vpn_watchdog_*` | watchdog run, freshness, result, restart/rate limit and recovery state | local supervision; never outside-in client-path recovery |
| `vpn_backup_*` | producer-published stage and restore timestamps/results | no inference from a timer, configured remote, repository ID or process state |
| `vpn_observability_expected_target` | reviewed expected inventory | desired coverage, independent of currently arriving series |
| `vpn_observability_evidence_state` | freshness/source/pipeline and canonical liveness adaptation | one-hot bounded state; stale, missing and unknown never become healthy |

The checked alert catalog is rendered from
`observability-alert-rules.yml.j2` and
`observability-expected-target-rules.yml.j2`. It covers watchdog evidence and
unresolved recovery, backup freshness/stage failure/restore readiness, the
synthetic pipeline watchdog, required-family or expected-target absence,
target staleness, source identity mismatch, and control-plane resource/pipeline
health. Generated required-family alert names bind the exact expected target,
role and family. A missing series stays an absence incident; it is not a
resolved notification. `ObservabilityBackupStageFailed` alone inhibits its
derivative stale-evidence alert for the same node and component.

Before deployment, validate the manifest, expected inventory, rendered rules
and templates together. A Prometheus query result proves central evaluation;
it does not prove a sender captured current input or that Telegram delivered a
message.

## Independent Kuma monitoring and Telegram evidence

Kuma is pinned to stable 2.5.5 architecture-specific manifests in role defaults.
Its UI is host-loopback only on port 13001, reached through an already approved
authenticated operator path. The private HTTPS 9444 vhost permits exact enrolled
source addresses and GET push paths only: no UI, setup, websocket administration,
metrics, status pages or query parameters. TLS verifies the private IP SAN.
Token-bearing access/error/application logging is disabled.

Use upstream authenticated UI setup and monitor configuration; do not edit
SQLite or add an unapproved provisioning client. Create N node monitors,
one pipeline monitor and one delivery monitor (five initially, twelve maximum).
Set distinct cryptographically random 20–128-character URL-safe tokens using
the authenticated monitor editor; do not keep a shorter autogenerated default.
Save tokens under their exact `node_id`/`kind` SOPS bindings.
Configure native Telegram with a separate secondary bot, not the primary token.
Missing authority to issue that token is a deployment blocker.

Node/pipeline producers run every 60 seconds. Configure their Kuma interval
and retry interval to 120 seconds, retries zero; observe the <=180-second down
bound at different scheduler phases. Delivery runs every five minutes; configure
540-second interval/retry interval, retries zero, and observe <=600 seconds.
Disable upside-down/maintenance for acceptance. Repeat notifications use failed
check counts (three), not seconds, and require observed pinned-runtime evidence.
Never-started monitors are part of acceptance.

A node checks its own declared local services and sends directly to Kuma.
The collector never synthesizes another node's heartbeat. Pipeline success
requires fresh expected node scrapes, Alertmanager visibility, successful recent
rule evaluation and a newly consumed synthetic rule-to-relay receipt.
Delivery success requires a real relay edit with advancing sequence and a real
send receipt younger than 26 hours; a new silent send occurs daily. An edit is
not proof of the send path. A send-only failure can take 26 hours plus the
delivery detection window to appear. API acceptance is not human receipt.

Push requests load tokens through systemd credentials, verify TLS, use bounded
timeouts, disable redirects/proxies and require exactly the expected JSON
acknowledgement. Stale receipts, missing targets and failed local checks withhold
success. Token possession can forge freshness; private ingress and rotation
reduce but do not eliminate that risk.

The surviving primary route reports observer/push failure as external coverage
unavailable, not confirmed VPN failure. Healthy process status is not proof of
working alert evaluation or Telegram delivery. Both routes share Telegram; both
observer and collector loss cannot guarantee notification. Shared private-network
loss remains a common-mode dependency. Authenticated external client-path
quorum remains unchanged; missing witnesses remain unknown/stale.

## Backup, restore and upgrades

Protect the live Kuma database as secret material; SOPS does not encrypt it.
Daily quiesced backup captures the whole data directory including WAL state,
encrypts directly with age to separate existing owner-controlled storage and
records the matching image digest and ciphertext checksum. Preserve the
previous database and image before upgrades. Container rollback alone cannot
roll back a database migration.

The restore helper requires an explicitly provisioned systemd age-identity
credential and a selected backup ID. It restores into a new private directory,
rejects traversal/links/special files, and verifies an isolated instance with no
network or published ports. Thus notifications cannot leave the restored
instance. Retain both datasets; do not run original and restored monitors with
outbound access simultaneously. Activate restored data only after exact-host
and credential approval.

## Finite maintenance silences

Alerting requires `observability_control_plane.alerting.silence_gateway.enabled`
and dedicated gateway authorities in `observability_secrets.silence_gateway`.
Bind the existing private role-vars mapping to the SOPS fields instead of
copying credential values. For example, the `alerting.silence_gateway` value in
the complete control-plane vars document can be:

```yaml
silence_gateway: >-
  {{ observability_secrets.silence_gateway | combine({
      'enabled': true, 'listen': '127.0.0.1:19094',
      'environment': 'staging', 'max_ttl_seconds': 14400}) }}
```

The role uses a fixed private configuration root and loopback-only gateway;
Alertmanager's underlying API requires a separate client certificate held only
by the gateway. Sender credentials cannot create or delete silences. A named
operator may delete only silences it created. The default maximum TTL is four
hours, bounded by the configured policy.

Create a mode-0600 JSON request in an owner-controlled directory. Its exact
fields are `schema_version: 1`, a technical-slug `reason`, UTC `starts_at` and
`ends_at`, and `matchers`. Matchers require the configured `environment` and
at least one exact `node` or `policy`; optional allowed stable labels further
narrow the scope. Do not use `node_id`, regex matchers, an owner field, tokens,
free-text diagnostics or an indefinite end time in this file.

```sh
export OBSERVABILITY_SILENCE_OWNER="operator"
export OBSERVABILITY_SILENCE_REQUEST="/owner/private/path/maintenance.json"
make observability-silence-create

# Use the UUID returned by the successful create operation.
export OBSERVABILITY_SILENCE_ID="<returned-uuid>"
make observability-silence-delete
```

These explicit mutation commands use the already-selected exact inventory
host and environment. They do not deploy, alter metrics, reset incident times,
or claim recovery. Alertmanager expires a silence at its finite end even if
the gateway is temporarily down. The private bounded audit retains categorical
creation, expiry and deletion records without bearer tokens. A successful API
response is not the required real alert delivery/expiry staging evidence.

## Migration and acceptance

1. Complete local schema, render, unit, security and full repository gates.
2. With exact-host access permission, measure collector and observer admission,
   verify private connectivity/runtime/backup storage and record matched VPN baselines.
3. With deployment and credential authority, configure the independent observer
   and N+2 real monitors. Verify private UI/ingress separation, actual secondary
   human receipt, persistence and encrypted isolated restore.
4. Deploy the collector and node agents serially on existing hosts. Require
   qualified heartbeats and fresh expected-target metrics after each.
5. Perform explicitly scoped missing-push, collector, observer, stale-receipt,
   revoked/wrong-SAN, token-rotation, storage and recovery drills. Verify primary
   observer-loss alerting and secondary collector-loss alerting separately.
6. Compare three matched baseline/enabled authenticated VPN runs: median
   throughput loss <=5%, p95 latency increase <=10%, no attributable new
   connection failures or VPN restarts. Unresolvable noise is unverified.
7. Request cutover only after real failure/recovery and human acceptance.
   Do not disable or delete working old routes or their secrets automatically.

Collector rollback uses the retained exact generation and digest-bound private
manifest. Agent rollback is reviewed reconvergence; monitoring-only disable
stops its units without touching VPN configuration or deleting retained data.
Kuma rollback requires a matching verified database/image pair. Failed authority
restoration retains its private recovery snapshot and blocks later publication;
do not delete it or blindly restart services.

Keep local source, local disposable runtime, hosted CI, host admission, API
receipts, human notification, and authenticated client evidence separate.
Mock/fixture results never establish resource admission, real scheduler timing,
Telegram delivery, VPN non-regression or live cutover. No step or feature closes
while its named required evidence is missing. The earlier dedicated-staging
task remains separate and open.

## Retained dedicated-staging cleanup only

The old three-provider resources and their private cleanup journal, if any,
remain governed by the existing sealed destructive-action workflow below.
This does not authorize creating dedicated hosts or resuming the retired
deployment/acceptance topology. Do not reinterpret its prior receipts as
acceptance of co-hosted monitoring.

### Guarded provider cleanup

Cleanup is a separate post-evidence transaction. First create a private scope
snapshot from the terminal acceptance journal, review its delete-only plans,
then seal it with a fresh private approval whose scope digest closes the
rollback/retention window. Only the sealed manifest may be passed to the run
target. The guard is fixed to staging UpCloud, Hetzner and Scaleway roots; it
rechecks clean source, account/project, state digest, complete Terraform address
set, provider identities and every reviewed plan before the first delete.
Final success requires independently authenticated 404 absence for every
addressable resource. Do not retire local recovery material until the redacted
receipt says `provider-absence-verified`; a missing approval or partial outcome
keeps it retained.

The destructive approval passed to `seal` has exactly:
`schema_version`, `task_id`, `change`, `snapshot_sha256`, `source_revision`,
`deployable_digest`, `acceptance_journal_sha256`, `scope_sha256`,
`approval_id`, `approved_at`, `expires_at`, and
`rollback_retention_closed: true`. Its hashes are copied from the reviewed
snapshot, never recomputed from hand-entered resource IDs. Use the Make
preparation surfaces in order:

```sh
make observability-staging-cleanup-snapshot \
  OBSERVABILITY_STAGING_CLEANUP_JOURNAL=/owner/private/run/journal.json \
  OBSERVABILITY_STAGING_CLEANUP_SNAPSHOT=/owner/private/run/cleanup-snapshot.json
make observability-staging-cleanup-seal \
  OBSERVABILITY_STAGING_CLEANUP_SNAPSHOT=/owner/private/run/cleanup-snapshot.json \
  OBSERVABILITY_STAGING_CLEANUP_APPROVAL=/owner/private/run/destructive-approval.json \
  OBSERVABILITY_STAGING_CLEANUP_MANIFEST=/owner/private/run/cleanup-manifest.json
make observability-staging-cleanup-validate \
  OBSERVABILITY_STAGING_CLEANUP_MANIFEST=/owner/private/run/cleanup-manifest.json \
  OBSERVABILITY_STAGING_CLEANUP_JOURNAL=/owner/private/run/journal.json
make observability-staging-cleanup \
  OBSERVABILITY_STAGING_CLEANUP_MANIFEST=/owner/private/run/cleanup-manifest.json \
  OBSERVABILITY_STAGING_CLEANUP_JOURNAL=/owner/private/run/journal.json \
  OBSERVABILITY_STAGING_CLEANUP_RECEIPT=/owner/private/run/cleanup-receipt.json
```
