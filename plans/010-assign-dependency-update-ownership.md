# Plan 010: Make Renovate the sole dependency-update PR owner

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- .github/dependabot.yml renovate.json docs/TESTING.md CONTRIBUTING.md tests/unit/test_dependency_update_ownership.py`
> If any existing in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: migration
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

The repository currently configures both Dependabot and Renovate to open version-update pull requests for GitHub Actions, Terraform, and Python. That overlap creates duplicate or racing pull requests with different schedules and grouping policies, wasting CI and maintainer attention. Renovate is already the documented owner, uniquely covers Rust plus the repository's custom sing-box managers, and should become the single explicit version-update surface.

## Current state

- `.github/dependabot.yml:12-91` configures weekly version updates for GitHub Actions, all three Terraform provider roots, and root Python requirements. It has no ecosystem that Renovate does not already support:

```yaml
updates:
  - package-ecosystem: github-actions
    directory: /
  - package-ecosystem: terraform
    directory: /terraform/providers/upcloud
  - package-ecosystem: terraform
    directory: /terraform/providers/hetzner
  - package-ecosystem: terraform
    directory: /terraform/providers/vultr
  - package-ecosystem: pip
    directory: /
```

- `renovate.json:3-30` extends `config:recommended`, pins GitHub Action digests, enables vulnerability-alert handling, and defines grouping for Terraform, Cargo, and GitHub Actions. Because `enabledManagers` is absent, the intended built-in manager ownership is implicit.
- `renovate.json:32-52` defines two `customType: "regex"` managers for Hysteria Realm and Snell sing-box pins. If `enabledManagers` is introduced, `custom.regex` must be included or those managers silently stop running.
- The supported manager identifiers needed by this repository are `cargo`, `github-actions`, `pip_requirements`, `terraform`, and `custom.regex`. The first four own `vpnd/Cargo.toml`/lockfile, workflow action references, `requirements.txt`, and Terraform roots; the last preserves both current custom regex managers.
- `docs/TESTING.md:126-156` already presents Renovate as the weekly dependency-update owner and lists all five managed surfaces, but it does not state that the other version-update bot is intentionally disabled.
- `CONTRIBUTING.md:17` says `chore:` is for tooling and dependencies and parenthetically attributes that behavior to Dependabot, contradicting the canonical testing documentation.
- `tests/unit/test_renovate_managers.py` is the existing structural pattern: load `renovate.json` with stdlib `json`, inspect manager fields, and assert documentation matches the configuration. Create a separate ownership-focused test rather than mixing bot exclusivity into the transport-pin safety test.
- Repository convention: configuration tests use plain pytest and repository-relative `Path`; prose paragraphs are one logical line unless the existing file is locally hard-wrapped; dependency/tooling commits use Conventional Commits; do not edit `CHANGELOG.md`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | command in the plan header | no output |
| JSON syntax | `mise exec -- python3 -m json.tool renovate.json >/dev/null` | exit 0 |
| Focused ownership tests | `mise exec -- python3 -m pytest tests/unit/test_dependency_update_ownership.py tests/unit/test_renovate_managers.py -q` | all tests pass |
| Full unit regression | `mise exec -- python3 -m pytest tests/unit/ -q` | all unit tests pass |
| Diff hygiene | `git diff --check` | exit 0, no output |
| Commit-scoped secret scan | after commit, `mise exec -- gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |

## Scope

**In scope** (the only files you may modify):

- `.github/dependabot.yml` (delete)
- `renovate.json`
- `docs/TESTING.md`
- `CONTRIBUTING.md`
- `tests/unit/test_dependency_update_ownership.py` (new)

**Out of scope** (do not modify):

- Renovate schedules, grouping behavior, vulnerability-alert behavior, digest pinning, custom regexes, datasources, versioning, package rules, or labels except where `enabledManagers` makes current ownership explicit.
- GitHub repository settings, Dependabot security alerts, vulnerability-reporting settings, branch protection, installed GitHub Apps, secrets, labels, existing pull requests, or remote bot configuration. Deleting `.github/dependabot.yml` disables only repository-configured Dependabot version updates.
- Dependency versions, lockfiles, manifests, Terraform provider constraints, workflow action digests, Ansible Galaxy pins, or binary pins.
- Adding a second update bot for an unsupported ecosystem. Future ownership changes require a separately reviewed policy change.
- `tests/unit/test_renovate_managers.py`; use it as a pattern but keep its secret-backed transport-pin contract unchanged.
- CI workflows, Makefile targets, root/other `CLAUDE.md` files, `CHANGELOG.md`, or unrelated documentation/tests.

## Git workflow

- Branch: `codex/advisor-010-dependency-update-ownership`
- Create one focused Conventional Commit: `chore(deps): make renovate sole update owner`.
- Stage exactly the five in-scope paths, including the Dependabot deletion.
- Do not push, merge, cherry-pick, or open a pull request.

## Steps

### Step 1: Make Renovate's manager ownership explicit

Add this exact top-level manager allowlist to `renovate.json` without changing existing schedules, rules, or custom manager definitions:

```json
"enabledManagers": [
  "cargo",
  "custom.regex",
  "github-actions",
  "pip_requirements",
  "terraform"
]
```

Keep the list alphabetical and place it near the other top-level policy settings before `packageRules`. `custom.regex` is load-bearing because `customManagers` are restricted by `enabledManagers` too. Do not add `ansible-galaxy`: the repository intentionally keeps Galaxy updates manual. Do not include broad category names such as `python`, `rust`, or `iac`; `enabledManagers` accepts concrete manager identifiers and the allowlist must prevent accidental expansion.

Delete `.github/dependabot.yml` entirely. Do not replace it with an empty file or a `version: 2` document with no updates; absence makes the single-owner policy unambiguous and avoids GitHub configuration churn.

**Verify**: `mise exec -- python3 -m json.tool renovate.json >/dev/null` → exit 0, and `test ! -e .github/dependabot.yml` → exit 0.

### Step 2: Align maintainer-facing documentation

In `docs/TESTING.md`'s dependency-update section, add one concise paragraph stating that Renovate is the sole automated version-update PR owner, `.github/dependabot.yml` is intentionally absent to prevent duplicate PRs, and the manager allowlist is the canonical ownership boundary. Preserve the existing ecosystem matrix and manual Xray, AmneziaWG, and Galaxy policies unchanged.

In `CONTRIBUTING.md`, replace the `chore:` row's Dependabot-specific parenthetical with Renovate-neutral ownership, for example `Tooling and dependency updates, including Renovate PRs.` Do not claim every Renovate commit necessarily uses a specific semantic prefix beyond what the repository actually enforces.

Do not add external citations or name external knowledge stores. Match each file's existing paragraph wrapping style rather than reflowing surrounding text.

**Verify**: `rg -n "Dependabot uses|\.github/dependabot\.yml is intentionally absent|sole automated version-update" CONTRIBUTING.md docs/TESTING.md` → no stale attribution and both new policy phrases are present.

### Step 3: Add a regression for exclusive ownership and complete coverage

Create `tests/unit/test_dependency_update_ownership.py` using `tests/unit/test_renovate_managers.py` as the style pattern. Add focused tests that prove:

1. `.github/dependabot.yml` does not exist, with a failure message explaining that reintroducing it would create duplicate version-update ownership.
2. `renovate.json["enabledManagers"]` is exactly the five-manager set `cargo`, `custom.regex`, `github-actions`, `pip_requirements`, and `terraform`; assert set equality for coverage and list equality against `sorted(...)` for deterministic review order.
3. Every `matchManagers` entry in `packageRules` belongs to the enabled built-in managers, and the presence of `customManagers` requires `custom.regex` in the allowlist. This must fail if a future rule names a disabled manager.
4. `docs/TESTING.md` states Renovate is the sole version-update owner and names the intentional absence of `.github/dependabot.yml`; `CONTRIBUTING.md` contains no `Dependabot uses this automatically` attribution.

Keep the test structural and offline: no GitHub API, Renovate CLI, npm install, network access, YAML dependency, or inspection of remote repository settings. Do not duplicate the detailed safe-pin assertions already owned by `test_renovate_managers.py`.

**Verify**: run the focused ownership-test command from the command table → all tests pass.

### Step 4: Run unit regression and commit normally

Run the full unit suite, JSON syntax check, and `git diff --check`. Inspect the full diff and confirm only the five in-scope paths changed. Commit normally with hooks enabled using `chore(deps): make renovate sole update owner`; never use `--no-verify` or a skip variable. After commit, run the commit-scoped gitleaks command and confirm the isolated worktree is clean.

**Verify**: `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly `.github/dependabot.yml`, `CONTRIBUTING.md`, `docs/TESTING.md`, `renovate.json`, and `tests/unit/test_dependency_update_ownership.py`; `git status --short` has no output; scoped gitleaks exits 0.

## Test plan

- The new focused test treats bot ownership as repository policy: one absent redundant configuration and one explicit Renovate manager allowlist.
- Set equality catches missing or extra managers; sorted-list equality keeps JSON review deterministic.
- Package-rule coverage catches a manager rule that is silently disabled by the allowlist.
- Custom-manager coverage protects the Hysteria Realm and Snell regex managers when manager restrictions change.
- Documentation assertions prevent the contributor guide and canonical testing matrix from diverging again.
- The existing `test_renovate_managers.py` remains green and continues owning the separate Xray/AmneziaWG safety boundary.

## Done criteria

- [ ] `.github/dependabot.yml` is deleted and no replacement Dependabot version-update configuration is added.
- [ ] `renovate.json` explicitly enables exactly `cargo`, `custom.regex`, `github-actions`, `pip_requirements`, and `terraform`, without changing existing schedules, grouping, alerts, or custom-manager behavior.
- [ ] `docs/TESTING.md` identifies Renovate as sole automated version-update owner and records why the Dependabot config is absent.
- [ ] `CONTRIBUTING.md` no longer attributes dependency commits to Dependabot.
- [ ] The new ownership test meaningfully guards exclusivity, exact manager coverage, package-rule compatibility, custom regex enablement, and documentation alignment.
- [ ] JSON syntax, focused ownership tests, and the full unit suite pass.
- [ ] `git diff --check` and commit-scoped gitleaks pass.
- [ ] Exactly five in-scope paths are committed; the executor reports the commit SHA; the isolated worktree is clean.

## STOP conditions

Stop and report instead of improvising if:

- Any existing in-scope file drifted from `7bdba37` or no longer matches the excerpts.
- Dependabot manages a checked-in ecosystem that Renovate cannot cover with the five named managers.
- The repository relies on `.github/dependabot.yml` for a security-alert or vulnerability-reporting behavior that would be disabled by deleting version-update configuration.
- `enabledManagers` disables either current custom regex manager, the Cargo/GitHub Actions/pip/Terraform surfaces, or requires another manager for a checked-in manifest that the existing documentation promises Renovate covers.
- A valid Renovate configuration requires changing schedules, grouping, package rules, custom regexes, dependency pins, workflows, or remote settings.
- The test requires network access, installing Renovate, querying GitHub, or touching a sixth file.
- A verification or normal commit hook fails twice after one reasonable correction within scope.
- Any secret, token, live pull request, remote configuration, or dependency update is required.

## Maintenance notes

The `enabledManagers` list is the dependency-update ownership boundary. Adding a new manifest type requires an explicit manager addition, documentation update, and ownership-test change in one review. Do not reintroduce `.github/dependabot.yml` for an ecosystem already in the Renovate allowlist; if a future ecosystem genuinely needs another bot, document a disjoint ownership matrix and change this exclusive policy deliberately rather than allowing silent overlap.
