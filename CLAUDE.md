# vpn-deploy — root knowledge file

## Vision

Reproducible, layered IaC for a four-tier multi-profile outbound connectivity stack
(P0 VLESS+REALITY+Vision, P1 nginx+XHTTP direct, P2 Hysteria2 + AmneziaWG,
P3 manual reachability). Threat model is active L7 fingerprinting and
aggressive QoS.

Nodes are disposable. Secrets are SOPS+age. The Makefile is the canonical
operator surface; `vpnd/` is a convenience CLI in front of it (see
`vpnd/CLAUDE.md` and `vpnd/src/cli.rs`).

## Hard rules

- No secrets in git, Terraform state, TF vars/outputs, cloud-init `user_data`,
  Ansible debug, or screenshots. Provider credentials in env vars only.
- No public admin panel. No remote installer piped to root shell.
- One UUID / shortId / peer key per device — never shared.
- Pinned versions; pre-releases through staging only.
- Gitleaks gates CI.
- CDN is **not** the filtered-path baseline (see `docs/CDN-DECISION.md`).
- **No references to external knowledge stores** (store names, filesystem
  paths, page slugs, or externally hosted citations) anywhere in this repo — code,
  comments, docs, commit messages, task notes. Knowledge that needs to live in
  this repo lives in this repo.
- **No carrier / ISP / geographic / operator-identifying labels** in file names,
  slugs, variable names, doc table cells, or comments — e.g. no `carrier-region`
  or `mobile-network`. Describe
  cohorts, profiles, and configurations by their technical signature instead:
  packet shape, protocol parameters, threshold values, observed DPI behaviour.

## Layered ownership

```
Terraform     → VPS, firewall, SSH key, DNS, floating IP
cloud-init    → admin user, SSH hardening, python3, marker file
Ansible       → all runtime state (packages, nftables, xray, nginx, …)
SOPS+age      → secrets at rest, outside Git tracking
vpnd (Rust)   → convenience CLI in front of Make/Terraform/Ansible/SOPS
```

Strict boundary: nothing crosses these except via documented interfaces.

## Per-folder CLAUDE.md system

Every meaningful folder has a `CLAUDE.md`. Together they form a
self-healing knowledge layer. Format: three sections — **Design decisions**
(WHY), **What's done well** (preserve), **Pitfalls** (the most valuable).
Keep each under ~40 lines. Update as part of the PR, not a separate task.

Cross-tool agents (Codex, Cursor, Aider, …) load `AGENTS.md`. There is a
real `/AGENTS.md` at the repo root (a distilled, opinionated subset of this
file); every folder with a `CLAUDE.md` also has an `AGENTS.md` symlink
pointing at it. Edit `CLAUDE.md` — never edit the symlink.

Current coverage:

```
CLAUDE.md                                — this file
ansible/CLAUDE.md                        — playbook order, group_vars contract
ansible/roles/<name>/CLAUDE.md           — 37 roles, all backfilled
terraform/CLAUDE.md                      — provider-root strategy
terraform/providers/<name>/CLAUDE.md     — upcloud, hetzner, vultr, scaleway
terraform/shared/CLAUDE.md               — cloud-init contract
scripts/CLAUDE.md                        — shell/python conventions
tests/CLAUDE.md                          — unit + snapshot + molecule + tf-test layers
vpnd/CLAUDE.md                           — Rust convenience CLI
vpnd/src/cli.rs                          — vpnd subcommand + flag definitions (canonical SOT)
docs/CDN-DECISION.md                     — ADR: CDN is not the filtered-path baseline
```

## Development

```bash
make ci-fast            # portable credential-free CI parity bundle; see docs/TESTING.md
make molecule-test ROLE=<name>
make tf-test            # terraform mock_provider tests
cd vpnd && cargo check  # convenience CLI typecheck
cd vpnd && cargo test   # snapshot tests for the recipient page
```

## Versioning

release-please drives versioning from Conventional Commits. Don't edit
`CHANGELOG.md` by hand. One bump per session by intent.

After every completed task, run the required validation and commit all current
worktree changes with a Conventional Commit. Do not leave completed task work
uncommitted unless the user explicitly asks for that.

## Change recipes

### New Ansible role

1. Scaffold `ansible/roles/<name>/` (tasks, defaults, meta, handlers as needed).
2. Add enable toggle to `ansible/group_vars/all.yml`.
3. Add secrets keys to `secrets/prod.secrets.example.yaml` if the role needs secrets.
4. Write a molecule scenario under `ansible/roles/<name>/molecule/` or add a justified skip to `docs/TESTING.md`.
5. Create `ansible/roles/<name>/CLAUDE.md` (Design decisions / Done well / Pitfalls).
6. Update `README.md` if operator-facing behaviour changed.
7. Include the role in `ansible/playbooks/site.yml` behind the toggle.

### New Terraform provider

1. Create `terraform/providers/<name>/` with identical output schema to existing providers (`server_ipv4`, `server_ipv6`, `admin_user`, `ssh_port`, `server_hostname`).
2. Keep the canonical output keys so `scripts/render-inventory.sh` uses its generic path; add a provider branch only for incompatible output keys or a provider-specific guest-convergence check.
3. Add a row to `docs/PROVIDER-NOTES.md` (status, version, known limits).
4. Create `terraform/providers/<name>/CLAUDE.md`.

### New vpnd subcommand

1. Add a variant to the `Command` enum in `vpnd/src/cli.rs`.
2. Create `vpnd/src/commands/<name>.rs` with signature `pub async fn run(ctx: &Context, args: …Args) -> Result<()>`.
3. Wire the module in `vpnd/src/commands/mod.rs`.
4. Add a match arm in `vpnd/src/main.rs`.
5. Add a snapshot test if the subcommand renders output (see existing tests for pattern).
6. Update `vpnd/CLAUDE.md` if the subcommand introduces an architecturally novel pattern.

### New AmneziaWG cohort

1. Create `ansible/roles/amneziawg/vars/cohorts/<technical-slug>.yml` with the obfuscation parameters. Slug names the packet shape, not the carrier — e.g. `narrow-junk-sequential`, `wide-junk-random-headers`. Per the hard rules above, do not name cohorts after the carrier, ISP, or geography where the shape was measured.
2. Add a row to `docs/AWG-COHORTS.md` (profile slug, junk packet sizes, init/response packet sizes, H1..H4 strategy).
3. Add a `group_vars` hint or comment if the cohort requires non-default operator awareness at deploy time.

## Source of truth

| Artifact | Canonical location | Must stay in sync with |
|---|---|---|
| CLI flags / subcommands | `vpnd/src/cli.rs` | README, runbooks, command builder if added |
| Package versions | release-please + `CHANGELOG.md` | `vpnd/Cargo.toml` `[package].version` |
| Secrets schema (structure) | `secrets/schema.json` + `scripts/validate-secrets.py` | `ansible/roles/*/`, `vpnd::secrets` |
| RIPDPI bundle contract | `contract/ripdpi-bundle.schema.json` (+ `scripts/validate-bundle.py`, `docs/RIPDPI-BUNDLE.md`) | `scripts/emit-bundle.sh`, vendored copy in the RIPDPI client repo (`core/data/src/test/resources/contract/`) |
| AWG cohort fingerprint algo | `scripts/ripdpi_cohort_fingerprint.py` + `contract/cohort-fingerprint.golden.json` | `scripts/emit-bundle.sh`, client `AmneziaWgParameters.cohortFingerprint()` |
| AWG arm64 S3/S4 version floor | `contract/amneziawg-arm64-version-floor.json` | role/schema guard + client vendored policy |
| Secrets schema (coverage) | `scripts/check-secrets-coverage.py` | `secrets/prod.secrets.example.yaml`, all Jinja2 templates |
| Protocol toggles | `ansible/group_vars/all.yml` | `ansible/roles/*/`, vpnd config templates |
| Recipient page | `vpnd/templates/recipient.html` | `ansible/roles/subscription-host/`, `docs/demo/` |
| AWG cohort profiles | `ansible/roles/amneziawg/vars/cohorts/` | `docs/AWG-COHORTS.md` |
| Xray version pin | SOPS secret `xray.version` (see `secrets/prod.secrets.example.yaml`) | `ansible/roles/xray/defaults/main.yml` (sentinel only), `docs/XRAY-RELEASE-LINE.md` |

## Task tracking

Portfolio state lives in `docs/tasks/issues/`; execution lives in exactly one
mdtask file under `docs/tasks/work/` or an active OpenSpec change. The generated
`docs/tasks/board.md` is read-only. The strict schema, risk rule, federation
contract, and two-commit close lifecycle are in `docs/tasks/README.md` and the
canonical `.agents/skills/repo-task-board/SKILL.md` skill.

Use only `./taskctl` for task lifecycle, mdtask access, OpenSpec archival, and
validation. Cross-repository references are qualified as `project#TASK-ID` and
are checked against a peer checkout rather than mirrored manually. Install the
exact tools with `make task-tools`; run `make task-check` before handoff.

## When the user says "remember"

Save to the relevant folder's `CLAUDE.md`, not to a memory system. The
per-folder knowledge layer is the durable artifact.
