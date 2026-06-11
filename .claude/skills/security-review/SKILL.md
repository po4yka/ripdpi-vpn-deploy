---
name: security-review
description: Security review against the vpn-deploy threat model (RU-internet / TSPU-aware). Catches secrets-in-git, layer-boundary breaches, shared per-device material, admin-panel exposure, and CDN-as-baseline mistakes. Use before any merge that touches secrets, Terraform, cloud-init, Ansible runtime state, or vpnd. vpn-deploy project variant.
---

# Security Review (vpn-deploy)

Threat model: an active state-grade adversary (RU TSPU class) controls the network path,
inspects metadata, and probes endpoints. Nodes are disposable; the repo is the recovery key.

## When to activate

- Adding or modifying a secret key, UUID, REALITY shortId, AmneziaWG peer key
- Changing a Terraform provider, cloud-init template, or Ansible role
- Adding a new role / playbook / vpnd subcommand
- Changing nftables, sshd_config, or any baseline hardening
- Touching `subscription-host`, `honeypot`, or `cdn-front` roles
- Any change to `secrets/*.yaml` or `.sops.yaml`
- Anywhere you see `--no-verify`, `gitleaks: ignore`, or `# nosec`

## Hard rules — failing any one is a `REQUEST CHANGES`

### 1. Secrets

- No secrets in git, Terraform state, TF vars/outputs, cloud-init `user_data`, Ansible
  debug, or screenshots. Provider credentials live in env vars only — never in
  `terraform.tfvars`.
- SOPS+age is the only at-rest format. Decrypted secrets are read into memory and never
  written to disk outside `/run/...`.
- `gitleaks` runs in CI and gates merge. Do not bypass.
- Verify: `make ci-fast` runs `scripts/check-secrets-coverage.py` and
  `scripts/validate-secrets.py`. Both must pass.

### 2. Per-device material

- One UUID, one REALITY shortId, one AmneziaWG peer key per device. **Never shared.**
- Recipient pages (`vpnd/templates/recipient.html`) must render device-specific URIs;
  reuse across devices is a leak.
- Subscription URLs must be unique per device and rotated on revocation.

### 3. Layer boundaries

```
Terraform -> cloud-init -> Ansible -> SOPS+age -> vpnd
```

Nothing crosses except via documented interfaces.

- Terraform owns cloud resources. Does NOT own runtime state.
- cloud-init owns first-boot. Does NOT own service config or secrets.
- Ansible owns runtime state. Does NOT own cloud resources.
- vpnd is convenience only. Does NOT bypass Make / Terraform / Ansible.

Cross-layer violations (e.g., Ansible creating cloud resources, Terraform writing secrets
into `user_data`) are a `REJECT`.

### 4. Exposure

- No public admin panel. Ever. Internal-only or wireguard-fronted only.
- No remote installer piped to root shell (`curl ... | sudo bash` patterns).
- Probe endpoints (subscription-host, etc.) must rate-limit at nftables level via the
  `policy-ratelimit` role — application-layer rate limiting is insufficient.

### 5. RU baseline

- CDN is **not** the RU baseline. See `docs/CDN-DECISION.md`. P0 = VLESS+REALITY+Vision
  TCP/443. P1 = nginx+XHTTP direct. CDN-fronted paths are non-RU profiles only.
- Hysteria2 (P2) is UDP/443 — confirm UDP egress before enabling.
- AmneziaWG cohort tuning lives in the SOPS-encrypted `amneziawg_secrets.{jc,jmin,jmax,s1,s2,h1..h4}`
  block — wrong values = trivial DPI detection. See `docs/AWG-COHORTS.md`.

### 6. Versions

- All package versions pinned. Pre-releases through staging only — never on production
  toggles in `ansible/group_vars/all.yml`.
- `ansible/roles/xray/defaults/main.yml` is the canonical Xray pin. Bumping requires a
  PR with `docs/XRAY-RELEASE-LINE.md` updated.

## Review checklist

- [ ] `git diff` reviewed for hardcoded keys, tokens, UUIDs, IPs, hostnames
- [ ] No new files in `secrets/` are unencrypted (look for `sops:` block in YAML)
- [ ] Terraform `state` and `user_data` rendered values do not contain secrets
- [ ] Ansible tasks that handle secrets have `no_log: true`
- [ ] Any new role has a molecule scenario or a justified skip in `docs/TESTING.md`
- [ ] Any new endpoint is rate-limited at nftables OR has a documented exception
- [ ] Per-device material is generated, not copied from another device
- [ ] No `--no-verify`, no `gitleaks:ignore`, no skipped pre-commit hooks
- [ ] No mention of Claude, Claude Code, or Anthropic in commits (root `CLAUDE.md` rule)
- [ ] Conventional Commit footer does not contain `Co-Authored-By:` trailers

## Common findings

| Finding | Severity | Fix |
|---|---|---|
| Hardcoded UUID in test fixture | HIGH | Move to generated fixture, ensure not in prod profile |
| Terraform output exposes admin IP | MEDIUM | Wrap in `sensitive = true` and verify state encryption |
| Ansible debug task leaks env var | HIGH | Add `no_log: true`, audit `journalctl -u ansible-pull` |
| New role missing `enable_<role>` toggle | LOW | Add to `group_vars/all.yml`, default to `false` |
| Pre-release version on prod toggle | HIGH | Move to staging toggle only |
| CDN added as P0/P1 backend | REJECT | See `docs/CDN-DECISION.md` |

## See also

- Root `CLAUDE.md` — hard rules
- `docs/CDN-DECISION.md` — why CDN is not the baseline
- `[[linux-hardening]]` — baseline role hardening
- `[[bash-scripting]]` — scripts/ hardening
