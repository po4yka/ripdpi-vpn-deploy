# vpn-deploy — agent instructions

Canonical instructions for every coding agent in this repository. The root `CLAUDE.md` imports this file, so edit this file rather than maintaining a second copy.

## Project

Reproducible, layered IaC for a four-tier outbound connectivity stack:

- **P0** — VLESS + REALITY + Vision (TCP/443, filtered-path baseline)
- **P1** — nginx + XHTTP direct (configurable port; no CDN baseline)
- **P2** — Hysteria2 (UDP) + AmneziaWG (device tunneled outbound)
- **P3** — manual reachability fallbacks

The threat model is active L7 fingerprinting and aggressive QoS. Nodes are disposable: when an IP burns, recreate it from git + secrets instead of repairing it in place.

Layer ownership is strict; nothing crosses these boundaries except through documented interfaces:

| Layer | Owns |
|---|---|
| Terraform | VPS, provider firewall, SSH key, DNS, floating IP |
| cloud-init | admin user, SSH hardening, python3, marker file |
| Ansible | all runtime state (packages, nftables, xray, nginx, ...) |
| SOPS + age | secrets at rest, outside Git tracking |
| `vpnd` (Rust) | convenience CLI in front of Make/Terraform/Ansible/SOPS; never a replacement |

The Makefile is the canonical operator surface.

## Hard rules

- No secrets in git, Terraform state, TF vars/outputs, cloud-init `user_data`, Ansible debug output, or screenshots. Provider credentials live in env vars only. Do not read or print plaintext secret material (`.env`, `secrets/local/`, decrypted SOPS output, `*.tfstate`) into the session: transcripts and logs leave the operator machine.
- Never bypass safety gates (`--no-verify`, `--no-gpg-sign`, skipping gitleaks, pre-commit, or ansible-lint) unless the user explicitly asks. When a hook fails, fix the cause.
- One UUID, REALITY shortId, and AmneziaWG peer key per device. Never share or copy them between devices: shared material links devices and makes per-device revocation impossible.
- No public admin panel. No remote installer piped into a root shell.
- CDN is not the filtered-path baseline (`docs/CDN-DECISION.md`).
- Pin every version; pre-releases go through staging only, never onto production toggles.
- No references to external knowledge stores (store names, filesystem paths outside the repo, page slugs, externally hosted citations) in code, comments, docs, commit messages, or task notes. Knowledge the repo needs lives in the repo.
- No carrier, ISP, geographic, or operator-identifying labels in file names, slugs, variable names, doc table cells, or comments (e.g. no `carrier-region` or `mobile-network`). Name cohorts, profiles, and configurations by technical signature: packet shape, protocol parameters, threshold values, observed DPI behaviour.

## Decision boundaries

Repository-local, reversible work needs no confirmation: editing files, running tests, linters, formatters, Molecule, `make check`/`ci-fast`/`validate`, refreshing snapshots you have reviewed, and committing your own changes locally.

Run these only when the user explicitly asks, because they touch real infrastructure, credentials, or shared history:

- Make targets or scripts that use cloud credentials, inventory, SSH, or decrypted secrets, including `plan`, `apply`, `destroy`, `staging-destroy`, `dry-run`, `deploy*`, `verify`, `security-verify`, `smoke-test`, `fleet-*`, `rotate-*`, `rollback-*`, `promote-spare`, `blue-green`, `decrypt`, `bootstrap-secrets`, `issue-*`, `install-*` (except the local `install-hooks`), `backup-state`, and the `observability-*` lifecycle verbs other than `render`/`validate`.
- Direct `terraform`, `ansible-playbook`, `sops --decrypt`, or SSH against real providers or hosts.
- Pushing, force-pushing, opening or merging PRs, tagging, `git reset --hard`, deleting branches, or discarding changes you did not make.

## Build and verify

| Goal | Command |
|---|---|
| Full local pre-PR gate (task contract + validate + ci-fast) | `make check` |
| Credential-free CI parity bundle | `make ci-fast` |
| Terraform fmt/validate, gitleaks, ansible-lint, playbook syntax | `make validate` |
| One Ansible role (Docker) | `make molecule-test ROLE=<name>` |
| Template render snapshots (refresh: `make snapshot-update`) | `make snapshot-check` |
| Terraform `mock_provider` tests / Conftest policies | `make tf-test` / `make tf-policy-verify` |
| Python unit tests | `python3 -m pytest tests/unit/<file>.py` (all: `make test-unit`) |
| Shell scripts | `make shellcheck` |
| vpnd | `cd vpnd && cargo test` (CI parity: `make vpnd-test vpnd-clippy`) |

Verify in proportion to risk. Run the narrowest check that exercises the change (the matching test file, `molecule-test` for the touched role, `snapshot-check` for template edits, `tf-test` for a provider root, `cargo test` for vpnd), then `make check` before handing off changes that span layers or touch schemas, secrets handling, CI, or shared scripts. `docs/TESTING.md` maps each area to its CI coverage. Report the commands you ran and their results; a skipped or failing check is reported as such.

Toolchains are pinned in `mise.toml` (Python 3.12 with `requirements.txt`, Terraform, Go, conftest, promtool). If a non-interactive shell resolves a different `python3`, run commands through `mise exec -- <cmd>`; otherwise Ansible-dependent tests fail with `ModuleNotFoundError` instead of reporting real regressions. An operator-local `.fleet.mk` feeds every `make` call, so Make-driven tests can fail locally for fleet-configuration reasons; confirm such a failure against a clean checkout before treating it as a regression.

## Where knowledge lives

- **Per-folder `CLAUDE.md`** files hold each subtree's design decisions and pitfalls. Every `AGENTS.md` below the root is a symlink to its sibling `CLAUDE.md`; edit `CLAUDE.md`, never the symlink, and give every new `CLAUDE.md` an `AGENTS.md -> CLAUDE.md` symlink (`tests/unit/test_agent_instructions.py` enforces this, skill layout, and that cited paths exist). Claude Code loads these files automatically when it reads files in the folder; other agents started at the repo root should open the nearest one before changing files in that subtree. Coverage: `ansible/` and all 37 roles under `ansible/roles/`, `terraform/` (providers, shared, exception), `scripts/`, `tests/`, `tools/`, `vpnd/`, `attestations/`, `docs/measurements/`.
- Folder notes use three sections: **Design decisions** (why), **What's done well** (preserve), **Pitfalls**. Update the folder's `CLAUDE.md` in the same change that alters its behaviour (`claude-md-touch.yml` warns in CI). When the user says "remember", record it there, not in an external memory system.
- Change recipes live next to the code they change: new Ansible role in `ansible/CLAUDE.md`, new Terraform provider in `terraform/CLAUDE.md`, new `vpnd` subcommand in `vpnd/CLAUDE.md`, new AmneziaWG cohort in `ansible/roles/amneziawg/CLAUDE.md`.
- **Skills** live in `.agents/skills/<name>/SKILL.md`; `.claude/skills/<name>` (and `.github/skills/` for the tasking skills) are symlinks to them. The tasking skills are generated assets pinned by `tools/tasking/generated-assets.lock.json`, so refresh their hash when you edit one.

## Source of truth

| Artifact | Canonical location | Must stay in sync with |
|---|---|---|
| CLI flags / subcommands | `vpnd/src/cli.rs` | README, runbooks |
| Package versions | release-please + `CHANGELOG.md` | `vpnd/Cargo.toml` `[package].version` |
| Secrets schema (structure) | `secrets/schema.json` + `scripts/validate-secrets.py` | `ansible/roles/*/`, `vpnd::secrets` |
| Secrets schema (coverage) | `scripts/check-secrets-coverage.py` | `secrets/prod.secrets.example.yaml`, all Jinja2 templates |
| RIPDPI bundle contract | `contract/ripdpi-bundle.schema.json` (+ `scripts/validate-bundle.py`, `docs/RIPDPI-BUNDLE.md`) | `scripts/emit-bundle.sh`, vendored copy in the RIPDPI client repo |
| AWG cohort fingerprint algorithm | `scripts/ripdpi_cohort_fingerprint.py` + `contract/cohort-fingerprint.golden.json` | `scripts/emit-bundle.sh`, client `AmneziaWgParameters.cohortFingerprint()` |
| AWG arm64 S3/S4 version floor | `contract/amneziawg-arm64-version-floor.json` | role/schema guard, client vendored policy |
| Protocol toggles | `ansible/group_vars/all.yml` + profile files `ansible/group_vars/vpn-*.yml` | `ansible/roles/*/`, vpnd config templates |
| Recipient page | `vpnd/templates/recipient.html` | `ansible/roles/subscription-host/`, `docs/demo/` |
| AWG cohort profiles | `ansible/roles/amneziawg/vars/cohorts/` | `docs/AWG-COHORTS.md` |
| Xray version pin | SOPS secret `xray.version` (see `secrets/prod.secrets.example.yaml`) | `ansible/roles/xray/defaults/main.yml` (sentinel only), `docs/XRAY-RELEASE-LINE.md` |

## Tasks and specifications

Use the `repo-task-board` skill for any portfolio task work; `docs/tasks/README.md` holds the full policy. The invariants:

- `docs/tasks/issues/` is the portfolio source of truth. Execution lives in exactly one of `docs/tasks/work/<TASK-ID>.md` or `openspec/changes/<change>/tasks.md`. `docs/tasks/board.md` is generated and read-only.
- Only `./taskctl` performs lifecycle transitions, mdtask access, OpenSpec archival, and validation. Never hand-edit the board, run upstream archive commands directly, pass `--no-validate`, invent task IDs, or delete a task before its terminal state is committed.
- OpenSpec is required for features, infrastructure behaviour, schemas, security/network changes, deployment lifecycle, and cross-repository contracts.
- Cross-repository references use qualified IDs such as `po4yka/RIPDPI#TRN-...`; validate with `make task-federation PEER_ROOT=<RIPDPI checkout>`. `make task-tools` installs the pinned tools; run `make task-check` before handoff.

## Commits

- Conventional Commits; release-please derives versions and `CHANGELOG.md`, which is never edited by hand. One bump per session by intent. Types and scopes: the `conventional-commit` skill.
- No `Co-Authored-By:` trailers and no mention of AI assistants or their vendors in commit messages (file names such as `CLAUDE.md` are fine). The commit-msg hook from `make install-hooks` rejects the trailer.
- After completing a task, run its verification and commit the task's own changes with explicit paths. Do not leave completed work uncommitted unless the user asks, and never sweep unrelated worktree changes into the commit.
- Keep diffs focused (<200 lines where practical); a bug fix does not carry surrounding cleanup.
