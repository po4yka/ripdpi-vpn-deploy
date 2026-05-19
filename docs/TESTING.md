# Testing — what's covered and what isn't

The repo's defense-in-depth philosophy applies to its own correctness: every
config, role, and script is checked at multiple layers before it can hit a
real VPS. This doc enumerates each layer and where coverage gaps exist
(with explicit reasons).

## Coverage matrix

| Artifact | Static check | Render check | Functional test (molecule) | Notes |
|---|---|---|---|---|
| **Terraform — UpCloud** | `terraform fmt -check` + `terraform validate` + `terraform test` (CI) | n/a | n/a | CI matrix runs all three providers. |
| **Terraform — Hetzner / Vultr** | `terraform fmt -check` + `terraform validate` + `terraform test` (CI) | n/a | n/a | Native tests cover server/output invariants, honeypot IP allocation, firewall toggles, SSH scoping, XHTTP port behavior, and port validation. |
| **cloud-init template** | `cloud-init schema --config-file` (CI) | rendered from the Terraform template with CI stub vars | n/a | |
| **Ansible playbooks** | `ansible-lint` + `ansible-playbook --syntax-check` (CI) | n/a | n/a | site.yml asserts VPN_SECRETS_FILE is set; CI passes the example schema as a stub. |
| **Ansible role: baseline** | ansible-lint | render check | **molecule** (debian13 + ubuntu24.04) | tests sshd hardening, sysctl, timesync, IPv4 forwarding gating. |
| **Ansible role: firewall** | ansible-lint | render check | **molecule** | tests nftables.conf parse + presence of expected ports. |
| **Ansible role: xray** | ansible-lint | render check (JSON validity) | **molecule** (template-only, stub binary) | tests config.json shape, systemd unit, symlink rollback. |
| **Ansible role: nginx-xhttp** | ansible-lint | render check (`nginx -t`) | **molecule** (idempotence + verify) | self-signed cert generated in pre_tasks; verifies no Cloudflare-specific directives leaked into RU baseline. |
| **Ansible role: cdn-front** | ansible-lint | render check (`nginx -t`) | **molecule** | opt-in tactical Cloudflare-fronted XHTTP role; not part of the RU baseline or required CI molecule matrix. |
| **Ansible role: hysteria** | ansible-lint | render check | **molecule** (template-only, stub binary) | verifies clients render + Salamander disabled by default. |
| **Ansible role: amneziawg** | ansible-lint | render check | **molecule (syntax+create only)** | full converge needs a kernel TUN device + golang build of amneziawg-go that Docker can't reliably provide; scenario exercises task-file structure so regressions are caught early, deeper testing happens against a real VPS. |
| **Ansible role: monitoring** | ansible-lint | render check | **molecule** | verifies node_exporter + journald + logrotate. |
| **Ansible role: watchdog** | ansible-lint + `bash -n` (verify play) | render check | **molecule** + idempotence | verifies probe script syntax + env file perms + topic rendering. |
| **Ansible role: backup** | ansible-lint | render check | **molecule** | verifies restic init + remote-sync block correctly *omitted* when disabled. |
| **Ansible role: subscription-host** | ansible-lint | render check (`nginx -t`) | **molecule** + idempotence | verifies revoked-tokens map + rate-limit zone + payload dir perms. |
| **Ansible role: geodata** | ansible-lint | render check | **molecule (syntax-only sequence)** | converge would couple to upstream URL availability + rate limits; scenario still exercises task-file structure. Use `molecule converge` manually for ad-hoc full-path testing. |
| **Ansible role: naive** | ansible-lint | render check (Caddyfile syntax NOT validated — Caddy not in CI matrix) | **molecule (syntax-only sequence)** | xcaddy from-source build skipped in CI to avoid Go-module-network flakiness; `molecule converge` runs it locally. |
| **Ansible role: honeypot** | ansible-lint | render check | **molecule** + idempotence | verifies service active, listener bound to configured port, script installed. |
| **Ansible role: probe-ratelimit** | ansible-lint | render check | **molecule** + idempotence | verifies daemon script + systemd unit + active state. nftables `probe_offenders` set is exercised in the full-stack scenario. |
| **Ansible role: warp-outbound** | ansible-lint | render check | **molecule (syntax-only sequence)** | Cloudflare WARP installer expects systemd-networkd + a registerable endpoint not available in CI; structure validation only. |
| **Full stack** | ansible-lint | render check | **`make molecule-full-stack`** (manual) | runs the entire `site.yml` end-to-end inside a privileged Debian-13 container with NET_ADMIN; verifies every enabled service is up + listening. See `ansible/molecule/full-stack/`. |
| **Shell scripts (39)** | `bash -n` syntax + **`shellcheck -s bash -S warning`** (CI) | n/a | n/a | every shell script in `scripts/` runs through shellcheck. |
| **Python validators** | implicit — they validate everything else | n/a | n/a | |
| **Secrets schema** | **`scripts/check-secrets-coverage.py`** | n/a | n/a | Walks every Jinja2 template, ensures every top-level variable is declared in `secrets/prod.secrets.example.yaml`, `group_vars/all.yml`, or a role's `defaults/main.yml`. |
| **Jinja2 templates (27)** | **`scripts/check-templates-render.py`** | renders all 27 role templates against synthetic + example data | n/a | Catches Jinja syntax errors, JSON-invalid output for `*.json.j2`, nginx parse errors for site configs. |
| **Cohort group_vars** | render check (group_vars/all.yml + cohort file are merged into render env) | n/a | n/a | If a cohort file references a flag the role doesn't accept, render fails. |
| **YAML formatting** | **yamllint** (CI) | n/a | n/a | uses `.yamllint.yml` profile. |
| **Secret leak detection** | **gitleaks** with custom rules (CI + pre-commit) | n/a | n/a | Custom rules: VLESS/Trojan/Hysteria URIs, REALITY priv keys, WG priv keys, age-secret-key, subscription tokens. |
| **Placeholder leak** | **`scripts/pre-commit-placeholder-scan.py`** (pre-commit) | n/a | n/a | Rejects any staged file (outside the schema example + generator scripts) that carries a `REPLACE_WITH_*` token. |
| **Decrypted-secrets audit** | **`scripts/spot-check-secrets.py`** (gating `make deploy`/`verify`) | walks the decrypted YAML | n/a | Placeholder check, cert expiry, RSA modulus match, H1..H4 type, password length. Bypass with `SKIP_PRECHECK=1`. |
| **Cert hygiene** | **`scripts/check-certs.sh`** (gating `make deploy`/`verify`) | openssl-driven | n/a | SAN coverage, expiry < 14 days, self-signed detection, modulus match across nginx_xhttp / hysteria / naive. |
| **Pinned-binary reproducibility** | **`.github/workflows/reproducible-build.yml`** (CI) | go build + sha256 compare | n/a | Three jobs: xray (from-source rebuild → soft-warn on bytewise drift), hysteria (hard-fail on release-asset sha256 mismatch), RealiTLScanner (same). |
| **Real-VPS end-to-end** | **`.github/workflows/real-vps-deploy.yml`** (workflow_dispatch / `ci-real-deploy` label) | provision → site.yml → verify → destroy | n/a | Approximates production deploy as closely as Actions allows. Ephemeral UpCloud VPS per run. Does not currently run smoke-test. See `docs/CI-REAL-DEPLOY.md`. |
| **Kill-switch validation** | **`scripts/check-singbox-killswitch.py`** (operator-driven) | static JSON analysis | n/a | Verifies auto_route + strict_route, route.final ≠ direct, DNS detour ≠ direct, no IPv6-only outbounds. |
| **vpnd Rust crate (114 tests)** | `cargo clippy --release --all-targets -- -D warnings` (CI) | n/a | `cargo test --release` (CI, blocking) | Covers runner builders (process, make, ansible, terraform, sops), config discovery, secrets parsing, registry round-trip, QR encode, update-cache, completions snapshot, ai-docs emit, host CRUD, doctor bundle, share bundle. Plus 4 proptest properties for `urlencode` round-trip and `redact_secrets` per-line invariants. |
| **vpnd mutation testing (weekly)** | `cargo mutants` (`.github/workflows/mutants.yml`) | n/a | n/a | Scheduled Monday 08:00 UTC. Targets `src/runner/**`, `src/commands/doctor.rs`, `src/pages/qr.rs`, `src/secrets.rs`. Non-blocking — surviving mutants posted to a rolling tracking issue with label `automation:mutation-testing`. |
| **Python unit tests (91 tests, 1 skip)** | pytest (CI) | n/a | n/a | Covers emit-singbox, SOPS round-trip, render-inventory, relay/fallback, subscription token revocation lifecycle, tspu-canary, scan-reality-targets, singbox kill-switch. (Shell orchestrator dry-runs migrated to bats — see below.) |
| **Shell-orchestrator bats tests (29 tests)** | `bats tests/bats/` (CI, blocking) | n/a | n/a | Covers `blue-green.sh --dry-run`, `fleet-rotate.sh --dry-run`, `age-recovery-combine.sh` 3-of-5 round-trip, `restore.sh --dry-run` (path-A + path-B). Uses the same `tests/stubs/bin/` PATH-prepend harness as the Python tests. bats-support v0.3.0 + bats-assert v2.1.0 vendored under `tests/bats/test_helper/`. |
| **Terraform policy (cross-provider, Conftest)** | `.github/workflows/tf-policy.yml` per PR | n/a | n/a | Runs each provider's native Terraform tests with `mock_provider`, then `conftest verify -p terraform/policy/` for Rego syntax/unit-test validation. The workflow intentionally does not run real provider plans against example tfvars because those require operator credentials and provider API access. `make tf-policy` for local. |
| **Container image scanning (Trivy)** | `.github/workflows/image-scan.yml` per PR | n/a | n/a | Dynamically enumerates base images from `ansible/roles/*/molecule/*/molecule.yml`. Uploads HIGH/CRITICAL SARIF to the Security tab without blocking unrelated PRs on upstream base-image CVEs. Escalate by adding an allow-list entry only with rationale + expiry + owner in `.trivyignore`. |
| **Repo drift (weekly)** | `.github/workflows/drift.yml` | `scripts/drift-since-tag.sh --repo-only` | n/a | Scheduled Monday 12:00 UTC. Diffs the repository against the last known-good tag. Updates a single rolling issue labelled `automation:drift` when drift is detected; silent when clean. Operator-side cron (against live servers) is unchanged and uses the script without `--repo-only`. |
| **Jinja2 snapshot diff (27 templates)** | `scripts/render-snapshots.py` | golden-file diff | n/a | Fails on any unintended render change. Run `make snapshot-update` after intentional template edits. |

## Test fixtures and stubs

All shared test inputs live under `tests/fixtures/` and stub binaries under
`tests/stubs/bin/`.

### `tests/fixtures/`

| File | Purpose |
|---|---|
| `secrets-sample.yml` | SOPS-decrypted-shaped YAML with placeholder values; loaded by pytest and Rust integration tests via `include_str!` |
| `secrets-sample.sops.yaml` | Same content age-encrypted to a test-only key (`tests/fixtures/age-test.key`) |
| `tf-output-sample.json` | `terraform output -json` shape; consumed by render-inventory tests |
| `inventory-sample.ini` | Expected output of `render-inventory.sh` for the sample TF output |
| `fleet-plan-sample.yaml` | Input shape for `fleet-rotate.sh --dry-run` tests |
| `age-recovery-shares/` | 5 Shamir shares (3-of-5 threshold) for age-recovery round-trip tests |
| `singbox-killswitch-valid.json` | Valid sing-box bundle for kill-switch positive-case test |

### `tests/stubs/bin/`

POSIX shell scripts (shellcheck-clean, ≤30 lines each) that replace real
binaries during pytest dry-run tests. Tests prepend `tests/stubs/bin` to
`PATH`; each stub echoes its invocation to `$STUB_LOG` so tests can assert
exact argument vectors without network or filesystem side-effects.

Stubs provided: `terraform`, `ansible-playbook`, `sops`, `curl`, `gh`,
`upcloud`, `hcloud`, `vultr`.

The bats tests under `tests/bats/` use the same `PATH=tests/stubs/bin:$PATH`
discipline and call the same fixture files. See `tests/stubs/README.md` for
the discipline contract and how to add a new stub.

## Test phases mapped to operator workflow

| Operator step | Tests that protect it |
|---|---|
| `git commit` (local) | pre-commit hooks: gitleaks, terraform fmt, ansible-lint, yamllint, **shellcheck**, **secrets-coverage**, **templates-render**, **placeholder-scan** |
| `git push` (PR) | CI matrix: terraform fmt+validate (3 providers), terraform test (3 providers), cloud-init schema, ansible-lint + syntax, required molecule scenarios for baseline/firewall/xray/hysteria/nginx-xhttp/watchdog/monitoring/backup/subscription-host plus watchdog failure, shellcheck, secrets-coverage, templates-render, yamllint, gitleaks, unit tests (91 pytest + 114 Rust + 29 bats), Conftest TF policy (3 providers), Trivy image scan, snapshot diff, secrets schema; reproducible-build covers xray + hysteria + RealiTLScanner sha256. |
| PR labeled `ci-real-deploy` | **real-vps-deploy** workflow: provisions an ephemeral UpCloud VPS, runs site.yml + verify, destroys — closest approximation to production in CI. See `docs/CI-REAL-DEPLOY.md`. |
| `make validate` (operator) | terraform fmt + validate + gitleaks + ansible-lint + ansible syntax-check |
| `make validate-target` | live probe of REALITY target (TLS / H2 / SAN / uTLS / ASN / template OPSEC) |
| `make plan` | terraform plan (catches infrastructure drift) |
| `make dry-run` / `make deploy` / `make verify` | **pre-deploy-check** runs first: spot-check-secrets + check-certs; bypass with `SKIP_PRECHECK=1` |
| `make deploy` | role handlers run validate-before-restart (Xray, nftables, nginx) |
| `make verify [TAG_ON_SUCCESS=1]` | post-deploy gates assert services up, listeners present; optionally git-tag the commit as `vpn-deploy-known-good-*` |
| `make drift-since-tag` | weekly: diff fleet against the last known-good tag (terraform plan + ansible --check). The CI scheduled variant uses `--repo-only` and runs without SOPS access — see `.github/workflows/drift.yml`. |
| scheduled Monday 08:00 UTC | **cargo-mutants** (`.github/workflows/mutants.yml`) — validates vpnd test suite is doing its job; non-blocking |
| scheduled Monday 12:00 UTC | **drift-since-tag --repo-only** (`.github/workflows/drift.yml`) — repository-level drift detection; opens/updates a rolling issue |
| weekly weekend | **Renovate** opens grouped dependency-update PRs (Terraform providers, Rust crates, GitHub Actions digest pins, Xray/Realm/AmneziaWG version pins via regex managers) |
| `make smoke-test` | end-to-end real-traffic dial through every enabled profile |
| `make check-killswitch BUNDLE=…` | per-client validation of emitted sing-box bundle (5 rules: auto_route, strict_route, sniff, final ≠ direct, DNS detour ≠ direct, no IPv6-only outbound) |

## Dependency updates

Pinned versions are not maintained by hand — Renovate opens weekly PRs
for the ecosystems it supports, and each PR runs through the full CI
matrix above before a human merges.

Renovate config lives at `renovate.json` at the repo root. Key behaviors:

- `helpers:pinGitHubActionDigests` preset — every Action stays SHA-pinned;
  Renovate auto-updates digests with the matching version comment preserved.
- Terraform providers grouped into a single weekly PR; Rust crates grouped
  the same way (lowers merge overhead).
- Custom regex managers for `xray_version`, `realm_version`, and
  `amneziawg_version` in `ansible/roles/*/defaults/main.yml` — each pointed
  at upstream GitHub Releases. `docs/XRAY-RELEASE-LINE.md` remains the
  policy SOT; the Renovate PR is the *trigger* for operator review.
- `vulnerabilityAlerts.enabled: true`. Schedule: weekly on weekends.

| Ecosystem | Renovate covers? | Where pinned | Refresh cadence |
|---|---|---|---|
| GitHub Actions (digests) | yes | `.github/workflows/*.yml` | weekly, one PR per Action |
| Terraform providers | yes | `terraform/providers/*/versions.tf` + `.terraform.lock.hcl` | weekly, grouped |
| Rust crates | yes | `vpnd/Cargo.toml` + `vpnd/Cargo.lock` | weekly, grouped |
| Python tooling | yes | `requirements.txt` | weekly, grouped |
| Xray / Realm / AmneziaWG binaries | yes (via regex managers) | `ansible/roles/*/defaults/main.yml` | per upstream release; operator merges against `docs/XRAY-RELEASE-LINE.md` policy |
| Ansible Galaxy collections | **no** (Renovate gap) | exact versions in `requirements.yml` | manual quarterly review (see below) |
| geodata (geosite/geoip) | n/a | concrete URLs + sha256 values in the deployed vars file | daily systemd timer on the VPS via `geodata` role |

### Manual quarterly Galaxy collection refresh

Renovate does not yet support Ansible Galaxy. Once a quarter, run:

```bash
# Inspect current pins
grep -A1 'name:' requirements.yml

# Check upstream for newer versions
ansible-galaxy collection list  # local cache
# or browse https://galaxy.ansible.com/<collection>

# Bump exact pins in requirements.yml; install fresh
rm -rf ~/.ansible/collections
ansible-galaxy collection install -r requirements.yml --force

# Re-run molecule on at least one role
make molecule-test ROLE=baseline

# Commit with: chore(deps): refresh Ansible Galaxy collections
```

Auto-merge is intentionally **not** enabled for any Renovate PR — every
update goes through a human review. Operators who want auto-merge can
configure it per-ecosystem in repo Settings.

## Build attestation (SLSA Level 3)

Every released `vpnd` binary ships with a Sigstore-signed SLSA-v1.0 Build
Level 3 provenance attestation generated by `actions/attest-build-provenance`
from `.github/workflows/release-vpnd.yml`. The attestation proves the binary
came from this repo's trusted build workflow on a specific commit SHA.

Verify a downloaded binary:

```bash
gh attestation verify ./vpnd-x86_64-unknown-linux-gnu \
  --owner po4yka --signer-workflow .github/workflows/release-vpnd.yml
```

`scripts/install-vpnd.sh` calls this automatically when `gh` is on PATH and
`VPND_SKIP_ATTESTATION` is unset. The script warns and continues if `gh` is
missing — set `VPND_SKIP_ATTESTATION=1` to opt out explicitly.

## Pre-commit hooks

Local pre-commit configuration (`.pre-commit-config.yaml`) catches common
issues before CI cycles:

- `terraform_fmt`, `terraform_docs`, `terraform_tflint` via
  `antonbabenko/pre-commit-terraform` — Terraform formatting, auto-generated
  per-provider README, and security linting.
- `cargo-clippy` (local hook) — workspace warnings-as-errors for vpnd.
- `prettier` scoped to JSON files in `tests/fixtures/` and `secrets/schema.json`
  only — does not touch markdown or vendored package.json files.

Generated `terraform/providers/<name>/README.md` files are committed; the
`terraform_docs` hook keeps them in sync on every commit.

## What is intentionally NOT tested

- **Live external network reachability of upstream geodata / Xray / Hysteria
  binaries.** Test would couple the build to upstream availability. We
  pin-and-checksum at deploy; CI doesn't re-validate every release.
- **AmneziaWG TUN converge inside Docker.** Requires kernel TUN device +
  golang build of amneziawg-go. Render check covers template correctness;
  `awg show` is part of `verify.yml` against a real VPS.
- **NaiveProxy xcaddy build.** Pulls Go modules; flaky in CI. Render check
  + bash-syntax cover the artifact shape; the build runs only on the target
  VPS during deploy.
- **Cloudflare WARP registration.** Requires a registerable WARP endpoint not
  available in CI containers. Structure validation only via molecule
  syntax-only scenario.
- **RealiTLScanner full-scan integration.** Binary required at runtime;
  coupling CI to upstream build would introduce flakiness. Shellcheck covers
  the wrapper script shape.
- **`scripts/restore.sh` real mode.** The `--dry-run` mode is covered by
  `tests/unit/test_restore_dryrun.py`. The live restore path (decrypts
  SOPS secrets, re-provisions real infrastructure) is only safe to exercise
  against a throwaway VPS; a maintainer TODO covers adding it to the
  `ci-real-deploy` label workflow.
- **End-to-end traffic against geographic locations** (RU, EU, US). Would
  require live infrastructure with the right BGP. This is what
  `make burn-check` (operator-side cron) covers post-deploy.
- **Long-running stability** (memory leaks, descriptor exhaustion). Out of
  scope for unit-level testing; the watchdog role catches it post-deploy.
- **Active-probing simulation** against the deployed REALITY listener. The
  validator covers the static OPSEC properties; behavior under real
  probing is observable only against live infrastructure.

## Adding a new role

When you add a role, the checklist is:

1. Write the role under `ansible/roles/<name>/`.
2. Reference it in `ansible/playbooks/site.yml` with a `vpn.enable_<name>`
   toggle.
3. Add the toggle to `ansible/group_vars/all.yml` and to every
   `vpn-<cohort>.yml`.
4. If the role consumes new secret keys, add them to
   `secrets/prod.secrets.example.yaml`. **Do not skip this.** The
   `check-secrets-coverage.py` validator will fail PRs that miss it.
5. Either:
   - Add `ansible/roles/<name>/molecule/default/{molecule,converge,verify}.yml`
     and add the role to the molecule matrix in `.github/workflows/ci.yml`, or
   - Document a justified skip in this file's coverage matrix.
6. If the role drops shell scripts via templates, the rendered output must
   pass `bash -n` (added to your verify play).

## Adding a new template

1. Reference variables that exist in role defaults, group_vars, or the
   secrets schema. The `check-secrets-coverage.py` validator will catch
   omissions.
2. If it's a `*.json.j2` template, the render check will validate it as
   JSON.
3. If it's an nginx site config, name it `*.conf.j2` under a role whose
   parent dir contains "nginx" — the render check will run `nginx -t`.

## Adding a new script

1. `bash -n` must pass (catches syntax).
2. `shellcheck -s bash -S warning` must pass (catches common bash
   pitfalls). Add `# shellcheck disable=SCXXXX  # reason` for justified
   exceptions.
3. Include a top-of-file comment block describing usage, env, and exit
   codes.
