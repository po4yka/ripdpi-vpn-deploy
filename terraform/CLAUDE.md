# terraform — cloud resource layer

## Design decisions

**Per-provider root, identical outputs** — Terraform module sources can't
be variable-driven, so each provider gets its own root under
`providers/<name>/`. Every root exports the same outputs: `server_ipv4`,
`server_ipv6`, `honeypot_ipv4`, `admin_user`, `ssh_port`, `server_hostname`,
`zone`, `public_listeners`. `scripts/render-inventory.sh` reads all but `zone`
and is therefore provider-neutral.

**SSH port is one cross-layer input** — `var.ssh_port` configures cloud-init,
the provider edge allowlist, the canonical Terraform output, inventory's
`ansible_port`, cloud-init waiting, and the on-host nftables rule. Default 22
preserves existing deployments. Because server resources intentionally ignore
later `user_data` drift, changing this creation-time input triggers node
replacement and is held by `prevent_destroy`; use the normal disposable-node
blue-green path rather than changing a live node in place.

**Local state per provider and environment** — we don't trust remote state with VPN infrastructure. `ENV=prod` deliberately remains Terraform's legacy `default` workspace; every other `ENV` maps to its own same-named workspace. Initialize a new environment with `make PROVIDER=<provider> ENV=<env> init` before any plan, apply, or output. State is backed up via `make backup-state` (age-encrypted). Lose state → re-import (`docs/RUNBOOK-incident.md`).

**No `local-exec` / `remote-exec`** — Terraform stays declarative.
cloud-init owns first-boot bootstrap; Ansible owns runtime state.

**Secondary public IP is opt-in per root** — `additional_public_ip = true`
allocates the honeypot address; there is no generic floating-IP toggle.
Blue-green moves follow the disposable-node path instead.

**Typed listener contract crosses the cloud/runtime boundary** — `public_listeners` in tfvars is the provider-edge allowlist. Its resolved Terraform output is rendered into inventory, verified against Ansible's enabled listener manifest before deploy, and used by nftables and security verification. An empty contract fails the plan; the historical implicit default set survives only behind the explicit `use_legacy_public_listeners = true` opt-in.

**New providers follow one recipe** — create `providers/<name>/` exporting
the same outputs so `render-inventory.sh` keeps its generic path (add provider
code there only for incompatible keys or a guest-convergence check such as
Vultr's secondary IPv4). Validate constrained inputs with `contains([...])`
allowlists like the existing roots, add `mock_provider` cases under `tests/`
for `make tf-test`, and keep DNS inside the owning root behind an explicit
opt-in variable (`providers/vultr/dns.tf`). Add the name to every hardcoded
provider list: Makefile loops, the `ci.yml` provider matrices,
`scripts/terraform-env.sh`, `scripts/backup-tf-state.sh`,
`scripts/tf-policy-test.sh`, `scripts/destroy.sh`, the liveness allowlists
(`contract/protocol-liveness.schema.json`, `scripts/liveness_profiles.py`,
`scripts/install_liveness_sentinel.py`), `vpnd/src/config.rs`, and the
provider tuples in `tests/unit/` (for example
`test_provider_listeners_parity.py`). This list drifts, so finish with
`rg -il scaleway --hidden -g '!terraform/providers/**'` and cover every
enumeration it finds. Then add a `docs/PROVIDER-NOTES.md` row and
`providers/<name>/CLAUDE.md` with its `AGENTS.md -> CLAUDE.md` symlink. Roots
never compose each other as modules.

## What's done well

- **Validation blocks on every input** — region, plan, CIDR, key formats
  all validated at plan time, not apply time.
- **Outputs are minimal** — only what the Ansible layer needs. No
  back-channel information (e.g., no API keys in outputs).
- **No version constraint on the cloud provider** — pinned in
  `versions.tf` per provider root; major bumps go through staging.

## Pitfalls

- **TF state contains the SSH public key fingerprint**, but never the
  private key. If a state file leaks, the recovery is to rotate the SSH
  key, not just delete state.
- **Cloud-init `user_data` is plaintext in state** — never put secrets
  there. Even with state encryption, this is operator-readable.
- **`terraform destroy` does not remove backups** — the `backup` role's
  remote restic repo persists. Destroy + recreate restores node data
  from that restic repository (`ansible/roles/backup/CLAUDE.md`,
  `docs/RUNBOOK-incident.md`); there is no `make restore` target.
- **Provider auth via env vars only** — never `provider` block credentials
  in code. The block must be empty (the provider auto-reads env).
- **`tf-test`** uses `mock_provider`** — these tests verify the *shape*
  of plans, not that the cloud provider behaves correctly. Real-deploy
  validation is separate (`docs/CI-REAL-DEPLOY.md`).
- **Raw Terraform bypasses environment selection** — operator paths must use `scripts/terraform-env.sh` (or the Makefile / `vpnd` wrappers), never direct `terraform output`, `plan`, or `apply`.
- **A provider rule without the contract is a drift bug** — do not add static listener ports to a provider firewall or nftables template; update `public_listeners` and the runtime role configuration together.
