---
name: security-review
description: Pre-merge security review of a diff against this repo's threat model, with a checklist and verdict format. Use when reviewing or finishing a change that touches secrets or SOPS tooling, Terraform or cloud-init, network exposure (listeners, firewall, rate limits), per-device client material, Ansible tasks that handle secrets, or vpnd. Not for style or performance-only changes.
---

# Security review (vpn-deploy)

The adversary controls the network path, inspects traffic metadata, and actively probes endpoints. Nodes are disposable; the repository plus SOPS secrets is the recovery key, so a leak into Git, Terraform state, or logs is permanent. The hard rules in `AGENTS.md` define what is forbidden; this skill is how to check a diff against them.

Review the diff (`git diff <base>...HEAD`), run the gates below that apply, and report a verdict: **APPROVE**, **REQUEST CHANGES** (fixable finding), or **REJECT** (the change's direction violates a hard rule, e.g. a CDN baseline, a public admin panel, or a cross-layer shortcut). Give file:line evidence for each finding.

## Checklist

- **Secrets in Git or state.** No keys, tokens, UUIDs, shortIds, private IPs or hostnames in tracked files. Only the example, schema, README, and `.sops.yaml.example` under `secrets/` are tracked. `make validate` runs gitleaks over history and the staged tree.
- **Secret schema.** New secret keys appear in `secrets/prod.secrets.example.yaml` and `secrets/schema.json`; `scripts/check-secrets-coverage.py` and `scripts/validate-secrets.py` pass (both run in `make ci-fast`).
- **Terraform and cloud-init.** Nothing secret in `user_data`, variables, or outputs; outputs stay minimal. `make tf-policy-verify` runs the Conftest policies in `terraform/policy/` (including `no_secrets_in_user_data.rego`, `admin_port.rego`, `ssh_cidrs.rego`).
- **Ansible.** Tasks that template, register, or print secret values set `no_log: true`. Decrypted secrets exist on disk only as the operator-local `SECRETS_FILE` (mode 0600, default under `${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/vpn-provision-<uid>/`, see `docs/SECRETS.md`); nothing copies it elsewhere.
- **Layer boundaries.** Terraform does not run Ansible or SSH (`local-exec`/`remote-exec`), cloud-init does not carry service config or secrets, and `vpnd` shells out to Make targets instead of reimplementing them.
- **Per-device material.** UUIDs, REALITY shortIds, AmneziaWG peer keys, and subscription tokens are generated per device (`scripts/new-client.sh`, `make issue-sub-token`), never copied from another device; revocation stays per device.
- **Exposure.** A new public listener is added to the Terraform `public_listeners` contract and the runtime role together (see `terraform/CLAUDE.md` and `ansible/roles/firewall/CLAUDE.md`). Admin, metrics, and status endpoints bind to loopback or the tailnet only. Rate limiting is single-layer per surface: browser-facing HTTP routes (`subscription-host`, the nginx-xhttp evaluation path) use nginx `limit_req`; `policy-ratelimit` (nftables) only throttles blackhole-routed client abuse and is not probe defence (`ansible/roles/policy-ratelimit/CLAUDE.md`).
- **Versions.** New binaries and packages are pinned and checksum-verified. The Xray pin is the SOPS secret `xray.version`; `ansible/roles/xray/defaults/main.yml` holds only an empty sentinel. Bumps update `docs/XRAY-RELEASE-LINE.md` and pass `scripts/check-xray-breaking-changes.py`. Pre-releases go to staging only.
- **Bypass markers.** No `--no-verify`, `gitleaks:allow`, unjustified `# shellcheck disable=`, or skipped pre-commit hooks in the diff or its instructions.
- **Transport baseline.** No CDN-fronted path promoted to P0/P1 (`docs/CDN-DECISION.md`).

## Common findings

| Finding | Severity | Fix |
|---|---|---|
| Secret value reaches Ansible output or a debug task | HIGH | `no_log: true`; re-run the play and check the operator-side output |
| Hard-coded UUID or token in a test fixture | HIGH | Generate it in the fixture; keep production profiles free of it |
| Listener opened in a provider firewall or nftables template without the contract | HIGH | Add it to `public_listeners` and the role together |
| Pre-release version on a production toggle | HIGH | Move it to a staging profile |
| Second rate-limit layer stacked on an HTTP route | MEDIUM | Keep nginx `limit_req` only for that surface |
| New role without an `enable_*` toggle in `ansible/group_vars/all.yml` | LOW | Add the toggle; enabling a profile is a config change |
| CDN added as a P0/P1 backend | REJECT | See `docs/CDN-DECISION.md` |
