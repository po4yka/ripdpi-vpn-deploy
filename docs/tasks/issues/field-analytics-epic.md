---
id: EPC-1795085241910080
title: "Field analytics program: client field reports, per-protocol probes and block detection"
kind: epic
status: backlog
area: epic
priority: high
risk: high
owner: Planner
parent: null
blocked_by: []
spec_mode: required
openspec_change: epc-1795085241910080-field-analytics-epic
created: 2026-11-19
updated: 2026-11-26
related_tasks: []
---

## Goal

The operator can tell a server failure from a network block per client ASN and protocol, using opt-in anonymous client reports.

Priority rationale (2026-11-26): almost all external evidence about blocking is single-vantage. The threat model already states that CI measures only the unfiltered half. Opt-in client reports aggregated by client ASN and server ASN, with no IP addresses, are the only source that closes both gaps. Deliver the children in the order D2 (field-report ingest), D3 (continuous protocol probes), D5 (network block detection) ahead of other monitoring work. Evidence behind this ranking is single-source and unverified.

## Acceptance criteria

- Children D1 to D7 are done and their `blocked_by` edges stay accurate.
- D2, D3 and D5 are not postponed behind other monitoring work.
- The acceptance evidence is the D7 verification.
