# ANS-1795351855549662: Add a disposable staging profile for the p2-udp transports

## Objective

A disposable staging node dry-runs the `vpn-p2-udp` transport set through the canonical deployment controller with staging secrets only: monitoring, watchdog and backup are off, everything else equals `vpn-p2-udp`.

## Ownership

Single serialized lane. Ansible: `group_vars/vpn-p2-udp-staging.yml`, `role-tiers.yml`. Tests: `tests/unit/test_deploy_profile_guard.py`, `tests/unit/test_listener_contract.py`, `tests/unit/test_tailnet_management.py`, `tests/unit/test_public_site_contract.py`, `tests/unit/test_ci_real_deploy.py`. Docs: `docs/reference/deploy-profiles.md`, `docs/reference/architecture.md`, `ansible/CLAUDE.md`.

## Execution

- [x] ANS-1795351937363114 Add the vpn-p2-udp-staging family profile with its contract tests #feature !high @item:ANS-1795351855549662
- [x] ANS-1795351982817826 Document the profile and its dry-run inputs #feature !high @item:ANS-1795351855549662

## Verification

- Local narrow checks: `scripts/check-deploy-profile.py`, the profile guard, listener contract, Tailnet profile, public site origin and staging origin tests, `make docs-check`.
- Local gate: `make check`.
- Remote: PR CI on the exact head SHA.
- Dry-run: `make dry-run` of a disposable staging node rendered with `COHORTS=p2-udp-staging`, recorded under `ANS-1795259263103243`.
