# Change: Deliver isolated reliable and upgradeable four-protocol connectivity

Task ID: `EPC-1791618453830051`

## Why

The original 22 transport findings were audited at 28783a7e1d48a0c192db4da06cf23b9d9a9d5637. Current main 605ae0be18dcbe1c55e3e7d8658131b2e0c201d3 integrates several repairs, while residual isolation, delivery, runtime acceptance, validation and authenticated topology defects remain. This behavioral epic coordinates their smallest coherent changes and a gated upgrade/feature path; it does not duplicate source-fixed work or revive cancelled external acceptance.

Audit coverage: A01, A02, A03, A04, A05, A06, A07, A08, A09, A10, A11, A12, A13, A14, A15, A16, A17, A18, A19, A20, A21, A22; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Deliver working public recipient connectivity with private-destination isolation and exact per-device authoritative configuration.
- Retain complete accepted runtime authority across failed changes and reconcile effective health rather than configuration intent.
- Exercise all original findings through inherited repair ownership or named executable regression cases; keep source, native, physical and external evidence distinct.
- Deliver stable candidate migration and typed opt-in XHTTP/ECH features only after the baseline protocol matrix and required recipient acceptance pass.

## Capabilities

### New Capabilities

- `transport/reliable-four-protocol-portfolio`: deliver isolated reliable and upgradeable four-protocol connectivity.

### Modified Capabilities

- None.

## Impact

- Child OpenSpec changes and their exact owned runtime/schema/client/test scopes
- Existing reviewed remediation change records are read-only inherited evidence
- NEW audit-coverage.md and roadmap.md within this linked change; no separate process task
- Shared schemas, Makefile, CI selectors, snapshots and portfolio metadata have one serialized integration owner
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
