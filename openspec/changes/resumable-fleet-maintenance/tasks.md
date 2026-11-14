# OPS-1793686022000048

## Objective

Deliver all ten fleet-maintenance requirements through canonical operations.

## Ownership

Primary owns maintenance, release-input and operator-kit scripts, matching tests,
Make wiring, CI and documentation. Shared Make and CI writes are serialized.
Independent review is read-only.

## Execution

- [ ] OPS-1793686512392634 Deliver and verify resumable fleet maintenance and encrypted recovery #feature !high @item:OPS-1793686022000048
- [ ] OPS-1794070939441144 Resume a converged node at acceptance without a second deploy #feature !high @item:OPS-1793686022000048

## Verification

Run matching behavior tests, make check, independent security review, exact-head
hosted CI, merged-main CI, canonical live previews and scoped acceptance, and
independent encrypted offsite recovery verification.
- [x] OPS-1794657885705909 Reconcile accepted deployments and generate catalog-bound maintenance configurations #feature !high @item:OPS-1793686022000048
- [x] OPS-1794657918337568 Schedule bounded drift checks and verified operator backups with job status #feature !high @item:OPS-1793686022000048
