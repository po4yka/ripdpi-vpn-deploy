---
id: OPS-1792759217301702
title: Select profiles by transfer quality and diagnose MTU
kind: feature
status: done
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: profile-quality-mtu
created: 2026-10-23
updated: 2026-10-24
related_tasks: ["po4yka/RIPDPI#TRN-1792759596946903"]
status_detail: Positive native and emulator acceptance, catalogue migration repair, full local gate, producer/client PRs and exact combined-main CI passed. No fleet or physical-device acceptance is claimed.
closed_at: "2026-10-24T18:10:20Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Positive native and emulator quality and packet-size acceptance, catalogue migration repair, full local make check, producer/client PRs and all five exact-main workflows passed at f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc. No fleet or physical-device acceptance is claimed.
---

## Goal

Select existing relay profiles using verified goodput and latency under load,
with durable traffic limits and stable switching, and expose correctly scoped
MTU diagnosis in the paired recipient.

## Acceptance criteria

- A coordinated version 2 policy reaches the actual recipient with strict
  bounds, exact payload verification and no mandatory backend.
- The current selector compares healthy members, retains manual/network/runtime
  authority and promotes only a repeatedly better qualified candidate.
- A durable shared body budget bounds failures, cancellation, restart and policy
  changes before network I/O. Exhaustion is not a transport failure.
- Quality and MTU results distinguish verified, partial, stale and unsupported
  evidence. Direct packet-size lower bounds never become exact or tunnel MTU.
- Real socket and native client tests exercise the positive selection and
  diagnostic paths, including cleanup, failure boundaries and hysteresis.
- Independent review, full relevant local gates, paired contracts and protected
  PR/main CI pass. Refusal-only code or mock-only proof cannot close this feature.
- Source delivery does not enable a live policy, deploy servers or claim
  physical-device acceptance.
