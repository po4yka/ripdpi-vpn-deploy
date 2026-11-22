## Context

See `proposal.md`. Today the operator MacBook holds Terraform state (local backend, one workspace per `PROVIDER`/`ENV`, see `scripts/terraform-env.sh`), the operator kit under `secrets/local/` (`docs/how-to/local-operator-kit.md`), the only SOPS age identity in daily use, the admin SSH identity and the provider tokens. The public repository already has a protected-environment pattern for credentialed CI (`ci-real-deploy` in `.github/workflows/ci-disposable-deploy.yml`, capability `ci/credentialed-deploy-gating`) and a Tailnet hand-off for CI deploys (`DEPLOY_CI_TAILNET_HANDOFF`). Earlier temporary Vultr-only CONNECT proxies on node-b and node-c are recorded in the private kit as prior art for the egress design.

The operator chose: GitHub Actions on GitHub-hosted runners as the executor; a dedicated secretless egress VPS with a fixed IP for provider APIs (not observer-a); a migration to OpenTofu for client-side state encryption.

## Goals / Non-Goals

- Goal: every operation that today needs the MacBook (plan, apply, destroy, dry-run, deploy, verify, acceptance, rotate-*, issue-*, DNS changes) runs from the private ops repository CI, triggered by a Claude cloud session through Git.
- Goal: every CI identity is distinct from the operator's own and is revocable alone.
- Non-goal: self-hosted runners, a long-lived control-plane server holding secrets, or a public admin panel.
- Non-goal: moving the observer or the Kuma backup; they are unchanged.

## Decisions

- Split into seven child changes so each one is reviewable and has one gate. Rejected: one change, because its tasks file would cross six layers and could not be verified in one pass.
- Order (also the `blocked_by` edges in `REQ-WFO-ORDER`):

| Child | Task | Depends on | Why |
|---|---|---|---|
| W1 ops repository and kit mapping | `private-ops-repository-w1` | — | Every later change needs a private home for config, receipts and workflows. |
| W2 OpenTofu toolchain | `opentofu-toolchain-w2` | — | Pure toolchain swap, provable offline; encryption needs OpenTofu. |
| W3 encrypted B2 state | `encrypted-remote-state-w3` | W1, W2 | Needs `tofu` encryption and a private place for backend config and receipts. |
| W4 CI identities and environments | `ci-identities-environments-w4` | W1 | Environments live in the ops repository. |
| W5 egress proxy node | `egress-proxy-node-w5` | W2, W3, W4 | The node is an OpenTofu resource with remote state; its Tailnet grant names the CI tag from W4. |
| W6 Porkbun DNS root | `porkbun-dns-root-w6` | W2, W3, W5 | New root starts on remote state; Porkbun API calls go through the egress allowlist. |
| W7 ops workflows and cloud environment | `ops-repository-workflows-w7` | W1, W3, W4, W5, W6 | Assembles everything into runnable workflows and the cloud trigger path. |

- Split of trust: the cloud session edits non-secret settings only, through pull requests in the ops repository. CI generates or decrypts secrets inside a job that runs in a protected environment. Rejected: giving the cloud session a scoped token, because its environment variables are readable inside its VM.

## Contracts and ownership

- Public repository: `terraform/` (renamed tool, same layout), `mise.toml`, `.github/workflows/{ci,tf-policy,daily-security,drift}.yml`, `Makefile`, `scripts/*tf*`, new `ansible/roles/egress-proxy/`, new `terraform/dns/porkbun/`, docs. Each child owns its own paths; shared files (`Makefile`, `mise.toml`, `docs/reference/testing.md`, `.sops.yaml` examples) are edited in the order W1, W2, W3, W4, W5, W6, W7.
- Private ops repository: config, receipts, workflows, environment definitions. Defined in W1.

## Risks / Trade-offs

- GitHub becomes a single point of control → `REQ-WFO-BREAK-GLASS`; W3 and W5 document break-glass from the MacBook.
- A compromised CI environment can mutate the fleet → mutations run only after the operator merges, enforced by an owner-only merge ruleset (W4), and per-identity revocation.
- More moving parts (B2, egress VPS) → each has a documented failure mode and a fallback path.

## Migration Plan

Children land in the table order. Live steps (creating the ops repository, buckets, keys, the egress node, Tailnet policy edits, state migration) each need explicit operator authorization at action time; this planning change authorizes none of them. Rollback for each child is in its own design.

## Open verification questions

The children list their own open questions; the program-level ones are:

1. Can a Claude cloud session dispatch a workflow, or only push and open pull requests? W7 designs the PR/push-triggered path either way.
2. Can B2 enforce the W3 lock across CI and workstation writes under the intended key scopes and retention policy? W3 keeps local state authoritative until the full probe succeeds.
3. Does every provider client honour `HTTPS_PROXY` when it runs under OpenTofu? W5 proves it per provider before enabling allowlists.
