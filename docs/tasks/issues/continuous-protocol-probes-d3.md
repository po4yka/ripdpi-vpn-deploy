---
id: MON-1795086175387484
title: Export continuous per-protocol authenticated probe and aggregate peer metrics
kind: feature
status: review
area: monitoring
priority: high
risk: high
owner: Planner
parent: EPC-1795085241910080
blocked_by: []
spec_mode: required
openspec_change: mon-1795086175387484-continuous-protocol-probes-d3
created: 2026-11-19
updated: 2026-11-19
related_tasks: []
---

## Goal

Sentinel and probe-matrix authenticated probes for VLESS+REALITY, XHTTP, Hysteria2 and AmneziaWG run continuously and export per-protocol Prometheus metrics, and aggregate (not per-user) exporters exist for AmneziaWG and Hysteria2.

## Acceptance criteria

- Each of the four protocols has a continuous probe success gauge and latency metric with the labels protocol, node and vantage only.
- An AmneziaWG exporter reports the count of peers with a fresh handshake, never per-peer series.
- A Hysteria2 exporter reports aggregate traffic and connection counts from the traffic API, never per-user series.
- Metrics are in the metric manifest and the existing observability tests pass.
