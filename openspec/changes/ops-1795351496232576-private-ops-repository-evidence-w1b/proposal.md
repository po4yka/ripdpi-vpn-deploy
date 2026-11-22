# Change: Carry the ops repository capability and prove its inputs with a dry-run

Task ID: `OPS-1795351496232576`

## Why

`OPS-1795327950629406` (W1) delivered the private ops repository: Make and the deploy controller read external inputs (pull request 683), the repository has an owner-only merge gate, and the current non-secret inputs are imported (pull request 686). Its lifecycle could not close, because the evidence transfer committed in `baa16596` omits `REQ-OPSREPO-MERGE-GATE` and taskctl validates every historical transfer. W1 was dropped and archived without spec sync (`openspec/changes/archive/2026-11-22-ops-1795327950629406-private-ops-repository-w1`). This change carries W1's capability spec into the main specs and owns the evidence W1 could not close: a dry-run through the ops inventory, which the repository policy requires because W1 changed the deploy controller. Part of epic `EPC-1795327697650892`.

## What Changes

- Carries the `operations/private-ops-repository` capability spec unchanged from W1.
- Records the merged W1 implementation, the live ops repository, its merge gate and the import as evidence for that spec.
- Runs a check-mode dry-run for one production node through the ops inventory and compares host selection and inputs with the kit.
- No code change: the implementation is already on main.

## Capabilities

### New Capabilities

- `operations/private-ops-repository`: as defined in W1; carried unchanged.

### Modified Capabilities

- None.

## Impact

- Task state and specs only, plus one authorized check-mode dry-run against a production node (no changes applied).
