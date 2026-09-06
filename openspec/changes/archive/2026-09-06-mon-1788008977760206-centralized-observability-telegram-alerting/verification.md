---
task_id: MON-1788008977760206
change: mon-1788008977760206-centralized-observability-telegram-alerting
commit_sha: ca5be8c841139ffa3d2a544e64d13b76f57bc694
local: not_applicable
local_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
remote_ci: not_applicable
remote_ci_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
dry_run: not_applicable
dry_run_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
staging: not_applicable
staging_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
live: not_applicable
live_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
client: not_applicable
client_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
artifact: not_applicable
artifact_evidence: "Task dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed."
---

# Verification

`required` means the named proof must be observed and recorded against the
exact candidate/deployed SHA; it is not a planning PASS. The source preparation
evidence below is narrower than the outstanding staging and live matrix. Update evidence fields and every table row only from actual
runs. Archive is forbidden while any category is `required` or `blocked`.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OBS-TOPOLOGY | MON-1788009838945651 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-HOST-CLASS | MON-1788009844659393 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-INGEST | MON-1788009840041404 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-METRICS | MON-1788009822802454 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-FRESHNESS | MON-1788009822802454 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-NODE | MON-1788009840567973 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-VPN | MON-1788009841087711 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-WATCHDOG | MON-1788009841599763 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-DETECTORS | MON-1788009841599763 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-BACKUP | MON-1788010842186450 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-RULES | MON-1788009842115523 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-TELEGRAM | MON-1788009842624414 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-DEADMAN | MON-1788009843138508 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-PRIVATE-UI | MON-1788009843647612 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-MAINTENANCE | MON-1788009842115523 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-RETENTION | MON-1788009840041404 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-SECRETS | MON-1788009838945651 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-CONFIG | MON-1788009844659393 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-MIGRATION | MON-1788009846690094 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-OPERATIONS | MON-1788009843647612 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |
| REQ-OBS-ACCEPTANCE | MON-1788009846690094 | Dropped: Owner explicitly cancelled this task and its outstanding external acceptance on 2026-09-06 and authorized removal from the active portfolio. Unperformed acceptance is cancelled, not passed. | not_applicable |

## Local and hosted test matrix

| ID | Test | Expected result | Boundary |
|---|---|---|---|
| L1 | Prometheus rule state tests for pending, firing, keep-firing and clear | exact alert state and duration | local |
| L2 | absent, never-seen, stale, malformed and future evidence | explicit unknown/stale; never healthy, blocked or resolved | local |
| L3 | current value/count/time changes under stable labels | one unchanged incident fingerprint | local |
| L4 | Telegram HTML/Markdown metacharacters and hostile annotations | escaped allowlisted bounded message | local |
| L5 | repository secret corpus through metrics, templates, status and logs | no secret-shaped value emitted | local |
| L6 | unknown labels and cardinality overflow | family dropped/rejected; collector failure observable | local |
| L7 | malformed evaluator JSON and incompatible schema/runtime | monitoring impaired; never VPN outage | local |
| L8 | all canonical protocol verdict/control/quorum combinations | exact parity with evaluator; no PromQL quorum engine | local |
| C1 | agent Molecule converge and second run | hardened, enabled and idempotent | hosted Linux |
| C2 | agent disable convergence | sender/owned credential removed; loopback node_exporter retained | hosted Linux |
| C3 | ingress plaintext, unknown, revoked and cross-node credential/path | request rejected before storage | hosted Linux |
| C4 | listener/security scan | public write path only; no public admin/exporter UI | hosted Linux |
| C5 | invalid rules, Alertmanager config or template generation | current complete generation remains active | hosted Linux |
| C6 | Telegram stub returns rate limit, server error, timeout, then success | bounded retry/failure metric; no secret logs | hosted Linux |
| C7 | oversized incident group | deterministic truncation and omitted count | hosted Linux |
| C8 | systemd sandbox and filesystem permissions | only declared users, credentials and read/write paths | hosted Linux |
| C9 | two-host sender/receiver integration | authenticated central sample arrival and expected labels | hosted Linux |
| C10 | control-plane converge, self-health, second run, disable and failed readiness | idempotent lifecycle, bounded loopback resource evidence and complete last-known-good generation | hosted Linux |
| C11 | dead-man converge, reverse-health summary, second run, disable and invalid pulse config | idempotent least-privilege lifecycle with bounded resources and no stale sender | hosted Linux |
| C12 | agent invalid candidate generation | current ready generation remains active and credential unchanged | hosted Linux |
| C13 | silence gateway valid and invalid requests plus direct Alertmanager POST | only exact finite policy-valid silence accepted; direct write rejected | hosted Linux |
| C14 | backup producer interruption during marker publication | prior complete marker or new complete marker only; never a partial success | hosted Linux |

## Staging failure matrix

Every drill uses disposable staging targets or supported endpoint overrides. It
must not mutate production routes, firewall, provider resources, credentials,
or live data merely to manufacture evidence.

| ID | Drill | Expected result |
|---|---|---|
| S1 | stop node_exporter while agent remains live | one exporter alert; fresh authoritative recovery |
| S2 | stop a staging node | one node-missing incident; derivative node alerts inhibited |
| S3 | block remote write within WAL window | queue/stale warning, backoff, no false recovery or loss claim |
| S4 | restore remote write within WAL window | samples resume and resolve only after fresh stability |
| S5 | exceed bounded WAL window | explicit dropped/lost-sample critical evidence |
| S6 | fail a service and allow bounded watchdog repair | local recovery recorded; client-path state remains independent |
| S7 | block one profile on one sentinel | degraded warning; no quorum critical |
| S8 | block all profiles on one sentinel | sentinel warning below quorum; no promotion |
| S9 | meet quorum for three two-minute evaluations | one critical policy incident; no automatic mutation |
| S10 | fail direct control | unknown/impaired alert; no blocked/quorum conclusion |
| S11 | recover one required profile | candidate clears; recovery after fresh stability only |
| S12 | remove metrics while an outage is firing | no Telegram resolved; missing-evidence incident overlaps |
| S13 | create multiple derivative failures | grouping/inhibition leaves one root incident |
| S14 | apply and expire a scoped maintenance silence | source state unchanged; same incident resumes, no false recovery |
| S15 | publish invalid control-plane generation | activation refused; last-known-good remains ready |
| S16 | stop Prometheus, Alertmanager and then the control host | independent dead-man firing and bounded reminders |
| S17 | restore the control plane | dead-man recovery only after fresh valid pulses |
| S18 | rotate one node sender identity | bounded overlap succeeds; old identity rejected after proof |
| S19 | fail primary bot-token rotation | prior primary credential and route remain authoritative |
| S20 | roll back central paging generation | exactly one authority and schedule; TSDB/state retained |
| S21 | staging-only resource-series injection for CPU, memory, swap, disk and inodes | each threshold lifecycle and root grouping fires without exhausting the host |
| S22 | inject clock, future evidence, source drift and certificate-expiry states | correct unknown/warning/critical transitions with stable fingerprint |
| S23 | drive detector threshold then stop detector input | security event alert followed by detector-stale inhibition of quiet conclusions |
| S24 | inject canonical backup local, remote, integrity and restore states | each evidence class alerts independently without timer substitution |
| S25 | cross the isolated staging TSDB reserve threshold | reserve alert fires; no destructive cleanup or unrelated data loss |
| S26 | inject restart-loop, network-error and filesystem-error series | expected component/node lifecycle and inhibition without unsafe host damage |
| S27 | stop and restore the dead-man while the control plane stays healthy | primary dead-man-missing firing/recovery and no forged secondary recovery |
| S28 | exercise the low-frequency secondary-route canary in an approved window | operator observes a clearly labelled non-incident canary and local delivery state advances |
| S29 | revoke or replace the staging primary bot credential before its canary | pulse becomes invalid and secondary dead-man alerts without waiting for a fleet incident |

## Live, client, Telegram, and artifact acceptance

| ID | Evidence | Required observation |
|---|---|---|
| V1 | deployed source | installed control/dead-man/agent generation and deployable digest match candidate |
| V2 | fleet telemetry | central query returns fresh expected series for every enabled managed node |
| V3 | public surface | only declared write-only ingestion listener is public; query/admin/exporter ports absent |
| V4 | client traffic | every required REALITY, XHTTP, Hysteria2 and AmneziaWG profile completes authenticated traffic from two approved vantages |
| V5 | primary Telegram | operator visibly observes labelled synthetic or staged firing and resolved messages in intended topic |
| V6 | dead-man Telegram | operator visibly observes independent control-plane loss and stable recovery messages |
| V7 | credential lifecycle | one sender and primary/dead-man notification credential rotation preserves authority then rejects old material |
| V8 | rollback | last-known-good generation restores without duplicate schedules, credential leakage or destructive storage action |
| V9 | hosted SHA | all required hosted checks are green at the exact candidate/deployed SHA |
| V10 | artifacts | redacted generation, config, rule, route, metric-manifest and expected-inventory digests recorded |

## Proof boundaries and prohibited substitutions

- Local config/parser/rule success is not hosted Linux, deployment, central
  ingestion, real client traffic, Telegram receipt, or rollback proof.
- A remote-write HTTP success is not proof that the expected series is queryable
  and fresh; query it centrally.
- Telegram API success is not proof that the intended operator/topic received
  both firing and resolved messages; observe them.
- A dashboard or status command is not paging. A green timer is not backup or
  restore. Local watchdog self-dial is not outside-in availability. One vantage
  is not quorum. A push or queued job is not exact-SHA hosted success.
- Fixtures and stubs prove deterministic behavior only. They cannot close live,
  client, Telegram, or artifact evidence.
- If credentials, approved hosts, failure-domain selection, staging window,
  external vantages, Telegram access, or hosted CI are unavailable, mark the
  exact category `blocked` with evidence and keep the change active.

## Source preparation, 2026-09-04

The final integration combines the published telemetry foundation
`f5b9a208c445b865cbd487d6b226ba94eda94702` with the remaining MON adapters,
alerting, private operator commands, independent dead-man and backup outcome
producer. The final candidate SHA and whole-gate results must be recorded after
commit; targeted preparation runs do not substitute for that gate.

- The foundation main run `33569773572` failed its enabled-agent recovery
  fixture after converge and idempotence. The revised fixture requires the
  sender's transmitted timestamp to cross the observed outage watermark and
  a new authenticated node/path arrival. It no longer mistakes continuously
  queued scrapes for failed recovery. The focused agent-render module passed
  21 tests, including pending-but-drained, below-watermark and no-arrival cases.
- Canonical rendering exposed the missing Alertmanager generation variable
  and incomplete dead-man JSON envelope. Both were fixed without relaxing
  StrictUndefined or JSON validation; all 128 template snapshots were updated
  only for the intentional source additions.
- Dead-man receiver configuration and credentials are startup snapshots.
  Credential, executable, generation-link and unit changes now restart inside
  the activation block, followed by bounded direct-loopback readiness. No
  deferred restart can bypass that block's failure handling or resurrect a
  subsequently disabled role. Enabled and disabled Molecule scenarios are
  required in CI; fixture destinations remain confined to loopback.
- Four optional source identity arguments now preserve explicit empty values in
  the control-plane adapter unit. The real CLI regression proves argument
  parsing succeeds and invalid inventory remains a typed stale failure.
- The client vendors the metric-manifest example byte-for-byte. Its mirror
  update is an integration prerequisite, not evidence of client VPN traffic.

No staging placement, fleet rollout, two-vantage protocol acceptance, human
Telegram receipt, credential rotation on production, paging cutover or live
rollback has been performed by this source integration. Those execution steps
and all corresponding required evidence remain open.

## Finite silence gateway: local native C13, 2026-09-04

The real Darwin arm64 Alertmanager 0.28.1 and the gateway source with SHA256
`8c461d391fd1aa5c8157649171ad0946016c33c6f484197baf67c9ed2dc32ffa`
passed one bounded 15.468-second run. The official archive checksum was
`6ad077f9de99fe96843a68313f19dd2dbc1e8929135293e48bb10824bd6b4df4`;
the verified binary checksum was
`f8a3adfe1793e86faa7a3c19a5c98097f196f2479ff245e3d9411e24c03e5c2d`.

The run observed a firing webhook, a 15-second finite silence, and a second
firing webhook after native expiry with the same alert identity and no resolved
notification. Direct backend access without a client certificate, missing
authentication, sender maintenance, excessive TTL, broad scope and foreign-owner
deletion all refused; creator deletion succeeded. Processes and threads exited,
ports closed, and the private runtime including generated keys was removed.
The redacted result SHA256 is
`03af9762a3bc190419ab24c9ccd1a78ccb0518808524228915ea46cdbecb0655`.

This proves the local gateway/Alertmanager protocol and expiry boundary only.
It does not prove Linux/systemd, staging placement, fleet/VPN traffic or Telegram
receipt. The MON execution step remains open through those required gates.

Independent source review found that failed activation could leave new gateway
credentials with the old Prometheus credential snapshot. The corrected role
captures its fixed authority write-set before publication, restores bytes and
metadata on ordinary Ansible failure, and reloads the previous service snapshots.
Six real-Ansible scenarios with explicit filesystem and HTTP-process service
adapters passed: active rotation/retry, inactive restoration, first-install
cleanup, incomplete restore with retained recovery state, partial active topology
refusal and first-enable failure with a standalone active Prometheus. The helper
passed 22 filesystem/CLI cases, including size limits, unsafe paths and retained
recovery state. These are adapter tests, not native systemd rollback proof.

A later installed-Ansible check-mode regression exposed skipped snapshot capture
followed by parsing empty stdout. A separate read-only inspection path now allows
six observed check-mode scenarios: unchanged and rotated authority, a fresh
namespace, stopped/disabled service activation prediction, and manual-recovery/
unsafe-namespace refusal. Managed bytes, inodes,
modes and service state remained unchanged; no rollback snapshot was created.
Runtime binary installation and abrupt process/host loss are outside the ordinary
authority rollback boundary. Final exact-commit and hosted results are pending.

## Integrated source gate, 2026-09-05

The reviewed exact source candidate
`fe860a0941adfb5993bc6dbc58531779d1aea573` completed the canonical local
`make -j1 check` gate. Pytest reported 3,760 passing tests and three existing
skips in 1,942.52 seconds; all 55 Bats tests, 184 Rust tests, release Clippy,
all four Terraform mock suites, 45 Conftest policies, cloud-init, rendering,
schemas and the remaining `ci-fast` gates passed. The mode-0600 log has SHA256
`3aefbb718c257ca2e2448edb4797655e805dbb75c72c866f4bcc3b5306fbf559`.
The isolated Colima profile stopped successfully; its Docker context and
configuration were unchanged.

The exact-head hosted CI run `33966423515` completed every required job,
including pytest, the agent, control-plane and dead-man normal and failure
Molecule scenarios, full-stack Molecule, Terraform, Bats and Rust. CodeQL run
`33966423427` also succeeded. The final dead-man fixture correction passed 139
focused tests, including 35 pipeline cases under `TMPDIR=/tmp`, and independent
review found no P0-P2 issue. Earlier load-sensitive fixture failures and one
provider-registry setup failure were not credited; they were corrected or
re-run on this exact source.

This evidence-only descendant marks only the source-gate execution step done.
No executable, role, template, contract or infrastructure source changed after
the tested candidate. Staging placement, fleet rollout, two-vantage protocol
traffic, visibly observed Telegram firing/recovery, credential rotation,
paging cutover and live rollback remain required and are not claimed here.
