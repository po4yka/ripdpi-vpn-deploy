# CI identities and environments

> **Status:** Current · **Type:** how-to · **Tier:** — · **Reviewed:** 2026-11-22

CI operates the fleet from the private ops repository with its own identities: a CI age recipient, a CI admin SSH key, two Tailnet tags and scoped provider and state tokens. Each identity lives only in the GitHub environments that need it, and the operator can revoke each one alone. This page covers the environment matrix, the pull-request gate and the order of the live setup.

## Environment matrix

| Environment | Runs on | Secrets |
|---|---|---|
| `tofu-plan` | `pull_request_target` preview, schedule | `STATE_PASSPHRASE`, `STATE_ACCESS_KEY_ID`/`STATE_SECRET_ACCESS_KEY` (state bucket `tofu-state-plan`), provider tokens (read-only where the provider offers one), `TS_CI_TOFU_OAUTH_*` |
| `tofu-apply` | push to `main` | the same names, with the `tofu-state-apply` identity and write tokens |
| `deploy-check` | `pull_request_target` preview, schedule | `SOPS_AGE_KEY` (CI age identity), `CI_SSH_PRIVATE_KEY`, `TS_CI_DEPLOY_OAUTH_*` |
| `deploy` | push to `main` | the same names as `deploy-check` |
| `ops-secrets` | push to `main` | `SOPS_AGE_KEY` only |
| `tailnet-policy` | push to `main` | `TS_POLICY_OAUTH_*` only |
| `ci-bootstrap` | push to `main` | `CI_BOOTSTRAP_TOKEN` only: a short-lived fine-grained token that writes the generated CI identities into their environments |

Provider token names are `HCLOUD_TOKEN`, `UPCLOUD_TOKEN`, `VULTR_API_KEY`, `SCW_ACCESS_KEY`/`SCW_SECRET_KEY` and `PORKBUN_API_KEY`/`PORKBUN_SECRET_API_KEY`. Every environment allows deployments from `main` only. The ops repository's `operator-merge-gate` ruleset blocks direct pushes, force pushes and deletion on `main` and lets only the owner merge, so the operator's merge is the approval for every mutating run.

`scripts/validate-ops-environments.py --root <ops checkout>` enforces the matrix on every workflow in the ops repository:

- a job uses only the secrets of its own environment, and every secret needs an environment;
- `tofu-apply`, `deploy`, `ops-secrets` and `tailnet-policy` run only on a push to `main`;
- preview environments run no mutating command (`make apply`, `deploy*`, `rotate-*`, `issue-*`, `tofu apply`, `sops` writes and similar);
- a `pull_request_target` job checks out the pull request head only into a separate directory and runs the `--pr` classifier before its first secret;
- `secrets: inherit`, the whole `secrets` context and dynamic environment names are refused;
- each environment secret has a `catalog.json` entry with `authority: gh-environment`, `environment`, `secret`, `scope`, `expires_at` and `revoke_procedure`.

With `--public-repo <public checkout>` it also refuses an `upstream.lock` revision that `origin/main` of the public repository does not contain.

## Pull-request previews

A preview job runs default-branch workflow code. Before any secret step it runs:

```bash
python3 scripts/validate-ops-environments.py --root <pr checkout> --pr <base sha> <head sha> --public-repo <public checkout>
```

The classifier prints a JSON verdict. `preview` (exit 0) means the diff changes only boolean toggles (`enable_hysteria`, `enable_backups`, `enable_provider_firewall`, `additional_public_ip`) on existing `config/tfvars/<provider>/<workspace>.tfvars` files. The job then builds the preview from the trusted tree plus those values. `defer` (exit 1) lists the reasons. The job then loads no credential, and the change gets its first credentialed run after the operator merges it. Additions, deletions, renames, mode or symlink changes, inventories, `known_hosts`, backend files, `.sops.yaml`, workflows, `fleet.mk` and `upstream.lock` always defer.

## Live setup order

Each step is a live action that needs the operator's authorization:

1. Create the seven environments with a deployment branch policy of `main` only. Confirm that the `operator-merge-gate` ruleset is active.
2. Generate the CI age identity and the CI SSH key in one `ci-bootstrap` run, so that the private halves exist only as environment secrets. The operator creates a fine-grained token limited to the ops repository with environment write access and the shortest expiry, stores it as `CI_BOOTSTRAP_TOKEN` in `ci-bootstrap`, and revokes it and deletes the secret after the run. The run refuses to replace an existing identity secret. Commit the public recipient to the ops `.sops.yaml` and the public key to the tfvars `admin_ssh_public_keys` lists and the inventory variables.
3. Run `sops updatekeys` over every `config/*.secrets.sops.yaml`, then dry-run and deploy `baseline` so that every node accepts both admin keys.
4. Import the live Tailnet policy byte for byte into `tailnet/policy.hujson`, then add `tag:ci-tofu` and `tag:ci-deploy` with their `tagOwners` and grants.
5. Issue the provider tokens and record a catalog entry for each environment secret. Then run the validator on the ops repository.

## Revocation

- **CI SSH key:** remove it from `admin_ssh_public_keys` and the inventory list, then deploy with the operator key. Do not deploy the removal with the CI key: `baseline` removes that key during the run, and the later plays lose their connection. `baseline` writes the admin `authorized_keys` exclusively from the list, so the key disappears from every node while the operator key stays. Delete the secret from `deploy-check` and `deploy`.
- **CI age identity:** remove the CI recipient from `.sops.yaml`, run `sops updatekeys` and rotate the data key (`sops rotate -i`) of every affected document, then replace the credentials that the identity could read. Delete the secret from `deploy-check`, `deploy` and `ops-secrets`.
- **Tailnet and provider tokens:** revoke each one at its provider, following the `revoke_procedure` in its catalog entry, then delete the environment secret.
