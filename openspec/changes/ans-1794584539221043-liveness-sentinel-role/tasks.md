# ANS-1794584539221043: Prepare a cloud liveness sentinel through an Ansible role

## Objective

A permanent cloud node, first the long-lived split-hop Node B, becomes a protocol-liveness sentinel through Ansible: pinned sing-box, Xray and the immutable AWG toolchain are installed into role-owned paths after verification, the native probe finds them, and the installed `expected_runtime` pins are published for the operator.

## Ownership

Single serialized lane. Ansible: `roles/liveness-sentinel`, `role-tiers.yml`, `playbooks/site.yml`, `group_vars` complete `vpn` maps. Scripts: `provision-disposable-liveness-runtime.py`, `vpn-protocol-liveness.py`, `contract/liveness-runtime-pins.json`. Tests: `tests/unit/test_liveness_sentinel_role.py`, `tests/unit/test_tailnet_management.py`. Docs: `docs/reference/protocol-liveness.md`, `docs/how-to/deploy.md`, `docs/reference/deploy-profiles.md`, `docs/reference/testing.md`.

## Execution

- [x] ANS-1794584586331605 Ship the liveness-sentinel role, shared pin file and probe prefix with Molecule, contract tests and docs #feature !high @item:ANS-1794584539221043

## Verification

- Local narrow checks: `make molecule-test ROLE=liveness-sentinel`, `tests/unit/test_liveness_sentinel_role.py`, `tests/unit/test_provision_disposable_liveness_runtime.py`, `tests/unit/test_tailnet_management.py`, `scripts/check-deploy-profile.py`, ansible-lint, `make docs-check`, then `make -k -j 4 check` once.
- Remote: PR CI on the exact head SHA.
- Dry-run, live and client: converging the live Node B with the role, building the AWG bundles and fetching `expected-runtime.json` are separately authorized operator work.
- [x] ANS-1794587887906786 Admit the liveness-sentinel AWG inputs through the deploy extra-vars validator #bug !high @item:ANS-1794584539221043
