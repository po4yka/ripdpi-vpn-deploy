# SEC-1792678909985498: Fail over admitted TCP destinations

## Objective

Reach a viable admitted A or AAAA destination through the fixed gateway within a bounded connection race, with one winning stream and no application replay.

## Ownership

Transport audit owns `scripts/transport_destination_policy.py`, `scripts/transport_egress_normalizer.py`, `tests/unit/test_transport_destination_failover.py`, required API call-site updates in `tests/unit/test_transport_destination_boundary.py`, and this task/change. Coordinate the precise `scripts/CLAUDE.md` and `tests/CLAUDE.md` additions and generated board during integration; do not edit shared Make targets or unrelated branches.

## Execution

- [x] SEC-1792679160742251 Return ordered immutable admitted address sets and update TCP and UDP policy consumers with normalization and family-order tests #feature !high @item:SEC-1792678909985498
- [x] SEC-1792679161411775 Race bounded nonblocking gateway CONNECT attempts under one deadline with winner-only relay and resource cleanup #feature !high @item:SEC-1792678909985498
- [ ] SEC-1792679162099578 Exercise real socket failover, stalled and abrupt controls, deadlines, policy changes, cancellation and no application replay; run complete local and hosted gates #feature !high @item:SEC-1792678909985498

## Verification

Run both complete destination test files with the pinned Python environment,
strict OpenSpec and task checks, then `build-gate -- mise exec -- make check`.
Hosted CI must pass for the reviewed commit. Portable real sockets prove local
normalizer behavior through an owned gateway fixture; no staging, live node or
Android acceptance is claimed by that result. All steps remain open until the
positive capability and their named checks are observed.
