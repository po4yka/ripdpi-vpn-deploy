# SEC-1795328680299474: Issue revocable CI identities in scoped GitHub environments

## Objective

CI holds its own age, SSH, Tailnet and provider identities, each in only the GitHub environments that need it, mutating operations run only after the operator merges, pull-request input never runs with secrets, and each identity can be revoked alone.

## Ownership

`scripts/validate-ops-environments.py`, `tests/unit/test_validate_ops_environments.py`, `terraform/providers/*/{variables,main}.tf`, `terraform/shared/cloud-init.yaml.tftpl`, `terraform/policy/`, `ansible/roles/baseline/**`, `docs/reference/secrets.md`, new `docs/how-to/ci-identities.md`. Ops repository: `.sops.yaml`, `config/*.secrets.sops.yaml`, `config/tfvars/**`, `tailnet/policy.hujson`, `catalog.json`. Serialized after W3 for the Terraform roots.

## Execution

- [x] SEC-1795328868236026 Add the environment and secret matrix with a validator that rejects cross-environment secrets and unsafe PR inputs #feature !high @item:SEC-1795328680299474
- [x] SEC-1795328879513998 Turn the admin key input into a list and make baseline manage admin authorized_keys exclusively, with Molecule add and revoke #feature !high @item:SEC-1795328680299474
- [x] SEC-1795328890918872 Add the CI tags, tagOwners and grants to an imported Tailnet policy file managed by the GitOps action #feature !high @item:SEC-1795328680299474
- [ ] SEC-1795328902011315 Create environments with default-branch policies and the owner-only merge ruleset and generate CI age and SSH identities in CI (authorized live step) #feature !high @item:SEC-1795328680299474
- [ ] SEC-1795328913746423 Re-encrypt every scoped SOPS file to operator plus CI and issue least-privilege provider tokens with catalog entries (authorized live step) #feature !high @item:SEC-1795328680299474

## Verification

Local: `python3 -m pytest tests/unit/test_validate_ops_environments.py`, `make tf-test`, `make tf-policy-verify`, `make molecule-test ROLE=baseline`, `make snapshot-check`, the `security-review` skill checklist. Remote CI: PR checks. Dry-run and live (authorized): baseline dry-run then deploy with both admin keys; revoke drill on staging; environment check with `scripts/check-ci-deploy-gate.py` logic against the ops repository; Tailnet policy test then apply.
