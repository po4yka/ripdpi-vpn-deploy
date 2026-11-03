# OPS-1793686022000048

## Objective

Deliver all nine fleet-maintenance requirements through canonical operations.

## Ownership

Primary owns maintenance, release-input and operator-kit scripts, matching tests,
Make wiring, CI and documentation. Shared Make and CI writes are serialized.
Independent review is read-only.

## Execution

- [ ] OPS-1793686512392634 Deliver and verify resumable fleet maintenance and encrypted recovery #feature !high @item:OPS-1793686022000048

## Verification

Run matching behavior tests, make check, independent security review, exact-head
hosted CI, merged-main CI, canonical live previews and scoped acceptance, and
independent encrypted offsite recovery verification.
