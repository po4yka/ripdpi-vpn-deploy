# Central observability operator surface

This runbook covers the exact-host commands for the centralized observability
agent, control plane, and independent dead-man. It does not authorize a
provider change, production deployment, credential creation, fault injection,
or paging cutover. The control plane and dead-man must already exist in the
generated inventory.

Every command requires an exact inventory alias, an explicit environment and
one component: `agent`, `control-plane`, or `deadman`. Wildcards, groups and
`all` are rejected before SSH or Ansible. The controller uses the inventory's
pinned SSH identity and the supplied `known_hosts`; it snapshots the selected
alias into a private one-host inventory, disables ambient Ansible vars plugins,
and supplies strict SSH options without a local config, proxy or multiplexing.
It never calls `ansible/playbooks/site.yml`. `OBSERVABILITY_ENVIRONMENT` has no
fallback to `ENV`: every Make invocation must supply it explicitly.

## Inputs

Set the non-secret scope once:

```sh
export OBSERVABILITY_INVENTORY="$PWD/ansible/inventory/generated.ini"
export OBSERVABILITY_HOST="control-observer"
export OBSERVABILITY_ENVIRONMENT="staging"
export OBSERVABILITY_COMPONENT="control-plane"
export OBSERVABILITY_KNOWN_HOSTS="$HOME/.ssh/known_hosts"
```

`render`, `validate`, `rotate`, and `rollback` additionally require the
materialized SOPS document and a role-variable file. Both must be same-owner,
non-symlink regular files with mode `0600` in an owner-controlled path:

```sh
export OBSERVABILITY_SECRETS_FILE="/owner/private/path/staging.secrets.yml"
export OBSERVABILITY_VARS="/owner/private/path/control-plane-vars.yml"
```

The vars document must contain the selected role's exact mapping with
`enabled: true`; a disabled or different component is rejected before Ansible.
Use the dedicated `remove` command for disable convergence. `remove` also
requires that same private deployment-vars snapshot, so it disables the actual
configured roots instead of guessing defaults.

The controller rejects enabled `ANSIBLE_DEBUG` or `ANSIBLE_DIFF_ALWAYS` and
sets both false for child processes. It never prints a secrets path, decrypted
value, command output from a journal, process environment, endpoint, or
generation derived from agent credentials.

## Command effects

| Command | Reads | Mutates | Notifies or injects failure |
|---|---|---|---|
| `make observability-render` | private vars/secrets, exact inventory, selected host facts | Ansible check mode only | no |
| `make observability-validate` | private vars/secrets and role syntax | no host contact | no |
| `make observability-status` | fixed systemd properties and loopback readiness on one host | no | no |
| `make observability-drill` | authenticated local gateway on the staging control plane | submits one synthetic firing/resolved pair | **yes: private staging Telegram route** |
| `make observability-silence-create` | private bounded request and named owner credential | finite scoped notification suppression | no synthetic incident |
| `make observability-silence-delete` | silence UUID and named owner credential | removes that owner's silence | existing incident delivery may resume |
| `make observability-rotate` | replacement private vars/secrets | converges only the selected role and host | may restart that role's units |
| `make observability-rollback` | private last-known-good vars/secrets plus a digest-bound rollback manifest | reconverges only the control-plane role and host to its remotely retained previous generation | may restart that role's units; no notification is claimed |
| `make observability-remove` | private deployment vars snapshot | converges `enabled: false` for only the selected role and host | no; control-plane TSDB retention remains intact |

The status output is a bounded JSON object containing only the requested alias,
component, categorical unit states and aggregate readiness. It is passive and needs no locally decrypted secrets. Control-plane readiness
uses the existing remote sender credential without exposing it. `healthy` is local component readiness, not fresh fleet telemetry,
outside-in VPN availability, Telegram receipt, or dead-man independence.

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

## Telegram delivery contract

The primary route is Alertmanager's native Telegram notifier. Both warning and
critical routes use the same HTML-escaped allowlist template, send resolved
notifications and cap a notification at five alerts; configuration validation
refuses values above ten. Omitted alerts are reported through the deterministic
`TruncatedAlerts` count. The route waits 30 seconds before its first group,
regroups after five minutes, and repeats critical incidents after one hour and
warnings after six hours. These bounds limit notification frequency; they do
not shorten or resolve the source incident.

Alertmanager retains its native retry semantics for 429, server and transport
failures. The independent dead-man sender is deliberately smaller: at most two
requests, at most five seconds per request, one bounded retry delay, and a
`Retry-After` delay capped at five seconds. It retries transport errors, 429 and
5xx responses; semantic 4xx rejection stops immediately. Neither sender logs a
token, request body, chat/topic destination or Telegram response body.

API success and notification metrics prove an API-level attempt/outcome only.
For acceptance, record separately observed, clearly labelled firing and
resolved messages in the configured private primary topic and a loss/recovery
pair in the independent secondary topic. Preserve timestamps and the deployed
source/config generations without copying message bodies or destinations into
the repository.

## Storage and retention

The control plane fixes Prometheus retention at 30 days and 20 GB and refuses
enablement unless at least 40 GiB is available before publication. The agent
WAL is bounded to one hour by default. Alertmanager state and the Prometheus
TSDB are runtime data, not a usage ledger; per-user traffic and billing claims
are prohibited.

Control-plane disable removes owned units, ingress and generated configuration
but preserves the TSDB. Agent disable removes its owned WAL and runtime; it
does not remove node_exporter or producer-owned watchdog/backup evidence.
Dead-man disable removes its sender state because stale incident state cannot
be adopted by a later independent deployment. Destructive TSDB removal,
archive export and retention changes require a separate approved action.

## Workflow

Validate syntax, then run the remote check-mode render:

```sh
make observability-validate
make observability-render
```

Inspect one component without materializing secrets:

```sh
make observability-status
```

Rotate credentials only after preparing a complete replacement SOPS document
and matching role vars. The role validates and publishes a content-addressed
generation before activation:

```sh
make observability-rotate
```

The controller's confirmation is deliberate but is not production authority.
Production execution still requires an explicitly approved change window and
the repository's deployment evidence gates.

For rollback, point `OBSERVABILITY_SECRETS_FILE` and `OBSERVABILITY_VARS` at the
retained control-plane material and provide a private `0600` JSON manifest whose
host, component, previous generation and SHA-256 values bind both files. The
controller reads the actual remote `previous.yml` link through the same strict
transport and refuses a missing, divergent, or arbitrary generation. Agent and
dead-man rollback remain unavailable through this operator surface until they
retain an equivalent durable previous-generation link.

```sh
export OBSERVABILITY_ROLLBACK_MANIFEST="/owner/private/path/control-plane-rollback.json"
make observability-rollback
```

Removal is component-scoped and convergent:

```sh
make observability-remove
```

## Staging delivery drill

`make observability-drill` is accepted only for `staging` plus the
`control-plane` component and requires `OBSERVABILITY_SILENCE_OWNER` to name a
configured operator. The token remains in its fixed remote root-owned credential
file; do not provide a token in argv or environment. It sends a clearly labelled synthetic warning with
one stable fingerprint and keeps it firing for more than the fixed 30-second
Alertmanager group wait. Before resolving it, the controller requires a bounded
authenticated loopback gateway observation of that active fingerprint routed to the
exact `telegram-primary` receiver. It performs no
deploy, provider call, service restart, public request, or production fault
injection.

Command success proves only that the local Alertmanager API accepted the pair.
Record the separately observed Telegram firing and resolved messages; API
acceptance is not human receipt. A dead-man loss/recovery drill, service or node
failure injection, credential rotation proof, two-vantage VPN proof and live
rollback remain separate approved staging steps.

### Required staging matrix

Run each row against the exact deployed source and record the categorical
result plus generation digests. Restore normal state after every injected
failure before moving to the next row.

| Row | Controlled action | Required observation | Refusal/rollback check |
|---|---|---|---|
| ingestion | valid node mTLS write, then wrong certificate/path/method/body | valid samples arrive under the expected node; invalid writes are rejected | no public query/admin path and no cross-node identity |
| agent/WAL | interrupt the receiver within the configured WAL window | queue age/error is visible and delivery resumes without an unbounded queue | expiry/drop is explicit; no unauthenticated fallback |
| expected inventory | stop one sender and age one producer artifact | missing target/family and stale evidence fire separately | deletion or unknown input cannot resolve the incident |
| watchdog/backup | publish failed, malformed, future and stale producer outcomes | exact watchdog, backup and restore-readiness alerts fire | timers and configured remotes never substitute for evidence |
| protocol liveness | run REALITY, XHTTP, Hysteria2 and AmneziaWG from two approved distinct vantages | canonical evaluator transitions and central adapter agree | one vantage, self-dial or unknown control cannot claim outage/recovery |
| grouping/inhibition | create node plus derivative failures and backup failure plus stale evidence | stable grouping and only the specified inhibition occur | fingerprints remain stable through updates |
| finite silence | create, expire and delete a narrow staging silence | delivery is suppressed/resumed while source state and incident start remain unchanged | over-TTL, broad, foreign-owner and unknown-label requests fail |
| primary Telegram | exercise firing, reminder, resolved, 429, 5xx and timeout paths | bounded route behavior and API outcome are visible; real firing/resolved messages are observed | source incident survives notification failure; secrets stay absent |
| dead-man | stop pulses/control plane, then restore fresh advancing pulses | secondary firing/reminder/recovery and reverse-health loss/recovery occur | replay, future, expired and unhealthy pulses do not reset the incident |
| credentials | rotate one sender, primary bot and secondary bot authority at a time | replacement works before old authority is revoked | failed rotation restores the prior generation |
| generation | reject an invalid rule/template/config, then activate and roll back a valid candidate | only a complete generation becomes ready | previous service states and the exact last-known-good chain return |

A deterministic HTTP stub may prove retry classification, bounds and
redaction. It is fixture evidence, not real Telegram delivery. Likewise, API
2xx, a green service, local self-dial and a single client vantage do not satisfy
the live rows.

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

## Failure handling

The controller emits only categorical failures. On an Ansible or SSH error,
inspect locally retained operator logs through the normal protected workflow;
do not retry with debug/diff, paste decrypted variables into argv, or replace
the exact role command with `site.yml`. Rollback refuses missing, mutable,
foreign-owned, group-writable or path-shape-invalid generations. Treat that as
an unresolved rollback blocker rather than repairing symlinks by hand.

### Alerting authority recovery boundary

An ordinary activation failure restores the captured credential/configuration
files and previous service states. Failed restoration retains a private snapshot
under `/etc/observability-control-plane/.authority-rollback` and blocks further
publication and disable. Do not delete that snapshot or blindly restart services;
restore the exact recorded authority under an exclusive maintenance window first.
Runtime binary installation and abrupt process/host loss are outside this
configuration rollback guarantee. Check mode inspects and predicts changes without
creating a snapshot, starting services, or performing readiness requests.

## Migration, cutover, and rollback order

Keep existing direct ntfy/Pushover paging authoritative while the central path
is introduced. Use one bounded, recorded overlap window and this order:

1. deploy the staging control plane and independent dead-man with no production
   sender or paging cutover;
2. onboard one canary agent, validate source identity/retention, and run the
   complete staging matrix;
3. onboard the remaining agents serially and require fresh expected-target
   evidence after each node;
4. evaluate central rules in shadow while direct paging remains active, then
   compare stable firing and resolved lifecycles rather than message counts;
5. observe real primary firing/resolved and secondary loss/recovery messages,
   rotate each authority, and prove last-known-good rollback;
6. approve one authoritative cutover, remove legacy delivery schedules and
   credentials, and verify that exactly one route remains.

If any central rule, Telegram delivery, freshness, rotation or rollback proof
fails, stop the migration and leave legacy paging authoritative. Do not run two
permanent paging implementations. Control-plane rollback uses the exact private
manifest and retained `alertmanager-previous.yml` generation described above.
Agent and dead-man activation failures restore their prior captured generation
inside their role transaction; they do not yet expose the operator rollback
command, so a failed live rollback keeps cutover blocked. A failed authority
restore leaves the private recovery snapshot in place and forbids disable or a
new publication until repaired in an exclusive window.

## Evidence boundaries

Record each class separately:

- **source/local:** exact commit and generation digests, targeted tests, rule
  tests, render/schema/security checks and full repository gate;
- **hosted:** exact-head required CI and independent review;
- **dry-run:** exact inventory aliases, clean source and check-mode result; no
  telemetry or notification claim;
- **staging:** the matrix above, including cleanup and rollback, on disposable
  hosts at the deployed source;
- **fleet:** fresh central evidence for every expected node/profile and absence
  of unexpected public listeners;
- **client:** authenticated traffic for all four protocols from two distinct
  approved vantages;
- **Telegram:** human-observed primary firing/resolved and independent
  secondary firing/recovery, distinct from API outcome;
- **cutover:** one authoritative route, legacy schedule/credential removal and
  a successful exact-generation rollback proof.

Queued jobs, fixture stubs, successful API responses, check mode, a healthy
timer or a single vantage may support one evidence class but cannot be promoted
to another. Leave the portfolio item open and name the exact missing class when
staging access, credentials, sentinels, Telegram observation or a change window
is unavailable.
