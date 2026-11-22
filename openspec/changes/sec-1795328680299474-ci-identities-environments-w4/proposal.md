# Change: Issue revocable CI identities in scoped GitHub environments

Task ID: `SEC-1795328680299474`

## Why

Every credential that operates the fleet today is the operator's own: the age identity, the admin SSH key, the Tailnet login and the provider tokens. Giving them to CI would make revocation of CI impossible without locking out the operator. CI needs its own identities, each revocable alone, and each available only to the jobs that need it. Part of W4 of epic `EPC-1795327697650892`.

## What Changes

- A fixed matrix of GitHub environments in the ops repository, with the secrets each may hold and whether it needs a required reviewer:
  - `tofu-plan` (no reviewer), `tofu-apply` (reviewer): state and provider credentials only.
  - `deploy-check` (no reviewer), `deploy` (reviewer), `ops-secrets` (reviewer, rotate and issue): age, SSH and Tailnet identities only.
  - `tailnet-policy` (reviewer): Tailnet policy push only.
- A validator in the public repository (`scripts/validate-ops-environments.py`) that reads the ops repository workflows and the environment matrix and rejects a job that references a secret outside its environment, a mutating job in a no-reviewer environment, or a no-reviewer job that consumes executable configuration changed in the triggering pull request.
- A separate CI age recipient added to the recipient policy; every scoped SOPS file is re-encrypted to operator plus CI. The operator identity becomes break-glass in the password manager.
- BREAKING: the admin SSH key input becomes a list (`admin_ssh_public_keys`) in every root and cloud-init, and the `baseline` role manages the admin account's `authorized_keys` exclusively from that list, so a CI key can be added and revoked by deploy.
- Tailnet: two CI tags (`tag:ci-tofu`, `tag:ci-deploy`) joined by workload identity federation or OAuth clients, `tagOwners`, and grants (`tag:ci-tofu` to the egress proxy port only; `tag:ci-deploy` to the nodes' management SSH only). The Tailnet policy file moves into the ops repository and is pushed by the official GitOps action.
- Least-privilege tokens for Scaleway, UpCloud, Vultr, Hetzner, Backblaze, Porkbun and Tailscale, each recorded in the catalog with its revoke procedure; read-only tokens for `tofu-plan` where the provider offers them.

## Capabilities

### New Capabilities

- `security/ci-operator-identities`: CI identities, environment matrix, reviewer rules and revocation.

### Modified Capabilities

- `ci/credentialed-deploy-gating`: unchanged for the public repository; the same no-secret-expansion and fork rules are extended to the ops repository by the new validator (no edit to the existing spec).

## Impact

- Terraform: `admin_ssh_public_key` to `admin_ssh_public_keys` in all roots and `terraform/shared/cloud-init.yaml.tftpl`; conftest policy for the list.
- Ansible: `ansible/roles/baseline` (exclusive admin `authorized_keys`), Molecule scenario.
- Secrets: CI age recipient in the ops repository `.sops.yaml`; `sops updatekeys` over every scoped file.
- External (authorized live steps): GitHub environments and secrets, Tailnet policy, OAuth clients or federated identities, provider tokens.
