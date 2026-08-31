# vpn-deploy — agent instructions

> Cross-tool counterpart to `CLAUDE.md`. Per-folder `AGENTS.md` are symlinks
> to the directory's `CLAUDE.md` — edit `CLAUDE.md`, not the symlink. This
> file is opinionated and explicit; treat it as the single entry point for
> agents that do not load `CLAUDE.md` natively (Codex, Cursor, Aider, …).

## Project at a glance

Reproducible IaC for a four-tier layered outbound connectivity stack:

- **P0** — VLESS + REALITY + Vision (TCP/443, filtered-path baseline)
- **P1** — nginx + XHTTP direct (configurable port; no CDN baseline)
- **P2** — Hysteria2 (UDP) + AmneziaWG (device tunneled outbound)
- **P3** — manual reachability fallbacks

Layers: Terraform → cloud-init → Ansible → SOPS+age secrets → optional `vpnd`
Rust CLI. Threat model: active L7 fingerprinting and aggressive QoS. **Nodes are disposable**:
when an IP burns, recreate from git + secrets, do not repair.

## Build & test

The Makefile is the canonical operator surface.

| Goal | Command |
|---|---|
| Fast CI gate (render, secrets, snapshots, schema, syntax, pytest) | `make ci-fast` |
| Single Ansible role | `make molecule-test ROLE=<name>` |
| Terraform mock_provider tests | `make tf-test` |
| Rust convenience CLI | `cd vpnd && cargo check && cargo test` |
| Validate before commit (fmt, validate, gitleaks, ansible-lint) | `make validate` |
| Dry-run deploy (no changes) | `make dry-run` |
| Full deploy | `make deploy` |
| Post-deploy verification | `make verify` |

## Hard rules — DO NOT

- Commit secrets, Terraform state, decrypted secrets, `user_data` contents,
  Ansible debug, or screenshots containing tokens. Provider credentials live
  in env vars only.
- Bypass safety gates: `--no-verify`, `--no-gpg-sign`, `gitleaks` skip,
  pre-commit skip, ansible-lint skip — never, unless the user has explicitly
  asked.
- Share UUIDs, REALITY shortIds, or AmneziaWG peer keys across devices. One
  per device, always.
- Mention Claude, Claude Code, or Anthropic in commit messages. Do not add
  `Co-Authored-By:` trailers.
- Pipe remote installers into root shells.
- Run public admin panels.
- Cross layer boundaries except through documented interfaces. Terraform owns
  cloud resources; cloud-init owns first-boot; Ansible owns runtime state;
  SOPS+age owns secrets at rest; `vpnd` is convenience only.
- Use CDN as the filtered-path baseline. See `docs/CDN-DECISION.md`.
- Commit pre-release versions to production toggles. Pre-releases go through
  staging only.
- Reference external knowledge stores anywhere in this repo — store names,
  filesystem paths, page slugs, or externally hosted citations in code,
  comments, docs, commit messages, or task notes. Knowledge that needs to
  live in this repo lives in this repo.
- Name files, slugs, variables, doc table cells, or comments after carriers,
  ISPs, geography, or operators — e.g. no `carrier-region` or `mobile-network`. Describe cohorts,
  profiles, and configurations by their technical signature instead: packet
  shape, protocol parameters, threshold values, observed DPI behaviour.

## Conventions — DO

- **Conventional Commits**. release-please drives versioning and the
  changelog; do not edit `CHANGELOG.md` by hand. One bump per session by
  intent.
- **Edit the per-folder `CLAUDE.md`** when local design context changes. The
  format is fixed: three sections — **Design decisions** (WHY), **What's done
  well** (preserve), **Pitfalls** (the most valuable). Keep each under ~40
  lines.
- **Prefer small, focused diffs** (<200 lines when possible). Bug fix ≠
  surrounding cleanup.
- **Run `make validate` before committing** Terraform or Ansible changes.
- **Verify before claiming completion**. If a hook fails, fix the cause —
  do not skip the hook.

## Per-folder agent docs

Walk the directory tree — every meaningful folder has its own `AGENTS.md`
(symlinked to `CLAUDE.md` with the three-section format above):

```
AGENTS.md / CLAUDE.md                                — this file (root)
ansible/                                             — playbook order, group_vars contract
ansible/roles/{amneziawg,backup,baseline,cdn-front,
              cascade-egress,cascade-ingress,dns-morph-bridge,firewall,geodata,honeypot,
              hysteria,hysteria-realm,intrusion_prevention,monitoring,naive,node_manifest,
              nginx-xhttp,network-exposure-gate,policy-ratelimit,package_updates,real-vps-awg-nat,reality-self-steal,
              runtime-release,security_audit,split-hop-egress,
              split-hop-ingress,probe-matrix-target,snell,subscription-host,
              warp-outbound,watchdog,xray,xray-runtime}/  — 33 roles
terraform/                                           — provider-root strategy
terraform/providers/{hetzner,scaleway,upcloud,vultr}/ — per-provider quirks
terraform/shared/                                    — cloud-init contract
terraform/policy/                                    — OPA/conftest plan policies
terraform/exception/cascade-ingress/                 — inert governance-gated scaffold
scripts/                                             — shell/python conventions
tests/                                               — unit, snapshot, molecule, tf-test layers
vpnd/                                                — Rust convenience CLI
```

When working inside a subtree, the nearest `AGENTS.md` wins.

## Source of truth

| Artifact | Canonical location |
|---|---|
| CLI flags / subcommands | `vpnd/src/cli.rs` |
| Package versions | release-please + `CHANGELOG.md` |
| Secrets schema (structure) | `secrets/schema.json` + `scripts/validate-secrets.py` |
| Secrets schema (coverage) | `scripts/check-secrets-coverage.py` |
| Protocol toggles | `ansible/group_vars/all.yml` + cohort files (`vpn-p0.yml`, `vpn-p1p2.yml`, `vpn-fullstack.yml`) |
| Recipient page | `vpnd/templates/recipient.html` |
| AWG cohort profiles | `ansible/roles/amneziawg/vars/cohorts/` |
| Xray version pin | SOPS secret `xray.version` (see `secrets/prod.secrets.example.yaml`) |

## Task board and specifications

Repository work is tracked under `docs/tasks/`. Read `.agents/skills/repo-task-board/SKILL.md` before creating, updating, triaging, executing, or closing work.

- `docs/tasks/issues/<slug>.md` is the portfolio source of truth with stable IDs.
- Simple execution lives in `docs/tasks/work/<TASK-ID>.md`; specification-driven execution lives in `openspec/changes/<change>/tasks.md`.
- `docs/tasks/board.md` is generated by `./taskctl generate-board` and is read-only.
- Cross-repository references use qualified IDs such as `po4yka/RIPDPI#TRN-...`; validate the combined graph with `make task-federation PEER_ROOT=<RIPDPI checkout>`.

Use only `./taskctl` for state transitions, mdtask access, OpenSpec archival, validation, and the two-commit close lifecycle. Direct upstream archive, `--no-validate`, manual task IDs, and deleting a task before its committed terminal state are forbidden. Features, infrastructure behavior, schemas, security/network changes, deployment lifecycle, and cross-repository contracts require OpenSpec.

Portable tasking skills are canonical under `.agents/skills/`. The pinned development tools are installed by `make task-tools`; global mdtask or OpenSpec installations are neither required nor authoritative.

## Change recipes

### New Ansible role

1. Scaffold `ansible/roles/<name>/` (tasks, defaults, meta, handlers as needed).
2. Add enable toggle to `ansible/group_vars/all.yml`.
3. Add secrets keys to `secrets/prod.secrets.example.yaml` if the role needs secrets.
4. Write a molecule scenario under `ansible/roles/<name>/molecule/` or add a justified skip to `docs/TESTING.md`.
5. Create `ansible/roles/<name>/CLAUDE.md` (three-section format).
6. Update `README.md` if operator-facing behaviour changed.
7. Include the role in `ansible/playbooks/site.yml` behind the toggle.

### New Terraform provider

1. Create `terraform/providers/<name>/` with identical output schema to existing providers (`server_ipv4`, `server_ipv6`, `admin_user`, `server_hostname`).
2. Keep the canonical output keys so `scripts/render-inventory.sh` uses its generic path; add a provider branch only for incompatible output keys or a provider-specific guest-convergence check.
3. Add a row to `docs/PROVIDER-NOTES.md` (status, version, known limits).
4. Create `terraform/providers/<name>/CLAUDE.md`.

### New vpnd subcommand

1. Add a variant to the `Command` enum in `vpnd/src/cli.rs`.
2. Create `vpnd/src/commands/<name>.rs` with signature `pub async fn run(ctx: &Context, args: …Args) -> Result<()>`.
3. Wire the module in `vpnd/src/commands/mod.rs`.
4. Add a match arm in `vpnd/src/main.rs`.
5. Add a snapshot test if the subcommand renders output.
6. Update `vpnd/CLAUDE.md` if the subcommand introduces an architecturally novel pattern.

### New AmneziaWG cohort

1. Create `ansible/roles/amneziawg/vars/cohorts/<technical-slug>.yml` with the obfuscation parameters. Slug names the packet shape, not the carrier — e.g. `narrow-junk-sequential`, `wide-junk-random-headers`. Per the hard rules above, do not name cohorts after the carrier, ISP, or geography where the shape was measured.
2. Add a row to `docs/AWG-COHORTS.md` (profile slug, junk packet sizes, init/response packet sizes, H1..H4 strategy).
3. Add a `group_vars` hint or comment if the cohort requires non-default operator awareness at deploy time.

## When the user says "remember"

Save to the relevant folder's `CLAUDE.md` (the `AGENTS.md` symlink points at
it), not to an external memory system. The per-folder knowledge layer is the
durable artifact.
