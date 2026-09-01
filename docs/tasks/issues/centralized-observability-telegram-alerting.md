---
id: MON-1788008977760206
title: Deliver centralized observability and Telegram alerting
kind: feature
status: backlog
area: monitoring
priority: high
risk: high
owner: primary
parent: null
blocked_by: [TST-1787850553468536, ANS-1787497148207353]
spec_mode: required
openspec_change: mon-1788008977760206-centralized-observability-telegram-alerting
created: 2026-08-29
updated: 2026-09-01
related_tasks: [SEC-1787916931540401, TST-1787497001212692]
---

## Goal

Every managed server and every required VPN profile has fresh, redacted,
centrally evaluated health evidence. Stable incidents reach private Telegram
topics with bounded reminders and authoritative recovery; loss of the monitoring
plane reaches a separate dead-man route. Local process state, stale/missing
metrics, one vantage, notification counters, and green timers never substitute
for authenticated client traffic or observed delivery.

## Acceptance criteria

- An independent control plane accepts only authenticated node-specific
  write-only telemetry, keeps query/admin surfaces private, enforces bounded
  metric/label/retention contracts, and exposes expected targets for every
  enabled fleet node and profile.
- Hardened agents preserve loopback node_exporter and existing producer
  ownership, export explicit success/freshness/error state, buffer remote write
  within a bounded WAL, and remove only their owned runtime on disable.
- Canonical protocol-liveness remains the sole owner of variant/profile/control/
  sentinel/quorum semantics. Two approved distinct vantages prove real
  REALITY, XHTTP, Hysteria2 and AmneziaWG traffic; unknown/stale evidence cannot
  become outage, rotation, health, or recovery.
- Tested rules cover node/service/resource/source, detectors, backup/restore,
  telemetry pipeline, per-vantage degradation and quorum incidents with stable
  fingerprints, exact inhibition, finite silences, reminders, and no false
  resolution when series disappear.
- Alertmanager sends escaped, bounded, redacted firing/resolved Telegram
  messages using file-backed SOPS material. An independent host/path and bot
  credential deliver monitoring-plane loss/recovery; Telegram cannot mutate
  infrastructure or silence incidents.
- Generation validation and last-known-good rollback cover agents, ingress,
  Prometheus, rules, Alertmanager, templates, expected inventory, credentials,
  and paging cutover without destructive storage cleanup or duplicate routes.
- Tests-first local and hosted exact-SHA gates, full repository validation,
  staging fault/rotation/rollback drills, exact-source fleet metrics, actual
  two-vantage client traffic, visibly observed primary/dead-man Telegram
  lifecycles, and artifact digests are recorded as separate evidence classes.
- Missing provider/failure-domain choice, credentials, live access, staging
  window, client vantage, Telegram receipt, hosted SHA, or rollback proof keeps
  the task open with exact status; fixture/dry-run/push/queued-job evidence does
  not close it.

## Ownership

- Planning and integration: primary in
  `codex/telegram-observability-plan-20260829`; implementation must begin in a
  fresh dedicated worktree rebased on the chosen integration base.
- New agent/control/dead-man roles, metric/rule/Telegram contracts and tests may
  be delegated by disjoint path. Shared Makefile, site/group_vars,
  inventory/listener/firewall, secrets, CI and common documentation are a
  serialized primary lane.
- `TST-1787850553468536` remains authoritative for passive inspection and
  protocol-liveness publication until integration. Active runtime-pattern,
  verification, restricted-management, recurring-AWG, backup, denylist and
  secrets changes keep their existing file ownership; overlapping work is
  rebased/serialized, never overwritten.
- No live provider, server, Telegram, credential, failure injection, cutover or
  storage action is authorized by this planning record alone.

## Current source status

- The exact-host observability operator controller now exposes render,
  validation, passive redacted status, staging synthetic delivery drill,
  credential convergence, last-known-good rollback and component removal.
- Its operator boundary rejects dirty deployable source before any transport,
  requires an explicit environment, snapshots one strict known-host SSH
  transport for Ansible, retains synthetic firing past the fixed group wait
  before receiver evidence and resolution, and fails closed on unbound removal
  or rollback inputs.
- This is source and local-test evidence only. No staging host, private
  Telegram receipt, live credential rotation, rollback, fleet telemetry or
  two-vantage client-path acceptance has been observed, so the feature remains
  open.
