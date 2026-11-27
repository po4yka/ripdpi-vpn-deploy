# vpn-deploy — agent instructions

Canonical instructions for every coding agent in this repository. The root `CLAUDE.md` imports this file, so edit this file rather than maintaining a second copy.

## Conversation language

Respond in the language of the user's message unless the user explicitly requests another language. Keep repository artifacts in their established language.

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
| `vpnd` (Python) | convenience CLI in front of Make/Terraform/Ansible/SOPS; never a replacement |

The Makefile is the canonical operator surface.

Run `env -u MAKEFILES -u MAKEFLAGS -u GNUMAKEFLAGS -u MFLAGS make workspace-status` once at session start, and again only after you switch worktree or branch. Clearing inherited Make inputs prevents them from being parsed before the discovery target. Use this prefix only on a direct `make` call that this file or a runbook shows with it. Commands that do not start `make` (pytest, git, Python, `./taskctl`) never need it, and tests that run Make clear these variables themselves. Give subagents its output instead of having them run it, so they use the same checkout and known local `origin/main`. For a selected task or machine-readable handoff, use `python3 scripts/workspace-status.py --task <TASK-ID> --json`; this resolves execution/spec pointers through `taskctl` without fetching or loading fleet configuration.

## Hard rules

- Keep operator credentials and VPN secrets out of Git, Terraform inputs/outputs, cloud-init `user_data`, Ansible output, and screenshots. Provider credentials live in env vars only. Providers can record generated credentials in Terraform state and saved plans; protect those files as sensitive data and use encrypted state backups. Do not load or print plaintext secret material (`.env`, decrypted SOPS output, state or saved plan JSON) into the session: transcripts and logs leave the operator machine. Agents maintain the local operator kit in `secrets/local/` through its operator tooling (`sops`, Make targets, the kit scripts) and may read its catalog, runner scripts, input mappings, inventories, encrypted SOPS documents, plans, receipts, logs, recipient artifacts and client configurations directly, so that an authorized deployment, device issuance or debugging session can run end to end. Do not read private keys (`keys/`), recovery material, state backups or decrypted secrets, and never quote secret values (keys, UUIDs, passwords, tokens, share links) in replies, commits, logs or task notes; describe them by field name and location instead.
- Never bypass safety gates (`--no-verify`, `--no-gpg-sign`, skipping gitleaks, pre-commit, or ansible-lint) unless the user explicitly asks. When a hook fails, fix the cause.
- One UUID, REALITY shortId, and AmneziaWG peer key per device. Never share or copy them between devices: shared material links devices and makes per-device revocation impossible.
- No public admin panel. No remote installer piped into a root shell.
- CDN is not the filtered-path baseline (`docs/decisions/0001-cdn-not-filtered-path-baseline.md`).
- Pin every version; pre-releases go through staging only, never onto production toggles.
- No references to external knowledge stores (store names, filesystem paths outside the repo, page slugs, externally hosted citations) in code, comments, docs, commit messages, or task notes. Knowledge the repo needs lives in the repo.
- No carrier, ISP, geographic, or operator-identifying labels in file names, slugs, variable names, doc table cells, or comments (e.g. no `carrier-region` or `mobile-network`). Name cohorts, profiles, and configurations by technical signature: packet shape, protocol parameters, threshold values, observed DPI behaviour.

## Decision boundaries

Repository-local, reversible work needs no confirmation: editing files, running tests, linters, formatters, Molecule, `make check`/`ci-fast`/`validate`, refreshing snapshots you have reviewed, and committing your own changes locally.

The following actions require user authorization because they touch real infrastructure, credentials, or shared history. An explicit deploy, recreation, cleanup or PR request can authorize its necessary steps without naming each command:

- Make targets or scripts that use cloud credentials, inventory, SSH, or decrypted secrets, including `plan`, `apply`, `destroy`, `staging-destroy`, `dry-run`, `deploy*`, `verify`, `security-verify`, `smoke-test`, `fleet-*`, `rotate-*`, `rollback-*`, `promote-spare`, `blue-green`, `decrypt`, `bootstrap-secrets`, `issue-*`, `install-*` (except the local `install-hooks`), `backup-state`, `restore-state`, and the `observability-*` lifecycle verbs other than `render`/`validate`.
- Direct `terraform`, `ansible-playbook`, `sops --decrypt`, or SSH against real providers or hosts.
- Pushing, force-pushing, opening or merging PRs, tagging, `git reset --hard`, deleting branches, or discarding changes you did not make.

Apply existing authorization within its resource, action, cost and time bounds;
recheck the current account, target, IP, plan and private inputs at action time.
Ask again when those bounds change, authorization expires, or an action is not
covered. A reviewable plan is still required before mutation. A request to open
a PR does not authorize merging it. Special platform requirements for bypassing
authentication or destructive actions still apply.
Force-push, history rewrites, destructive reset and discarding others' work
require authorization for that specific operation; a general deploy or PR
request does not supply it.

For deployment acceptance, use [the scoped completion checklist](docs/how-to/deploy.md#acceptance-scope-and-completion).
Choose recreation for a disposable node with unavailable management access;
use rescue/GRUB only when the owner explicitly chooses that emergency path.

## Build and verify

| Goal | Command |
|---|---|
| Full local gate, when the rule below requires it (task-check + validate + ci-fast; add `-j 4` to run independent checks in parallel) | `make check` |
| Credential-free CI parity bundle | `make ci-fast` |
| Terraform fmt/validate, gitleaks, ansible-lint, playbook syntax | `make validate` |
| One Ansible role (Docker) | `make molecule-test ROLE=<name>` |
| Template render snapshots (refresh: `make snapshot-update`) | `make snapshot-check` |
| Terraform `mock_provider` tests / Conftest policies | `make tf-test` / `make tf-policy-verify` |
| Python unit tests | `python3 -m pytest tests/unit/<file>.py` (all: `make test-unit`) |
| Shell scripts | `make shellcheck` |
| vpnd | `make vpnd-test vpnd-lint vpnd-parity-check` |

Verify in proportion to risk. Make all related edits first, then validate them together. Run the narrowest check that exercises the change (the matching test file, `molecule-test` for the touched role, `snapshot-check` for template edits, `tf-test` for a provider root, `make vpnd-test` for vpnd). Run `make check` once, before handing off changes that span layers or touch schemas, secrets handling, CI, or shared scripts; for other changes the narrow check is sufficient, because CI runs every check that the changed paths select. A passing check stays valid until its inputs change: do not run it again for a commit, a push, a PR or a merge (the commit hooks check staged files, CI checks the merged tree). After a failure, rerun only the failing check (`pytest --lf`, the single target) until it passes, then the gate once. Skip that gate rerun only when a `make -k` run showed every other check passing and the fix does not change their inputs; without `-k`, Make stops starting checks after the first failure. While iterating on documentation-only edits, `make docs-check` is the narrow check. `docs/reference/testing.md` maps each area to its CI coverage. Stop when the narrow check, and the gate where this rule requires it, pass: further runs, broader suites or extra review passes do not add evidence. Report the commands you ran and their results; a skipped or failing check is reported as such.

Toolchains are pinned in `mise.toml` (Python 3.12 with `requirements.txt`, Terraform, Go, conftest, promtool). If a non-interactive shell resolves a different `python3`, run commands through `mise exec -- <cmd>`; otherwise Ansible-dependent tests fail with `ModuleNotFoundError` instead of reporting real regressions. An operator-local `.fleet.mk` feeds every `make` call, so Make-driven tests can fail locally for fleet-configuration reasons; confirm such a failure against a clean checkout before treating it as a regression. Other known local-only failures: tests that run real `sops` under an untrusted mise `HOME`, and liveness profile tests when the local sing-box or Xray differs from the CI pin. A test that fails only under `-n auto` and passes when rerun alone is timing-sensitive; report it as such instead of investigating it again.

### Writing tests

Each test must protect a concrete behavior or regression that existing tests do not catch. Add or extend one when a change adds or alters behavior that no existing test exercises: a new branch, parser, boundary, security property, or a bug fix (its regression). Documentation, comments, formatting, renames and deletions that existing tests still cover need no new test. Test-first is optional: use it when a failing test is the quickest way to reproduce a bug. These rules apply to every new or changed test, and also to temporary assertions and smoke scripts.

- Search the area's tests first. Extend the matching test or add a case to its parametrization instead of writing a near copy.
- Assert behavior that you can observe: run the code (subprocess, import and call, rendered template, evaluated Ansible task fields). Do not assert code fragments, names or AST shape of a Python or shell implementation when a test that runs it can show the property.
- Use a source assertion only for a contract that a test cannot run offline. Examples are Make and workflow wiring, security or wire properties of Ansible, systemd, Terraform and templates, and version pins. Pin the property, not the formatting.
- Get expected values from literals, fixtures or an independent method, never from the implementation's own function or algorithm.
- Use a fake only for an external boundary (network, provider API, privileged process). Assert what the application does with the fake's result, not the value that the fake returns.
- Do not add production parameters, hooks or environment variables only to inject trivial wiring. Use the existing boundaries: subprocess, monkeypatch of the external call, or a stub binary in `tests/stubs/bin/`. Add a shared helper or fixture only when two or more tests use it.
- Before you commit, delete temporary assertions, debug output and one-off smoke scripts, or turn them into a test in the matching file.
- When you delete or simplify a test, name the test that still catches the regression. For a vpnd test with a `# Rust test:` annotation, move the annotation to the remaining test, update `vpnd/test-transfer.json`, and run `make vpnd-parity-check`. When you delete a module together with its tests, keep each test that exercises code you retain and move it to the module for that code.

### Investigating and delegating

- Reuse what the session already established. `workspace-status` output, file contents and check results stay valid until a branch switch, an edit to those inputs or a new commit; do not read a file again or repeat a search to confirm them.
- Search before you read: `git grep -n` or `rg -n` with a path filter and `--max-count`, then read only the matching ranges. For a repository-wide question (unreferenced names, flags no caller passes), write a short script over `git ls-files` instead of reading files one at a time.
- Bound command output. Write long logs to a file and print only a `tail` or a `grep` for `FAILED`, `^E ` or `error`. For a failed CI job, save `gh api repos/po4yka/ripdpi-vpn-deploy/actions/jobs/<id>/logs --allow-escape-sequences` to a file and search it; `gh run view --log-failed` can print nothing.
- In zsh, an unquoted `$FILES` stays one word and an unmatched glob aborts the command, so pytest can collect nothing or the whole suite. Pass file lists through `xargs` or `${=FILES}`, and list files with `git ls-files '<pattern>'`.
- Delegate only independent work that needs more than a few tool calls, and name the files to read and the question to answer. A read-only survey of a whole area runs out of turns before it reports: run the mechanical scan yourself and delegate the follow-up questions. Do not repeat a delegated search in the main session.
- A subagent that is isolated in its own worktree is refused a compound command that names `git`, and any command that cannot be shown to stay inside that worktree (an inline script, output redirected to a path outside it). Say so in its brief: run each git command alone from the worktree, keep scratch output inside the worktree, and change files with the file-edit tool.
- Keep planning and review proportional. A small change needs no written plan or separate review pass; give a substantial behavior change one independent review of the patch and its check results. A read-only reviewer agent cannot load a skill, so its brief names the files to read: `.agents/skills/ponytail-review/SKILL.md`, and `.agents/skills/security-review/SKILL.md` when that skill's trigger applies. The brief also carries the exact patch, the acceptance criteria and the check results.
- Change files with the file-edit tool, not with `sed -i` or an inline script, so that each change shows as a reviewable diff. `.claude/settings.json` allows edits to source, test and documentation paths; workflow files, agent settings, agent instructions and skills still ask, and secret, state and variable files are denied.
- Run a command that can take more than two minutes (`make check`, Molecule, a `./taskctl` lifecycle command, a deploy) in the background with its log in a file and no short timeout, and tell the user the log path. Wait for its exit instead of polling with `sleep`. A silent run is not a hung run: check `ps` for the process before you stop it or start a second one.

## Where knowledge lives

- **Documentation map:** `docs/README.md` lists every page by Diátaxis type (tutorials, how-to, reference, explanation, decisions, research, archive) with its tier; `docs/STYLE.md` sets the folder, status-line, naming and template rules that `tests/unit/test_docs_index.py` enforces. `docs/reference/make-targets.md`, `docs/reference/vpnd-commands.md` and `docs/llms.txt` are generated by `make docs-reference`; never edit them by hand.
- **Local operator kit:** before collecting or moving credentials, issuing or revoking access, changing operator configuration, or preparing recovery, read [the local kit contract](docs/how-to/local-operator-kit.md). Use ignored `secrets/local/` as the private index of authoritative material and tool-specific paths. Update its private catalog after authorized changes; report completeness and gaps without exposing values. This does not authorize credential use or live actions.
- **Continuation and local maintenance:** after an interruption or worktree change, follow [operator maintenance](docs/how-to/operator-maintenance.md) before reusing live inputs or retrying a transaction. Use its release, encrypted diagnostic and selected-kit commands for those checks; retain current scoped authorization and distinguish local recovery proof from live health.

- **Per-folder `CLAUDE.md`** files hold each subtree's design decisions and pitfalls. Every `AGENTS.md` below the root is a symlink to its sibling `CLAUDE.md`; edit `CLAUDE.md`, never the symlink, and give every new `CLAUDE.md` an `AGENTS.md -> CLAUDE.md` symlink (`tests/unit/test_agent_instructions.py` enforces this, skill layout, and that cited paths exist). Claude Code loads these files automatically when it reads files in the folder; other agents started at the repo root should open the nearest one before changing files in that subtree. Coverage: `ansible/` and every role under `ansible/roles/`, `terraform/` (providers, shared, exception), `scripts/`, `tests/`, `tools/`, `vpnd/`, `attestations/`, `docs/measurements/`.
- Folder notes use three sections: **Design decisions** (why), **What's done well** (preserve), **Pitfalls**. When a change makes a note false, update it in the same change. Add a new note only for a non-obvious reason that the code and tests cannot show, and keep each `CLAUDE.md` within the line cap in `tests/unit/test_agent_instructions.py`: it loads into every session that reads the folder. Detailed per-area history lives in the sibling `DESIGN-NOTES.md` (`scripts/`, `tests/`); open only the section for the area you change. When the user says "remember", record it in the folder's `CLAUDE.md`, not in an external memory system.
- Change recipes live next to the code they change: new Ansible role in `ansible/CLAUDE.md`, new Terraform provider in `terraform/CLAUDE.md`, new `vpnd` subcommand in `vpnd/CLAUDE.md`, new AmneziaWG cohort in `ansible/roles/amneziawg/CLAUDE.md`.
- **Skills** live in `.agents/skills/<name>/SKILL.md`; `.claude/skills/<name>` (and `.github/skills/` for the tasking skills) are symlinks to them. The tasking skills are generated assets pinned by `tools/tasking/generated-assets.lock.json`, so refresh their hash when you edit one. The `ponytail`, `ponytail-review`, `ponytail-audit` and `ponytail-debt` skills are vendored unchanged from DietrichGebert/ponytail at commit 09c434ab (MIT, `LICENSE` in each folder), except two local edits to `ponytail`: the Claude-only `argument-hint` key is removed, and its test rule defers to Writing tests above. Refresh them by copying the upstream `skills/` folders again and reapplying those edits.
- **Site content:** an operator-owned public site is written with the `public-site-content` skill and built with `make public-site-build`; [the how-to](docs/how-to/public-site.md) gives the bundle contract. The skill writes local files only.
- **Execution skills** route fresh-node prerequisites through `vpn-bootstrap`, existing-node rollout through `vpn-deploy`, scoped evidence through `vpn-acceptance`, and temporary-resource retirement through `vpn-cleanup`. Role implementation uses `ansible-role` with the relevant `systemd`, `bash-scripting` and security guidance. Load only the workflow needed for the request; preparation of a PR does not authorize its live recipes.

## Source of truth

For monitoring changes or historical `MON-`/fleet-observation task lookups, start at [the current contract and task history](docs/reference/observability-operations.md#current-contract-and-task-history) before using an older proposal or acceptance receipt.

| Artifact | Canonical location | Must stay in sync with |
|---|---|---|
| CLI flags / subcommands | `vpnd/src/vpnd/cli.py` | README, runbooks |
| Package versions | release-please + `CHANGELOG.md` | `vpnd/pyproject.toml` `[project].version` |
| Secrets schema (structure) | `secrets/schema.json` + `scripts/validate-secrets.py` | `ansible/roles/*/`, `vpnd.secrets` |
| Secrets schema (coverage) | `scripts/check-secrets-coverage.py` | `secrets/prod.secrets.example.yaml`, all Jinja2 templates |
| RIPDPI bundle contract (v3) | `contract/ripdpi-bundle.schema.json` (+ `scripts/validate-bundle.py`, `docs/reference/ripdpi-bundle.md`) | `scripts/emit-bundle.sh`, `scripts/client_payload.py`, vendored copy in the RIPDPI client repo |
| Client field-report contract (v1) | `contract/client-field-report.schema.json` (+ `scripts/validate-field-report.py`, `docs/reference/ripdpi-bundle.md`) | `contract/negative/report-*.json`, vendored copy in the RIPDPI client repo |
| Client network-hint contract (v1) | `contract/client-network-hint.schema.json` (+ `docs/reference/ripdpi-bundle.md`) | `contract/negative/hint-*.json`, `ansible/roles/subscription-host/files/vpn-field-report.py`, vendored copy in the RIPDPI client repo |
| Node address check contract (v1) | `contract/node-address-check.schema.json` + `contract/node-address-check.golden.json` | `scripts/address_admission.py`, vendored copy in the RIPDPI client repo |
| AWG cohort fingerprint algorithm | `scripts/ripdpi_cohort_fingerprint.py` + `contract/cohort-fingerprint.golden.json` | `scripts/emit-bundle.sh`, client `AmneziaWgParameters.cohortFingerprint()` |
| AWG arm64 S3/S4 version floor | `contract/amneziawg-arm64-version-floor.json` | role/schema guard, client vendored policy |
| Protocol toggles | `ansible/group_vars/all.yml` + profile files `ansible/group_vars/vpn-*.yml` | `ansible/roles/*/`, vpnd config templates |
| Recipient page | `vpnd/templates/recipient.html` | `ansible/roles/subscription-host/`, `docs/demo/` |
| AWG cohort profiles | `ansible/roles/amneziawg/vars/cohorts/` | `docs/reference/awg-cohorts.md` |
| Xray version pin | SOPS secret `xray.version` (see `secrets/prod.secrets.example.yaml`) | `ansible/roles/xray/defaults/main.yml` (sentinel only), `docs/reference/xray-release-line.md` |

## Tasks and specifications

Use the `repo-task-board` skill for any portfolio task work; `docs/tasks/README.md` holds the full policy. The invariants:

- `docs/tasks/issues/` is the portfolio source of truth. Execution lives in exactly one of `docs/tasks/work/<TASK-ID>.md` or `openspec/changes/<change>/tasks.md`. `docs/tasks/board.md` is generated and read-only.
- Only `./taskctl` performs lifecycle transitions, mdtask access, OpenSpec archival, and validation. Never hand-edit the board, run upstream archive commands directly, pass `--no-validate`, invent task IDs, or delete a task before its terminal state is committed.
- OpenSpec is required for features, infrastructure behaviour, schemas, security/network changes, deployment lifecycle, and cross-repository contracts.
- Cross-repository references use qualified IDs such as `po4yka/RIPDPI#TRN-...`; validate with `make task-federation PEER_ROOT=<RIPDPI checkout>`. `make task-tools` installs the pinned tools; run `make task-check` before handoff.

## Coding mode

Apply the `ponytail` skill at its default `full` level to every code change and review: smallest complete change, reuse before new code, no unrequested abstraction. Its rules are not repeated here; its test rule defers to [Writing tests](#writing-tests). Where it conflicts with this file, the hard rules, decision boundaries and verification above win; Ponytail never removes security checks, secret handling or required gates. Use `ponytail-review` for change review, `ponytail-audit` for whole-repo audits, and `security-review` in addition when the change meets that skill's trigger.

## Commits

- Conventional Commits; release-please derives versions and `CHANGELOG.md`, which is never edited by hand. One bump per session by intent. Types and scopes: the `conventional-commit` skill.
- No `Co-Authored-By:` trailers and no mention of AI assistants or their vendors in commit messages (file names such as `CLAUDE.md` are fine). The commit-msg hook from `make install-hooks` rejects the trailer.
- After completing a task, run its verification and commit the task's own changes with explicit paths. Do not leave completed work uncommitted unless the user asks, and never sweep unrelated worktree changes into the commit.
- Keep diffs focused; a bug fix does not carry surrounding cleanup.
- Stage everything that belongs to the commit and confirm that `git diff --name-only` is empty before `git commit`. pre-commit moves unstaged changes into a patch file for the whole hook run, which takes minutes here; a hook auto-fix conflict can lose that patch, and the round trip deletes an untracked symlink that replaces a tracked directory. To split work across commits, save `git diff` to a file first. Do not run tests in the same worktree while the hooks run.
- On a cold hook cache, run `python3 -m pre_commit install-hooks` before the first commit. An environment that installs during `git commit` can replace the worktree index with the hook repository's entries; `git ls-files -s` then lists foreign paths, and `git read-tree HEAD` rebuilds the index without touching the working tree. A gitleaks hook failure "go version does not match" means an inherited `GOROOT`: commit with `env -u GOROOT git commit`.

## Worktrees and pull requests

- Start each change in its own worktree from fresh `origin/main`: `git fetch origin main`, then `git worktree add -b <branch> .worktrees/<branch-slug> origin/main`. A worktree that an agent tool creates stays where the tool puts it. Do not build on a checkout that holds the branch of another session.
- A new worktree has no ignored inputs. Run `make task-tools` before `./taskctl openspec` commands. For a live action, take the inventory and the input mappings from the local operator kit as [the deploy runbook](docs/how-to/deploy.md) describes; the checkout that owns a Terraform environment state is not always the one you work in.
- Open a pull request ready for review. Use a draft only when the merge must wait for a condition that you can name, and state that condition in the first line of the description and in your reply.
- After each push to a pull request, confirm that its head is your commit (`gh pr view <number> --json headRefOid`) and give the check state with the link (`gh pr checks <number>`): passed, pending or failed. Do not call a pull request ready to merge while a required check is pending or failed. The merge path is auto-merge (`gh pr merge <number> --auto --rebase`), which merges after the required checks pass; the user enables it or asks you to. A merge before CI completes uses the owner bypass, and a failure then shows only on `main`.
- `main` accepts rebase merges only ([branch protection](docs/how-to/branch-protection.md)). When `main` moves under an open pull request, rebase the branch; the push that follows is a force-push, so ask for it once and name the branch.
- When the user reports a merge, run `git fetch origin main`, confirm the state with `gh pr view <number> --json state`, report the `ci` run of the merge commit (`gh run list --workflow ci --branch main --limit 3`) with any failed job, and start the next change from the new `origin/main`. Then remove the worktree and the local branch that you created for the merged pull request (`git worktree remove`, `git branch -D`; a rebase merge makes `-d` refuse). This removal needs no separate authorization; every other branch deletion does.
