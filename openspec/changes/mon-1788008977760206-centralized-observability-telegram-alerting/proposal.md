# Change: Deliver centralized observability and Telegram alerting

Task ID: `MON-1788008977760206`

## Why

The fleet already produces useful loopback-only node, systemd, process, Xray,
watchdog, honeypot, backup, and authenticated client-path evidence, but no
always-on control plane evaluates those signals together or routes a complete,
redacted incident lifecycle to Telegram. Operator-side cron and per-node direct
notifications leave independent gaps: a healthy process can mask an unusable
VPN path, a dead collector can look quiet, one failed vantage can be mistaken
for a fleet outage, and the monitoring host cannot report its own disappearance.

Operators need one durable view of every deployed server and every supported
VPN profile, with explicit provenance and freshness, bounded alert noise,
recovery notifications, and acceptance evidence that distinguishes local
metrics, staged failure injection, external client traffic, and actual Telegram
delivery.

## What Changes

- Add an always-on centralized observability capability that receives a
  redacted, bounded metric set from every managed node without publishing node
  exporters or administrative interfaces to the Internet.
- Evaluate host health, service state, storage pressure, collector freshness,
  backup and restore evidence, source drift, security detectors, and
  authenticated P0/P1/P2 client-path liveness under explicit severity,
  staleness, quorum, inhibition, grouping, reminder, and recovery policies.
- Deliver firing and resolved alert lifecycles to operator-selected private
  Telegram chats or topics through one central Alertmanager credential
  boundary; alert payloads exclude endpoints, credential material, client
  identity, destinations, and raw logs.
- Preserve local systemd/watchdog bounded recovery while keeping it distinct
  from central incident detection and outside-in VPN availability.
- Add an independent dead-man path so loss of the monitoring control plane or
  its Telegram delivery path cannot remain silently healthy.
- Add private operator status views and runbook links without exposing a public
  administrative panel or turning diagnostic counters into identity, billing,
  or durable usage records.
- Add staging failure drills, exact-source deployment checks, external
  multi-vantage protocol acceptance, real Telegram firing/recovery delivery,
  rollback, and secret-rotation evidence.
- BREAKING: the current local-only/no-external-telemetry monitoring contract is
  replaced by an explicit opt-in fleet observability contract with authenticated
  outbound telemetry and documented retention.
- BREAKING: central Alertmanager becomes the authoritative human paging path;
  per-node ntfy/Pushover delivery is removed after staged migration so one
  incident does not have divergent routing, templates, suppression, or secrets.

## Capabilities

### New Capabilities

- `operations/centralized-observability`: Owns collection, metric contracts,
  storage, rule evaluation, Telegram routing, dead-man coverage, private
  dashboards, operations, rollback, and proof for server and VPN availability.

### Modified Capabilities

- None. The active `operations/fleet-observation` change remains the source of
  passive inspection and authenticated sentinel evidence; this change consumes
  its published redacted results without redefining inspection or probe truth.

## Impact

- Ansible monitoring and watchdog roles, role ordering, new control-plane and
  telemetry-agent runtime ownership, systemd units, firewall/private-management
  contracts, and per-host convergence/disable behavior.
- Prometheus-compatible metric names and labels, recording and alerting rules,
  Alertmanager Telegram templates/routes, private status views, and
  control-plane self-monitoring.
- SOPS schema/example/coverage for Telegram, remote-write authentication,
  control-plane TLS, and dead-man material, with unique least-privilege
  credentials and auditable rotation.
- Existing protocol-liveness, passive inspection, backup/restore, honeypot,
  Xray diagnostics, node manifest, and watchdog outputs as bounded producers;
  no raw journal or per-user traffic forwarding.
- Makefile/operator commands, deployment profiles, documentation, Molecule and
  unit tests, configuration validation, staging fault injection, live fleet and
  external sentinel acceptance.
- A separately placed always-on monitoring host and two approved independent
  sentinel paths are operational prerequisites. Provider selection, production
  provisioning, Telegram bot/chat creation, credential installation, and live
  failure injection remain explicitly authorized execution steps rather than
  consequences of planning.
