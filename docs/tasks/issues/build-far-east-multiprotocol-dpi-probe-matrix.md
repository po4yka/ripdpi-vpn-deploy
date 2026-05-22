---
title: Build Far East multi-protocol DPI probe matrix on RU-ASN vantage
type: task
status: backlog
area: vpnd
priority: high
owner: unassigned
parent: null
blocks: []
blocked_by: []
created: 2026-05-22
updated: 2026-05-22
source_wiki_pages:
  - "[[far-east-multiprotocol-dpi-event-2026-05-22]]"
linked_task: null
---

- [ ] #task Build Far East multi-protocol DPI probe matrix on RU-ASN vantage #repo/RIPDPI-VPN-DEPLOY #area/vpnd #status/backlog ⏫

## Motivation

The 2026-05-22 ntc.party #24845 thread surfaced a coordinated multi-protocol DPI hit on Far East RU ISPs ~10:45–15:00 МСК window: MTProto + XHTTP-VLESS + XHTTP-Trojan + TCP-Trojan + possibly any encrypted non-443 traffic. Cross-protocol simultaneity is the new signal — TSPU appears to be applying policy at a level above per-protocol fingerprinting. Single-source forum signal; independent measurement is the gating step before promoting this to a confirmed mechanism.

## Proposed change

Extend `vpnd probe` (or add a new `vpnd probe-matrix` subcommand) to run a simultaneous probe matrix from a Far East RU-ASN vantage point.

Matrix dimensions:
- Protocols: MTProto, XHTTP-VLESS, XHTTP-Trojan, TCP-Trojan, plain TLS-non-443.
- Destination IP classes: Yandex Cloud (RU-domestic allowlist), generic RU-VPS, foreign datacenter (Hetzner / OVH).
- Time window: poll every 5 minutes; identify onset / recovery windows.

Output: structured JSON timeline distinguishing blocked / throttled / OK per (protocol × destination) cell. Persist to `vpnd/state/probe-matrix-<timestamp>.json` for offline analysis.

## Canonical recipe

new-vpnd-subcommand — follows §"New vpnd subcommand" in `CLAUDE.md` verbatim.

## Acceptance criteria

- [ ] `vpnd probe-matrix --vantage <far-east-vps> --duration 4h` runs and produces per-cell verdict JSON.
- [ ] Matrix covers 5 protocols × 3 destination IP classes.
- [ ] Onset/recovery time-window detection at 5 min granularity.
- [ ] Snapshot test for output schema lands in `vpnd/tests/`.
- [ ] `docs/PROBE-MATRIX.md` documents matrix dimensions and output format.

## Risks / open questions

- Far East VPS vantage availability — may need to commission a new node for the matrix run.
- Probe traffic generation could itself become a DPI signature; design so probes do not exceed legitimate-traffic rate.
- Result interpretation depends on independent OONI / dpi-checkers corroboration before promoting findings to wiki.

## References

- [[far-east-multiprotocol-dpi-event-2026-05-22]] — source concept
- [[2026-05-22-ntc-party-24845-tspu-multiprotocol-block]] — raw thread snapshot
- [[tcp-connection-freezing#Vector 3]] — Yandex-RU-domestic-allowlist differential explanation
