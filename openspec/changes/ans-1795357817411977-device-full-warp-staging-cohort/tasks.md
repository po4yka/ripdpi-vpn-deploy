# ANS-1795357817411977: Add a device-full staging cohort with WARP outbound for refresh acceptance

## Objective

A tracked `vpn-device-full-warp-staging` cohort lets a disposable node run the WARP outbound backend through its own disposable onboarding intent.

## Ownership

`ansible/group_vars/vpn-device-full-warp-staging.yml`, `ansible/role-tiers.yml`, `ansible/CLAUDE.md`, `docs/reference/deploy-profiles.md`, `docs/reference/architecture.md`, profile tests; `scripts/disposable_promotion.py`, `scripts/prepare-disposable-promotion-intent.py`, the `prepare-disposable-promotion-intent` Make inputs, `docs/reference/protocol-liveness.md`, the `vpn-bootstrap` skill and the promotion intent tests. One writer.

## Execution

- [x] ANS-1795358025489176 Add the device-full-warp-staging cohort, family listing and profile tests #feature !high @item:ANS-1795357817411977
- [x] ANS-1795444222175506 Admit the WARP staging cohort in disposable onboarding intents #feature !high @item:ANS-1795357817411977
- [ ] ANS-1795358069969748 Run the WARP namespace refresh and reboot check on a disposable node with this cohort #feature !high @item:ANS-1795357817411977

## Verification

- Local: profile tests (`test_deploy_profile_guard.py`, `test_ci_real_deploy.py`, `test_public_site_contract.py`, `test_tailnet_management.py`, `test_listener_contract.py`, `test_disposable_promotion.py`, `test_prepare_disposable_promotion_intent.py`, `test_retire_unbound_staging_client.py`), `scripts/check-deploy-profile.py`, `make docs-check`, `make task-check`.
- Remote CI: PR checks.
- Staging: WARP refresh and reboot check on one disposable node (SEC-1795260492741288).
- Dry-run, live, client, artifact: not applicable.
