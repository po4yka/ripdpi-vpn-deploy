---
id: MON-1790650904289505
title: Deploy and accept staging observability and Telegram alerting
kind: feature
status: doing
area: monitoring
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: staging-observability-telegram-acceptance
created: 2026-09-29
updated: 2026-09-29
related_tasks: []
---

## Goal

Add the missing exact-host bootstrap and bounded staging-acceptance operator
surfaces, deploy the centralized observability components to a disposable
cross-provider three-host topology, and obtain exact-source evidence for fresh
canary telemetry, primary and independent Telegram alert lifecycles, controlled
failure/recovery, credential rotation, last-known-good rollback, and approved
provider cleanup.

## Acceptance criteria

- Fresh control-plane and dead-man hosts receive the tested repository baseline,
  updates, host-class-aware guest firewall, loopback host monitoring, and source
  manifest through an exact-host non-VPN bootstrap surface.
- Staging-only bounded operator verbs cover fresh metric queries, long critical
  reminder drills, exact service/host faults, restoration, forced primary
  canary, and old-material rejection with redacted receipts.
- UpCloud, Hetzner, and Scaleway have tested identity/state/account-bound
  cleanup manifests covering every Terraform address and separately
  addressable provider resource, complete delete-only plan checks, and
  independent provider-specific absence proof before local capability
  retirement.
- The control plane, independent dead-man, and one VPN canary agent are deployed
  from one exact protected-main revision in distinct declared failure domains,
  with the dead-man on a provider different from the control plane;
  public exposure is limited to authenticated write-only ingestion, the
  authenticated pulse endpoint, reviewed VPN listeners, and source-restricted
  SSH.
- Before provisioning, every selected `staging` provider state is either empty
  or already bound to this task's immutable manifest; any unrelated pre-existing
  state or resource refuses before plan or apply.
- Fresh canary metrics advance centrally, valid writes succeed, and invalid,
  cross-node, revoked, plaintext, query, and administrative requests fail
  without secret or endpoint disclosure.
- Separately authorized control-plane service loss, provider host/network loss,
  dead-man service loss, and primary Telegram authority loss are observed by
  their independent path, meet bounded deadlines, and restore a healthy
  baseline before another row; recovery is never inferred from process state,
  an API response, or stale evidence.
- The owner separately observes labelled primary firing, reminder, and resolved
  messages and independent secondary control-plane-loss, reminder, and stable
  recovery messages in the intended private Telegram destinations.
- One canary sender identity and both Telegram bot authorities rotate serially;
  every replacement works before separately authorized upstream revocation,
  old material is categorically rejected afterward, and no duplicate
  authoritative route remains. A `still-valid` old bot token exits non-success,
  retains recovery material, and blocks rotation and cleanup acceptance.
- An invalid control-plane candidate refuses before mutation and a valid
  candidate is followed by exact digest-bound last-known-good rollback without
  storage loss or duplicate schedules.
- Component removal preserves the control-plane TSDB. Only after evidence is
  complete, the rollback/retention window is closed, and exact destructive-data
  approval is recorded is the complete manifest-bound managed resource set
  destroyed; every separately addressable provider resource is then verified
  absent and operator-local plaintext material retired safely. Hetzner primary
  storage is implicit in the server lifecycle, so server absence proves that
  storage is gone; separately addressable storage is checked independently.
- Redacted verification records exact source and generation digests, category
  outcomes, human observation, cleanup, local gates, and terminal hosted checks
  while explicitly excluding the remaining two-vantage protocol-liveness row,
  fleet-wide rollout, and production paging cutover.
