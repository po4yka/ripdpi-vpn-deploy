---
id: XRY-1793635470456809
title: Deliver bounded XHTTP pools with payload-verified TCP reserves
kind: feature
status: doing
area: xray-config
priority: high
risk: high
owner: transport-resilience
parent: null
blocked_by: []
spec_mode: required
openspec_change: xhttp-payload-tcp-reserve
created: 2026-11-02
updated: 2026-11-02
related_tasks: ["po4yka/RIPDPI#TRN-1793634968382224"]
---

## Goal

Deliver the bounded stream-up XHTTP profile to RIPDPI and retain payload-verified TCP reserves when a UDP path fails.

## Acceptance criteria

- Export the complete typed pool profile for primary and alternate XHTTP endpoints; reject unsupported modes and invalid tuning.
- Import, persist and apply the emitted pool in the paired client without loss. Parallel sessions share the endpoint pool and respect its connection limit.
- Prefer a TCP reserve after an active UDP path fails payload verification. Preserve recovery thresholds, cooldown, bounded retries and the encrypted selection when every path fails.
- Observe exporter regression tests, paired client tests, independent review and the required local gate. Record hosted CI separately.
- Use synthetic fixtures only. Deployment, real credentials, physical-device acceptance and filtered-network acceptance are outside this change.
