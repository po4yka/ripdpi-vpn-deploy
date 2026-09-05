# MON-1788008977760206: Deliver centralized observability and Telegram alerting

## Objective

Deliver an independently placed, reproducible monitoring control plane that
receives bounded authenticated telemetry from every managed server, consumes
canonical two-vantage VPN liveness, evaluates tested missing/stale/quorum rules,
and delivers redacted firing/recovery incidents to Telegram with an independent
dead-man. Completion requires exact-source staging, fleet, client, Telegram,
rotation, and rollback evidence; source or fixture completion alone leaves the
task open.

## Ownership

- Primary implementation owns new `ansible/roles/observability_{agent,control_plane,deadman}/`, their playbooks/Molecule/docs, the metric and alert
  contracts, expected-inventory/adapter scripts, control-plane rules/templates,
  scoped operator commands, new tests, task artifacts, integration, and evidence.
- Shared `Makefile`, `ansible/playbooks/site.yml`, `ansible/group_vars/`,
  listener/firewall/inventory contracts, `secrets/`, CI matrices, and common docs
  are serialized under primary; parallel workers receive disjoint role/test
  ownership and do not edit shared files simultaneously.
- `TST-1787850553468536` retains ownership of canonical protocol-liveness,
  passive inspection, report/schema and backup-evidence seams until integrated;
  this change adapts published redacted output and serializes shared edits.
- Runtime-pattern, verification-truthfulness, restricted-management, denylist,
  backup-hardening, recurring-AWG, and secrets-perimeter changes retain their
  documented shared-file lanes. Rebase/integrate them before overlapping edits;
  never copy their unmerged implementations into this change.
- Source implementation has no provider, Telegram, production SSH, deployment,
  service-failure, credential, or destructive-storage authority. Those effects
  occur only in the explicitly approved staging/live execution steps.

## Execution

- [x] MON-1788009822802454 Define versioned metric redaction freshness and expected-inventory contracts with exhaustive state-table tests #feature !high @item:MON-1788008977760206
- [x] MON-1788009838945651 Implement observability secrets topology and inventory contracts with duplicate-identity and public-listener rejection tests #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009822802454
- [x] MON-1788009839512116 Implement hardened observability agent adapters bounded WAL remote write and convergent disable with Molecule coverage #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009838945651
- [x] MON-1788009840041404 Implement write-only authenticated ingestion and bounded Prometheus storage with isolation rollback and integration tests #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009838945651
- [x] MON-1788009840567973 Implement expected-target generation and VPN control-plane dead-man resource service source-drift and pipeline rules with promtool tests #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009840041404
- [x] MON-1788009841087711 Adapt canonical protocol-liveness evidence without recomputing quorum and prove every verdict transition and stale path #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009838945651
- [x] MON-1788010842186450 Publish atomic versioned backup stage outcomes and failure timestamps for observability without changing backup execution semantics #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009838945651
- [x] MON-1788009841599763 Implement watchdog detector and backup freshness metrics while preserving producer ownership and truth boundaries #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788010842186450
- [x] MON-1788009842115523 Implement fixed-severity alert lifecycles grouping inhibition recovery reminders and an enforced finite-silence gateway with rule and API tests #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009840567973 @blocked_by:MON-1788009841087711 @blocked_by:MON-1788009841599763
- [x] MON-1788009842624414 Implement redacted Telegram firing reminder resolved and primary-canary delivery with bounded template timeout backoff and rate tests #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009842115523
- [x] MON-1788009843138508 Implement independent dead-man reverse health heartbeat secondary canary and Telegram lifecycle with replay resource and outage tests #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009842624414
- [x] MON-1788009843647612 Implement private fleet status views and explicit render validate status drill rotate rollback and removal commands #feature @item:MON-1788008977760206 @blocked_by:MON-1788009843138508
- [x] MON-1788009844150923 Deliver operator metric alert Telegram migration retention incident drill and rollback documentation with redaction checks #feature @item:MON-1788008977760206 @blocked_by:MON-1788009843647612
- [ ] MON-1788009844659393 Pass targeted tests full local gates hosted exact-source CI and independent security and correctness review #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009844150923
- [ ] MON-1788009845171889 Deploy staging control plane dead-man and canary agent and complete the controlled failure recovery rotation and rollback matrix #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009844659393
- [ ] MON-1788009845679050 Roll out agents and canonical liveness scheduling serially and prove fresh exact-source metrics for every expected fleet node #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009845171889
- [ ] MON-1788009846182502 Prove two-vantage authenticated profile traffic and observed primary and dead-man Telegram firing and recovery lifecycles #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009845679050
- [ ] MON-1788009846690094 Cut over authoritative paging remove direct legacy delivery and complete final rollback exact-SHA and evidence reconciliation #feature !high @item:MON-1788008977760206 @blocked_by:MON-1788009846182502

## Verification

- Local: tests-first metric/schema/redaction/cardinality and adapter state
  tables; expected inventory and missing-series behavior; canonical liveness
  parity; Prometheus/Alertmanager configuration, rules and templates; stable
  fingerprints, inhibition, silence, no-false-recovery, generation rollback,
  secrets/listener/hardening; targeted suites then `make validate` and
  `make ci-fast` through repository resource gates where applicable.
- Hosted CI: exact candidate SHA, agent/control/dead-man Molecule convergence,
  idempotence, disable/failure, mTLS and write-path rejection, Telegram retry and
  bounds, systemd sandbox, two-host remote-write integration, affected
  full-stack/security gates, and independent review.
- Dry-run: explicit staging targets, clean exact source, rendered topology,
  credentials references and no public admin listener. This is not deployment,
  telemetry arrival, notification, or client proof.
- Staging: the complete documented failure matrix across exporter/service/node,
  remote-write/WAL, detector/backup freshness, protocol vantage/quorum/control,
  missing evidence while firing, grouping/inhibition/silence, invalid reload,
  Telegram failure/recovery, control-plane dead-man, credential rotation, and
  last-known-good rollback without production route/firewall mutation.
- Live/fleet: installed control/dead-man/agent generation matches exact source;
  central queries show fresh evidence for every expected node; no unexpected
  public listeners or stale/unknown required producers remain.
- Client/Telegram: actual authenticated REALITY, XHTTP, Hysteria2 and AmneziaWG
  traffic from at least two approved distinct vantages; visibly observed primary
  firing/resolved and secondary dead-man firing/recovery messages. API 2xx,
  fixtures, one vantage, or local self-dial do not substitute.
- Artifact: candidate/deployed/hosted SHA, generation/config/rule/metric-manifest
  digests, redacted expected inventory, rule-route inventory, timestamps and
  explicit evidence-boundary labels. Preserve blockers instead of marking
  missing provider, credential, staging, client or Telegram proof complete.
