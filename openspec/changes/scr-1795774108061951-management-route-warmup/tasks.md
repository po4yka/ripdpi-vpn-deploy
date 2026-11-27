# SCR-1795774108061951: Warm the Tailnet management route before readiness and outlast relay home changes

## Objective

A preview or deploy on a Tailnet transport establishes and measures the relayed route before its readiness probe, refuses an unreachable or unusable route in seconds, and keeps its shared SSH session through a 300 s reply gap.

## Ownership

`scripts/deploy-controller.py` (`require_management_route`, the host-loop call site, `multiplexed`), the controller unit tests under `tests/unit/`, and `docs/how-to/deploy.md`. One writer for the controller file.

## Execution

- [x] SCR-1795774279138177 Warm and measure the Tailnet route before readiness in dry-run and deploy #feature !high @item:SCR-1795774108061951
- [x] SCR-1795774324586353 Raise the shared SSH master silence budget to 300 s in both modes #feature !high @item:SCR-1795774108061951
- [x] SCR-1795774367402539 Document the gated preview and refusal categories in the deploy runbook #feature !high @item:SCR-1795774108061951
- [x] SCR-1795774415106539 Reconcile the channel tolerance spec and record a live preview over the relayed route #feature !high @item:SCR-1795774108061951

## Verification

- Local: the controller unit tests that pin the gate order, the warm-up probe, the mode split and the SSH options; `make docs-check`.
- Remote CI: the `ci` run of the merge commit.
- Dry-run: one timed preview of a production node over the relayed route, with the route report in its log.
- Staging, client: not applicable; the change touches only the operator controller.
