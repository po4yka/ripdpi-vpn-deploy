## Context

Probe tooling exists for liveness and cascade legs; the exact continuity gaps per protocol are verified in the first step. `ansible/roles/monitoring/files/xray-stats-exporter.py` is the model for aggregate exporters.

## Goals / Non-Goals

- Continuous, bounded, aggregate-only health signals for the four protocols.
- Non-goal: per-user usage metrics, new probe protocols, or changes to rotation logic.

## Decisions

- Extend existing probes instead of adding a new probe framework. Rejected: a new daemon, because sentinel and probe-matrix already own vantage and credentials.
- Assumption: the first task step audits which of the four protocols already export a continuous metric; only the gaps are implemented.
- Assumption: the Hysteria2 traffic API listener is bound to loopback with its existing secret; no new exposure.
- Assumption: AmneziaWG handshakes are read with the pinned `awg show` tool on the node as an aggregate; the exporter never prints the peer table.
- Assumption: the probe credential is a dedicated probe identity, not a user identity (existing practice in `topology-authenticated-probes`).

## Contracts and ownership

- Scripts and roles listed in the proposal; one writer per file. The alert rule template and manifest are serialized lanes shared with D2, D5 and D6.

## Risks / Trade-offs

- Probe credential or sentinel outage reads as protocol failure -> existing sentinel quorum rules and an exporter-failure metric separate the two.
- Peer data leakage -> aggregate-only output tests.

## Migration Plan

Forward only; new units are enabled by role variables. Rollback disables the timers and removes the series; no data migration.
