# terraform — cloud resource layer

## Design decisions

**Per-provider root, identical outputs** — Terraform module sources can't
be variable-driven, so each provider gets its own root under
`providers/<name>/`. Output schema is fixed: `server_ipv4`, `server_ipv6`,
`admin_user`, `ssh_port`, `server_hostname`. `scripts/render-inventory.sh` is
therefore provider-neutral.

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

**Floating IP is optional** — `var.use_floating_ip` per provider. Cheap
operators skip it; blue-green operators turn it on.

**Typed listener contract crosses the cloud/runtime boundary** — `public_listeners` in tfvars is the provider-edge allowlist. Its resolved Terraform output is rendered into inventory, verified against Ansible's enabled listener manifest before deploy, and used by nftables and security verification.

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
  remote restic repo persists. Destroy + recreate gives you back state
  via `make restore`.
- **Provider auth via env vars only** — never `provider` block credentials
  in code. The block must be empty (the provider auto-reads env).
- **`tf-test`** uses `mock_provider`** — these tests verify the *shape*
  of plans, not that the cloud provider behaves correctly. Real-deploy
  validation is separate (`docs/CI-REAL-DEPLOY.md`).
- **Raw Terraform bypasses environment selection** — operator paths must use `scripts/terraform-env.sh` (or the Makefile / `vpnd` wrappers), never direct `terraform output`, `plan`, or `apply`.
- **A provider rule without the contract is a drift bug** — do not add static listener ports to a provider firewall or nftables template; update `public_listeners` and the runtime role configuration together.
