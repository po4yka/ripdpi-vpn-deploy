# Change: Deploy and accept staging observability and Telegram alerting

Task ID: `MON-1790650904289505`

## Why

The repository already contains the observability agent, control-plane,
independent dead-man, Telegram delivery, rotation, rollback, and removal
capabilities, but their acceptance is limited to source, fixture, and CI
evidence. The current operator surface also cannot prepare a fresh
control-plane or dead-man host with the required baseline and guest firewall,
or execute the live failure matrix with bounded restoration and redacted
receipts. Operators therefore still lack a reproducible live staging proof that
a canary node publishes fresh metrics, the primary and independent notification
paths reach the intended private Telegram destinations, failures recover
without false resolution, credentials can be rotated, and the last-known-good
generation can be restored and removed cleanly.

This component and notification proof is required before fleet-wide rollout or
authoritative paging cutover, but it is not the complete runbook staging matrix:
two-vantage authenticated VPN-profile proof remains a separate task. It must be
performed on disposable staging resources from an exact protected-main
revision and must not be represented as production, fleet, client-path, or
full-matrix acceptance.

## What Changes

- Add an exact-host bootstrap surface for fresh control-plane and dead-man hosts
  that converges the repository baseline, updates, guest firewall, local host
  monitoring, and source manifest before an observability component is allowed
  to deploy.
- Add bounded staging-only operator actions and redacted receipts for central
  metric queries, critical reminder drills, service/host fault injection,
  restoration, Telegram authority-loss detection, and old-material rejection.
- Add identity-bound guarded cleanup for the selected UpCloud, Hetzner, and
  Scaleway staging roots, including a complete Terraform-address and provider
  resource manifest, delete-only plan validation, and independent
  provider-specific absence proof.
- Provision or select disposable staging hosts for the observability control
  plane, independent dead-man, and one canary telemetry agent, with the
  control-plane and dead-man in distinct provider failure domains.
- Deploy the existing observability components from one exact protected-main
  revision while keeping administrative interfaces private and ingestion
  write-only and authenticated.
- Prove fresh exact-source canary metrics and execute the approved controlled
  failure and recovery matrix for the control plane, primary Telegram route,
  and independent dead-man route.
- Rotate one sender identity and both Telegram notification authorities,
  proving replacement material before revocation and rejection of old
  material after revocation.
- Prove exact last-known-good rollback without duplicate schedules, leaked
  credentials, or destructive storage mutation.
- Capture redacted machine-verifiable and human-observed acceptance evidence,
  then remove disposable resources only after a separate destructive-data
  approval closes the rollback/retention window, and verify provider absence.
- Keep fleet-wide agent rollout, two-vantage authenticated VPN-profile proof,
  and production paging cutover explicitly out of scope.

## Capabilities

### New Capabilities

- `operations/staging-observability-acceptance`: Reproducible deployment,
  failure/recovery, Telegram receipt, credential lifecycle, rollback, evidence,
  and cleanup requirements for the disposable observability staging topology.

### Modified Capabilities

- None.

## Impact

- Terraform/provider operations for disposable staging hosts and network
  policy across three existing provider roots; no production infrastructure
  mutation and no weakening of provider-independent dead-man placement.
- Make, Ansible playbook/role ordering, firewall listener reconciliation,
  operator controller, redacted receipt, and focused test changes for the new
  exact-host bootstrap and staging acceptance surfaces.
- Ansible deployment of `observability_agent`,
  `observability_control_plane`, and `observability_deadman` to exact selected
  staging hosts.
- SOPS-managed, least-privilege staging sender, TLS, and Telegram authorities;
  no plaintext secrets in Git, Terraform state, logs, or evidence.
- Existing Make operator targets for render, validate, deploy, status, drill,
  rotate, rollback, and removal, plus new staging-only bounded acceptance verbs.
- Private Telegram chats/topics for primary and secondary human-observed
  delivery, with API success treated only as transport evidence.
- Separately authorized operator/BotFather revocation of staging bot tokens and
  categorical old-token rejection checks that never print token or response
  bodies.
- Redacted task/OpenSpec verification evidence and provider cleanup records.
