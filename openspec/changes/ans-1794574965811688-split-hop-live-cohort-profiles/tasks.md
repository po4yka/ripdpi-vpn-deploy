# ANS-1794574965811688: Ship long-lived split-hop research cohorts for a live pair

## Objective

A long-lived split-hop research pair converges through tracked non-family cohorts: Node B listener-free as in staging, Node A with the production `vpn-device-full-tailnet` transports, monitoring, watchdog and backup, plus the responder and, in a separate profile, family egress scope.

## Ownership

Single serialized lane. Ansible: `group_vars/vpn-split-hop-egress-live.yml`, `group_vars/vpn-split-hop-ingress-live.yml`, `group_vars/vpn-split-hop-family-egress-live.yml`. Tests: `tests/unit/test_tailnet_management.py`. Docs: `docs/reference/deploy-profiles.md`, `docs/how-to/split-hop-pilot.md`.

## Execution

- [x] ANS-1794576187734721 Ship live split-hop cohorts for Node A and Node B with contract tests and docs #feature !high @item:ANS-1794574965811688

## Verification

- Local narrow checks: `scripts/check-deploy-profile.py`, `tests/unit/test_tailnet_management.py`, ansible-lint on the new cohorts, `make docs-check`.
- Remote: PR CI on the exact head SHA.
- Dry-run, live and client: the live pair's provisioning, deploy and device check are separately authorized operator work recorded under `ANS-1794231660855533`.
