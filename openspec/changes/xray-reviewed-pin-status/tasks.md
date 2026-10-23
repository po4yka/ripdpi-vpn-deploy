# XRY-1792776853872491: Separate reviewed Xray pins

## Objective

Check the explicit reviewed pin independently of upstream Latest status.

## Ownership

Primary writer owns the pin checker, its tests and release-line reference.

## Execution

- [ ] XRY-1792776944051255 Separate reviewed pin parsing from release availability and verify strict failure cases #bug !high @item:XRY-1792776853872491

## Verification

Focused pin regressions, breaking-change guard, make check and exact-head hosted CI. No live or client traffic change.
