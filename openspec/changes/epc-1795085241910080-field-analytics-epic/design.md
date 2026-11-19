## Context

See proposal.md. Server-side health is rich but the client path is invisible. The program adds one narrow, anonymous client signal and joins it with sentinel probes.

## Goals / Non-Goals

- Goal: distinguish server failure from network blocking per ASN and protocol.
- Goal: one canonical contract owned here and vendored by RIPDPI.
- Non-goal: per-user or per-device telemetry, or automatic rotation (the operator decides).
- Non-goal: a v2 compatibility path.

## Decisions

- Contracts live in this repository (`contract/`); RIPDPI vendors them (R2). Rejected: separate copies per repository, because they drift.
- Child changes are separate OpenSpec changes so each is reviewable and testable alone. Rejected: one large change.
- Assumption: all children have `risk: high` because they touch a cross-repository contract and an internet-facing endpoint.
- Assumption: RIPDPI R1-R4 are filed in the RIPDPI repository by its owner; this repository links them as `related_tasks` once their qualified IDs exist.

## Contracts and ownership

- Shared contract shape is defined in D1 and consumed by D2, D4, D5 and D7.
- One writer per child; shared files (`scripts/validate-bundle.py`, `scripts/emit-bundle.sh`, the alert rule template) are serialized in order D1, D3, D4, D2, D5, D6.

## Risks / Trade-offs

- Client signal is sparse for small ASNs -> suppress buckets under 5 attempts and bound ASN labels to top-N plus "other".
- Cross-repository drift -> D1 golden fixtures are vendored by RIPDPI R2.

## Migration Plan

Forward only. Bundle v3 replaces v2 in one change (BREAKING, named in D1 and D4). Rollback is a git revert of the generator and schema together with the matching client release.
