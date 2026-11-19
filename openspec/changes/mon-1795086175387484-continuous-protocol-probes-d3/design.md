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

## Audit of continuous probe coverage (MON-1795086204601885)

| Producer | vless-reality | xhttp | hysteria2 | amneziawg | Gap |
|---|---|---|---|---|---|
| `scripts/vpn-protocol-liveness.py` (sentinel runner) | authenticated `p0-reality` probe with payload fetch and `duration_ms` | authenticated `p1-xhttp` probe | authenticated `p2-hysteria2` probe | authenticated `p2-amneziawg` probe with fresh handshake | none: all four protocols are probed with the probe credential |
| `scripts/protocol-liveness.py` (evaluator, scheduled by `scripts/monitor-protocol-liveness.py`) | verdict per sentinel | verdict per sentinel | verdict per sentinel | verdict per sentinel | `duration_ms` is dropped from the published evidence, so no latency signal reaches the collector |
| `observability-protocol-liveness-adapter.py` (collector) | one-hot `vpn_observability_evidence_state` role | same | same | same | no per-protocol success gauge, no latency histogram, no `protocol`/`vantage` labels; the ingress relay rewrites the payload `node` label to the collector identity, so the probed node is lost |
| `scripts/probe-matrix-driver.py` | on-demand matrix report | same | same | same | operator-run, not continuous; continuity is owned by the scheduled liveness monitor, so the matrix is not changed |
| `scripts/cascade-leg-probe.py` | cascade legs only | - | - | - | not a per-protocol node probe; not changed |

Decisions taken from the audit:

- The evaluator publishes `profile_durations_ms` for each sentinel and required profile; the collector adapter derives `vpn_protocol_probe_success`, `vpn_protocol_probe_observed_timestamp_seconds` and the cumulative `vpn_protocol_probe_duration_seconds` histogram with the labels `protocol`, `node` and `vantage`. The protocol values reuse the client field-report `protocol` enum. The adapter keeps the cumulative bucket counts in a private state file, counts one observation per new `observed_at`, and omits success and latency for an item older than its staleness window (unknown, never healthy).
- The ingress relay keeps the payload `node` label only for `vpn_protocol_probe_*` series and only when the ingress identity is the collector's own cohosted agent, the sole holder of the published evidence. Every other sender keeps the certificate-bound `node` rewrite.
- The metric manifest schema admits the `histogram` type and the `protocol` label.
- Correction to the Hysteria2 assumption: the role had no Traffic Stats API listener. The opt-in exporter adds a loopback-only `trafficStats` listener whose secret is generated on the node (root-only file), so no SOPS schema change is needed.
- The AmneziaWG exporter reads `awg show all latest-handshakes` and prints only two counts.
