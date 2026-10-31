---
id: SEC-1793428392418058
title: Align the RIPDPI bundle latency probe cadence with the standard artifact
kind: bug
status: review
area: security
priority: high
risk: standard
owner: Client contract maintainer
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1793428392418058-align-the-ripdpi-bundle-latency-probe-cadence-with-the-standard-artifact
created: 2026-10-31
updated: 2026-10-31
related_tasks: ["po4yka/RIPDPI#DAT-1793428393229398"]
---

## Goal

The RIPDPI bundle's `auto` outbound probes latency every 30 minutes like the standard sing-box artifact, the two bundle contract examples carry that interval, and the client's vendored copies (`po4yka/RIPDPI#DAT-1793428393229398`) stay byte-identical so `contract-sync` passes.

## Acceptance criteria

- `scripts/client_payload.py` emits `interval: 30m` for every format with no format conditional.
- `contract/ripdpi-bundle.payload-failover.json` and `contract/ripdpi-bundle.hysteria-port-hopping.json` differ only in that scalar, and the byte-compare tests in `tests/unit/test_client_payload_recipient_boundaries.py` pass.
- `docs/reference/client-notes.md` and the `SEC-1793386547449444` change record describe one cadence.
- `./taskctl validate` and `make task-federation PEER_ROOT=<RIPDPI checkout>` pass; `contract-sync` passes after both repositories merge.
