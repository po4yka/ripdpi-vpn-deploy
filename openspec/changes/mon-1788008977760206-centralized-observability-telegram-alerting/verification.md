---
task_id: MON-1788008977760206
change: mon-1788008977760206-centralized-observability-telegram-alerting
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

No execution evidence exists at proposal time. `required` means the named proof
must be observed and recorded against the exact candidate/deployed SHA; it is
not a planning PASS. Update evidence fields and every table row only from actual
runs. Archive is forbidden while any category is `required` or `blocked`.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OBS-TOPOLOGY | MON-1788009838945651 | required topology render, independence validation, listener test, staging placement and exact-source artifact | required |
| REQ-OBS-HOST-CLASS | MON-1788009844659393 | required agent, control-plane and dead-man enabled, idempotent, failure and convergent-disable Molecule plus staged lifecycle | required |
| REQ-OBS-INGEST | MON-1788009840041404 | required TLS, wrong-path, unknown, revoked, plaintext, method, body-limit and backend-isolation tests plus staged remote write | required |
| REQ-OBS-METRICS | MON-1788009822802454 | required metric-manifest schema, allowlist, secret-corpus, cardinality and atomic exposition tests | required |
| REQ-OBS-FRESHNESS | MON-1788009822802454 | required fresh, stale, absent, never-seen, future, malformed, disabled and retired state-table tests with no false recovery | required |
| REQ-OBS-NODE | MON-1788009840567973 | required promtool node, service, resource, source and telemetry-pipeline rule tests for VPN, control-plane and dead-man hosts plus staging failures | required |
| REQ-OBS-VPN | MON-1788009841087711 | required evaluator parity state table and staged/live two-vantage authenticated profile transitions | required |
| REQ-OBS-WATCHDOG | MON-1788009841599763 | required adapter ownership tests and staged bounded local recovery proving service and client alerts remain separate | required |
| REQ-OBS-DETECTORS | MON-1788009841599763 | required producer success/input/staleness/error fixtures and detector-dead inhibition tests | required |
| REQ-OBS-BACKUP | MON-1788010842186450 | required producer-owned atomic marker, attempt/result/source/freshness/malformed/future/local/remote/integrity/restore tests plus staged stale evidence | required |
| REQ-OBS-RULES | MON-1788009842115523 | required promtool fingerprint, pending, keep-firing, inhibition, grouping, reminder, absent and authoritative recovery tests | required |
| REQ-OBS-TELEGRAM | MON-1788009842624414 | required stub retry/rate-limit/timeout/escaping/truncation/redaction and primary-canary tests plus visibly observed live firing/resolved pair | required |
| REQ-OBS-DEADMAN | MON-1788009843138508 | required pulse auth/replay/expiry/canary-receipt, reverse-heartbeat and staged/live control-plane/dead-man loss and stable recovery via separate routes | required |
| REQ-OBS-PRIVATE-UI | MON-1788009843647612 | required private-bind/public-listener rejection, authentication and redacted status-view coverage | required |
| REQ-OBS-MAINTENANCE | MON-1788009842115523 | required enforced-gateway owner/reason/exact-scope/TTL validation, direct-write rejection, expiry-under-outage and no-Telegram-authority tests | required |
| REQ-OBS-RETENTION | MON-1788009840041404 | required time/size/resource-limit render tests and staged reserve alert without destructive cleanup | required |
| REQ-OBS-SECRETS | MON-1788009838945651 | required SOPS schema/coverage/round-trip, duplicate-authority, runtime-mode, rotation and leakage tests | required |
| REQ-OBS-CONFIG | MON-1788009844659393 | required agent, control-plane and dead-man invalid candidate, atomic generation, readiness failure and last-known-good rollback tests | required |
| REQ-OBS-MIGRATION | MON-1788009846690094 | required shadow/canary/overlap/cutover/fallback removal and rollback evidence with exactly one paging authority | required |
| REQ-OBS-OPERATIONS | MON-1788009843647612 | required explicit-scope and side-effect contract tests for render, validate, status, drill, rotate, rollback and remove commands | required |
| REQ-OBS-ACCEPTANCE | MON-1788009846690094 | required reconciled local, exact-SHA hosted, dry-run, staging, live, client, Telegram and artifact evidence with no open substitution | required |

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
