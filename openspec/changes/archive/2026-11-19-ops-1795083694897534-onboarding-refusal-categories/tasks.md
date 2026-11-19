# OPS-1795083694897534: Report specific onboarding refusal categories in SSH baseline failure receipts

## Objective

A deploy-mode onboarding refusal publishes its fixed category in the private SSH baseline failure receipt; the missing-Terraform-workspace case reports `recovery-promotion-payload-input-unavailable`.

## Ownership

`scripts/client_payload.py`, `scripts/fleet_inspection.py`, `scripts/install_liveness_sentinel.py`, `scripts/recovery_promotion.py`, `scripts/sshd-baseline-controller.py`, their tests in `tests/unit/`, and the receipt row in `docs/how-to/deploy.md`. One writer lane.

## Execution

- [x] OPS-1795083969470810 Propagate fixed emitter and promotion refusal categories to the baseline failure receipt #bug @item:OPS-1795083694897534
- [x] OPS-1795083982510317 Add behavioural tests for each layer and update the deploy receipt documentation #bug @item:OPS-1795083694897534

## Verification

- Local: `python3 -m pytest tests/unit/test_emit_singbox_roundtrip.py tests/unit/test_install_liveness_sentinel.py tests/unit/test_fleet_inspection.py tests/unit/test_recovery_promotion.py tests/unit/test_sshd_baseline_controller.py` and `make check`.
- Remote CI: the PR checks on the exact commit.
- Dry-run, staging, live, client and artifact: not applicable; check mode writes no failure receipt and the change alters only failure-path diagnostics.
