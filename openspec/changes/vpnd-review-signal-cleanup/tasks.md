# SEC-1792842686096891: Stop terminal reviews on worker-delivered signals

## Objective

End terminal reviews after handled signals and complete cleanup without input.

## Ownership

CLI implementer owns the async terminal reader/export, shared review/signal
contracts, deploy/reconverge callers, narrow signal/Darwin loop dispatch, retained
runner cancellation join, wizard/lifecycle/runner tests and vpnd guidance.
Root owns task/spec records, board, package/full acceptance and Git delivery.
The independent reviewer is read-only. Runner process ownership is unchanged.

## Execution

- [x] SEC-1792842915023775 Implement signal-responsive terminal reviews and deterministic worker-signal regressions #bug !high @item:SEC-1792842686096891
- [x] SEC-1792842915762104 Preserve cancellation cleanup and terminal resource lifetimes with boundary tests #bug !high @item:SEC-1792842686096891
- [ ] SEC-1792842916403380 Verify the installed CLI, complete local gates, independent review and exact PR/main CI #bug !high @item:SEC-1792842686096891

## Verification

Run deterministic real-launcher PTY regressions before and after the fix, then
the affected wizard/lifecycle/runner tests, complete vpnd tests, lint and parity,
package validation, full local check and exact-head PR/main CI. No real provider,
private credential, SSH, deployment or device action is part of these checks.
