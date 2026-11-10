# ANS-1794322927427537: Add split-hop staging cohort profiles for Node A and Node B

## Objective

The canonical deployment controller stages both split-hop nodes through tracked cohorts: Node B listener-free, Node A with every `device-full-staging` transport plus the responder and, in a separate profile, family egress scope.

## Ownership

Single serialized lane. Ansible: `group_vars/vpn-split-hop-egress-staging.yml`, `group_vars/vpn-split-hop-ingress-staging.yml`, `group_vars/vpn-split-hop-family-egress-staging.yml`. Tests: `tests/unit/test_deploy_controller.py`, `tests/unit/test_tailnet_management.py`. Docs: `docs/how-to/split-hop-pilot.md`, `docs/reference/deploy-profiles.md`.

## Execution

- [x] ANS-1794323562304527 Add the three split-hop staging cohort profiles with their contract tests #feature !high @item:ANS-1794322927427537
- [x] ANS-1794324110536208 Correct the split-hop pilot guide and the deploy profile reference #feature !high @item:ANS-1794322927427537

## Verification

- Local narrow checks: `scripts/check-deploy-profile.py`, the no-listener promotion and Tailnet profile tests, `make snapshot-check`, `make docs-check`.
- Local gate: `make check`.
- Remote: PR CI on the exact head SHA.
- Dry-run and staging: a dry-run of each staging node with its cohort, recorded under `ANS-1794231660855533`.
