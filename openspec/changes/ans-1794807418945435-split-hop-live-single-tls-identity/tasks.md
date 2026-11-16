# ANS-1794807418945435: Present one TLS identity on the live split-hop Node A

## Objective

A production host in the profile `vpn-split-hop-family-egress-live` passes the TLS identity preflight with no exception, and the live Node A runs that profile with REALITY self-steal.

## Ownership

`ansible/group_vars/vpn-split-hop-family-egress-live.yml`, `tests/unit/test_tailnet_management.py`, `tests/unit/test_tls_identity_preflight.py` and `docs/reference/deploy-profiles.md`. The live rollout uses the private inputs of the live pair outside Git. One writer; no shared-file lane.

## Execution

- [x] ANS-1794807559120996 Enable self-steal and a private self-steal port in the live family-egress profile, with its tests and profile reference #feature @item:ANS-1794807418945435
- [x] ANS-1794807590109058 Roll the live Node A out with self-steal: dry-run, deploy, sentinel reinstall and device refresh #feature @item:ANS-1794807418945435

## Verification

Local: `pytest tests/unit/test_tls_identity_preflight.py tests/unit/test_deploy_profile_guard.py tests/unit/test_reality_self_steal.py`, the profile tests in `test_tailnet_management.py`, `test_public_site_contract.py` and `test_ci_real_deploy.py`, `scripts/check-deploy-profile.py`, `make docs-check` and `make task-check`. Remote CI on the merge commit. Live: a full dry-run of Node A, its review, the deploy with `make verify` and `make security-verify`, a fresh liveness proof from Node B's sentinel, and one handshake for each transport from the refreshed device. No staging deploy: the staging profiles do not change.
