# SCR-1791467099957833: Install standalone liveness profiles

## Objective

Install standalone and mixed sentinels using only their required canonical emitter inputs.

## Ownership

Own scripts/install_liveness_sentinel.py, tests/unit/test_install_liveness_sentinel.py, scripts/DESIGN-NOTES.md, tests/CLAUDE.md and docs/PROTOCOL-LIVENESS.md. Serialize task files and generated board in this worktree.

## Execution

- [x] SCR-1791467227702182 Select required canonical emitter formats and cover standalone mixed and required-error cases #bug !high @item:SCR-1791467099957833
- [ ] SCR-1791467228251004 Verify source gates and real standalone P1 onboarding with authenticated XHTTP #bug !high @item:SCR-1791467099957833

## Verification

Focused installer/profile tests, make check and terminal exact-head CI; real P1 onboarding and authenticated XHTTP are required before closing this task.
