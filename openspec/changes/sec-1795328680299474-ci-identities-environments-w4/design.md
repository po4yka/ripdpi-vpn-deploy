## Context

See `proposal.md`. The public repository already gates credentialed CI with the protected `ci-real-deploy` environment (`.github/workflows/ci-disposable-deploy.yml`, capability `ci/credentialed-deploy-gating`, checker `scripts/check-ci-deploy-gate.py` with `has_required_reviewer`) and joins the Tailnet with an OAuth client (`CI_TAILSCALE_OAUTH_CLIENT_*`). Nodes get one admin key through `admin_ssh_public_key` in cloud-init; `ansible/roles/baseline` owns the admin account. The Tailnet policy is edited in the admin console today. The scoped SOPS files are encrypted to the operator's age recipient (`secrets/.sops.yaml.example` shows the shape).

## Goals / Non-Goals

- Goal: CI can do everything the operator does, with identities the operator can revoke one by one.
- Non-goal: workflows themselves (W7); egress allowlists (W5).

## Decisions

- Environment matrix:

| Environment | Reviewer | Secrets | Used by |
|---|---|---|---|
| `tofu-plan` | no | `TF_VAR_state_passphrase`, B2 `state-plan` key, read-only provider tokens (write tokens where no read-only exists), `tag:ci-tofu` join | PR plan, scheduled drift |
| `tofu-apply` | yes | passphrase, B2 `state-apply` key, provider write tokens, `tag:ci-tofu` join | apply, destroy |
| `deploy-check` | no | CI age identity, CI SSH key, `tag:ci-deploy` join | dry-run, verify, acceptance |
| `deploy` | yes | same classes as `deploy-check` | deploy |
| `ops-secrets` | yes | CI age identity only | offline credential preparation |
| `tailnet-policy` | yes | policy-file push identity | Tailnet policy apply |

  Restrict each environment to the default branch. Revocation removes the age identity from all three holders and the SSH key from both deploy environments.
- Untrusted pull-request input: PR-time jobs use `pull_request_target` from same-repository branches, check out the PR head only as data in a separate directory, and run `scripts/validate-ops-environments.py --pr` before any secret step. Rejected: `pull_request` with environment secrets, because the PR could edit the workflow; GitHub's branch policy blocks it anyway.
- Classify the complete diff against the trusted base before starting a credentialed job. Automatic previews accept only enumerated, typed fields (for example a boolean protocol toggle) on existing trusted targets. Reject unexpected paths, field changes, renames, deletions and symlinks from that path. Inventory targets, SSH config and host pins, backend endpoints, recipient policy, workflows, Make inputs and the upstream pin require approval bound to the exact revision. A new revision needs a new decision. Build the automatic preview from base trust data plus the validated values.
- CI age identity: generated once in the `ops-secrets` job context (authorized live step), public recipient committed to `.sops.yaml`, private identity stored as an environment secret in the three age-key environments and nowhere else. `sops updatekeys` over every `config/*.secrets.sops.yaml`. On removal, update the recipients and rotate the SOPS data key in every affected document before replacing exposed credential values. Verify with a retained pre-revocation fixture data key.
- CI SSH key: ed25519, generated in a separately approved deploy bootstrap job; public half in the ops repository tfvars `admin_ssh_public_keys` and in group vars. `baseline` writes the admin `authorized_keys` with `exclusive: true` from the list. Molecule proves add and revoke. Rejected: SSH certificates with a CA, because there is no CA in the fleet today and it adds a signing service.
- Tailnet: prefer workload identity federation in `tailscale/github-action` (`id-token: write`, no stored secret); fall back to OAuth clients with the `auth_keys` scope bound to one tag. Policy additions:

```json
{
  "tagOwners": { "tag:ci-tofu": ["autogroup:admin"], "tag:ci-deploy": ["autogroup:admin"], "tag:egress": ["autogroup:admin"] },
  "grants": [
    { "src": ["tag:ci-tofu"], "dst": ["tag:egress"], "ip": ["tcp:3128"] },
    { "src": ["tag:ci-deploy"], "dst": ["tag:vpn-node"], "ip": ["tcp:<management-ssh-port>"] },
    { "src": ["tag:ci-deploy"], "dst": ["tag:egress"], "ip": ["tcp:<management-ssh-port>"] }
  ]
}
```

  The node tag name and SSH port are taken from the current policy during implementation. The policy file moves into the ops repository (`tailnet/policy.hujson`) and `tailscale/gitops-acl-action`, pinned by SHA, tests it on PRs and applies it on merge in `tailnet-policy`. The first push must be a byte-equivalent import of the live policy (the action's test mode against the live tailnet).
- Provider tokens (least privilege, recorded in the catalog):

| Provider | Plan token | Apply token |
|---|---|---|
| Hetzner | project token, Read | project token, Read & Write |
| Scaleway | IAM application, read-only permission sets, project-scoped | IAM application, write sets for the used products, project-scoped |
| UpCloud | sub-account with API access (read-only if offered) | sub-account with server, storage, network and firewall rights |
| Vultr | sub-user API key (read-only ACL if offered) | sub-user API key with server, firewall, reserved-IP ACLs |
| Backblaze | `state-plan` key | `state-apply` key |
| Porkbun | key with read permission on managed domains (W6) | key with DNS permission on managed domains |
| Tailscale | none | policy-push identity only in `tailnet-policy` |

## Contracts and ownership

- Public repository: `scripts/validate-ops-environments.py`, `tests/unit/test_validate_ops_environments.py`, `terraform/providers/*/{variables,main}.tf`, `terraform/shared/cloud-init.yaml.tftpl`, `terraform/policy/` (key list policy), `ansible/roles/baseline/**` and its Molecule scenario, `docs/reference/secrets.md`, new `docs/how-to/ci-identities.md`.
- Ops repository: `.sops.yaml`, re-encrypted `config/*.secrets.sops.yaml`, `config/tfvars/**` key list, `tailnet/policy.hujson`, `catalog.json`.
- Shared `Makefile` lane: after W3 (only if a new target is needed; none planned).

## Risks / Trade-offs

- A no-reviewer environment still holds write-capable tokens for providers without read-only tokens → workflow code always comes from the default branch, PR data is validated, and W5 restricts provider APIs to the egress IP so a leaked token is less useful.
- Re-encrypting to a CI recipient widens who can decrypt deployment secrets → the CI identity lives only in reviewer-gated or default-branch-only environments; revocation implies rotation.
- Moving the Tailnet policy into Git can lock the operator out by a bad push → the GitOps action's test step plus `tailnet-policy` approval; the admin console stays the break-glass path.

## Migration Plan

1. Land validator, Terraform list input, baseline role change and docs (offline checks: unit tests, `make tf-test`, `make molecule-test ROLE=baseline`, `make snapshot-check`).
2. Authorized live steps, in order: create environments with reviewers and branch policies; generate CI age and SSH identities inside CI; `sops updatekeys` and commit; deploy baseline with both admin keys (dry-run first); import the Tailnet policy and add tags and grants; issue provider tokens; record catalog entries and receipts.
3. Rollback: remove the CI SSH key and age recipient, rotate affected SOPS data keys and exposed credentials, then remove the environments. Verify operator access.

## Open verification questions

1. Do UpCloud sub-accounts and Vultr sub-users offer read-only API permissions? If not, `tofu-plan` holds write-capable tokens for them (accepted risk above).
2. Does `tailscale/github-action` workload identity federation work for this tailnet's plan, so no OAuth secret is stored?
3. Does `pull_request_target` from a same-repository branch pass an environment branch policy of "default branch only"? GitHub evaluates the base ref for that event; confirm with a no-secret test environment first.
4. Can the Claude cloud session open pull requests in the ops repository whose head branch is in the same repository (required for the `pull_request_target` path)?
