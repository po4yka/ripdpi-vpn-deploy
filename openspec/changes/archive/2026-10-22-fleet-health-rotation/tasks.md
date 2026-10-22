# OPS-1792654666090980: Repair fleet health and resumable rotation boundaries

## Objective

Deliver strict truthful fleet status, authenticated survivor admission and
durable exact-plan resume, with regression coverage and protected-main acceptance.

## Ownership

- Status worker owns scripts/fleet-status.sh, scripts/fleet_status.py,
  scripts/fleet_inspection.py, tests/unit/test_fleet_status.py and
  tests/unit/test_fleet_inspection.py.
- Rotation worker owns scripts/fleet-rotate.sh, scripts/fleet_rotation.py,
  scripts/fleet_rotation_liveness.py, tests/unit/test_fleet_rotation.py and
  tests/bats/fleet_rotate_dryrun.bats.
- Primary owns all Make/vpnd integration, other existing test fixtures and
  regression callers, docs and subtree guidance. Primary alone writes task,
  spec and board state and stages, commits, publishes and merges the change.
- Shared inventory API changes belong only to the status worker; the rotation
  worker consumes that API after agreement. No worker overwrites another lane.

## Execution

- [x] OPS-1792654871067546 Implement strict inventory fleet status with truthful watchdog regressions #bug !high @item:OPS-1792654666090980
- [x] OPS-1792654872580225 Enforce authenticated survivor availability before each rotation with regressions #bug !high @item:OPS-1792654666090980
- [x] OPS-1792654873965490 Bind serialized durable resume to the exact plan with interruption regressions #bug !high @item:OPS-1792654666090980
- [x] OPS-1792654875144749 Integrate operator contracts and pass local checks independent review and protected main CI #bug !high @item:OPS-1792654666090980

## Verification

- Focused: full status, rotation and inspection unit files plus the complete
  fleet-rotation Bats file and affected existing operator/vpnd tests.
- Local: make task-check, shellcheck, complete make check; compiler-backed
  checks use the machine-wide build gate. Regressions cover positive behavior,
  unknown/stale evidence, strict SSH, changed plans and interrupted publication.
- Remote: required PR checks, independent security review, protected merge,
  then exact-revision main checks.
- Dry-run: isolated plan validation with no state or host effects.
- Staging/live/client deployment: not applicable to this source-only fix.
