# Plan 016: Make contributor CI guidance drift-resistant

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, do not edit `plans/README.md`; the reviewer maintains the index in the advisory checkout.
>
> **Dependency preparation (run first in the isolated worktree)**: start from commit `7bdba37`, then apply dependency commits in this order: `d626c3f`, `4b772dd`, `72bdb4d`. All three are already DONE and must be ancestors of the Plan 016 commit. After applying them, verify `git diff --exit-code d626c3f -- CONTRIBUTING.md` is expected to show only Plan 013's data-plane wording, `git diff --exit-code 4b772dd -- CONTRIBUTING.md` is expected to show only Plan 010's Renovate wording, and `git diff --exit-code 72bdb4d -- tests/unit/test_governance_counts.py` produces no output. Inspect the combined `CONTRIBUTING.md` and stop if either dependency change is absent.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: 010 (`d626c3f`), 013 (`4b772dd`), 015 (`72bdb4d`)
- **Category**: docs
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

`CONTRIBUTING.md` manually claims a “12+ jobs” CI surface and a nine-role Molecule matrix, while the required workflow now has twelve default role scenarios, three non-default failure scenarios, and many additional required jobs. The same file recommends a partial local sequence instead of the repository's canonical `make check` parity gate. `docs/TESTING.md` already owns the complete live matrix, and `tests/unit/test_governance_counts.py` already compares that canonical row to `.github/workflows/ci.yml`. Make contributor guidance defer to those sources rather than duplicating fast-moving counts, and extend the existing governance test so this indirection remains explicit.

## Current state after dependencies

- `CONTRIBUTING.md:28-34` correctly describes installing pre-commit and commit-message hooks after Plan 013's unrelated governance cleanup, but says the hooks “gate git push” even though `Makefile:271-274` installs commit and commit-msg hooks only.
- `CONTRIBUTING.md:38-44` tells contributors to run `make validate`, `make install-hooks`, and `pre-commit run --all-files`; it omits `make ci-fast` and the canonical union target.
- `Makefile:337-365` defines `ci-fast` as the portable credential-free CI bundle and `check: validate ci-fast` as the full local parity gate.
- `CONTRIBUTING.md:46-65` manually states “12+ jobs,” enumerates an incomplete CI list, says Molecule covers nine roles, and lists informational workflows. These claims already drifted from live CI.
- `.github/workflows/ci.yml` currently has twelve default Molecule roles, three non-default scenarios, unit/Bats/snapshot/schema/Rust/Terraform jobs, and a final `required` aggregator. Counts and membership will continue changing.
- `docs/TESTING.md` owns the full coverage matrix. Its `git push` row enumerates all default and non-default Molecule scenarios and the complete required surface; its `make check` row defines the local boundary and exclusions.
- `tests/unit/test_governance_counts.py`, including Plan 015's audit-status guard, already parses `.github/workflows/ci.yml` and asserts that the `docs/TESTING.md` `git push` row includes every default Molecule role, every required non-default scenario, and unit tests.
- Plan 010 changes the `CONTRIBUTING.md` Conventional Commits table to name Renovate; Plan 013 replaces the prohibited external rationale pointer. Both changes must remain in the dependency baseline and in the final tree.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Dependency ancestry | `git merge-base --is-ancestor d626c3f HEAD && git merge-base --is-ancestor 4b772dd HEAD && git merge-base --is-ancestor 72bdb4d HEAD` | exit 0 |
| Fragile-count scan | `rg -n '12\+ jobs|matrix: [0-9]+ roles|molecule \(matrix:|Dependabot uses this automatically|external rationale pointer' CONTRIBUTING.md` | no output |
| Canonical pointers | `rg -n 'make check|\.github/workflows/ci\.yml|docs/TESTING\.md|required checks' CONTRIBUTING.md` | all four concepts appear in the setup/pre-flight/CI guidance |
| Focused governance test | `mise exec --no-deps -- python3 -m pytest tests/unit/test_governance_counts.py -q` | one test passes |
| Full unit regression | `mise exec --no-deps -- python3 -m pytest tests/unit/ -q` | all unit tests pass with unchanged collection count |
| Diff hygiene | `git diff --check --cached` | exit 0, no output |
| Commit-scoped secret scan | after commit, `gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |

## Scope

**In scope** (the only files the Plan 016 commit may modify relative to its dependency baseline):

- `CONTRIBUTING.md`
- `tests/unit/test_governance_counts.py`

**Out of scope** (do not modify):

- `.github/workflows/ci.yml`, any other workflow, `docs/TESTING.md`, Makefile targets, pre-commit configuration, scripts, roles, templates, snapshots, generated files, or runtime behavior.
- Adding a new CI job, changing which checks are required, changing branch protection, installing tools, or trying to make Molecule/GitHub-native/credentialed gates part of `make check`.
- Replacing the canonical `docs/TESTING.md` matrix with a new generated document or duplicating its role/job list in contributor guidance.
- Reverting Plan 010's Renovate wording, Plan 013's repository-native data-plane rationale, or Plan 015's audit disposition assertions.
- Changing contributor policy outside first-time setup, local pre-flight, and CI gates; reflowing unrelated prose; updating counts elsewhere.
- Updating `CHANGELOG.md`, plans, or any third file in the Plan 016 commit.

## Git workflow

- Branch: `codex/advisor-016-drift-resistant-contributor-ci`.
- Start from `7bdba37` and apply `d626c3f`, `4b772dd`, then `72bdb4d` before editing. Resolve no dependency conflict by invention; STOP if they do not apply cleanly.
- Create one focused incremental Conventional Commit: `docs(contributing): defer CI coverage to canonical matrix`.
- Do not push, merge, or open a pull request.

## Steps

### Step 1: Make local setup and pre-flight describe the real hook/gate boundary

In `CONTRIBUTING.md`:

- Keep `make install-hooks` as the one-time setup command, but say it installs commit-time and commit-message hooks; do not say those hooks gate `git push`.
- Replace the partial pre-flight command block with `make check` as the canonical local pre-PR parity command.
- Explain concisely that `make check` is the union of `make validate` and `make ci-fast`, fails closed on missing tools, and excludes Molecule containers, GitHub-native security services, and credentialed deploy jobs as documented in `docs/TESTING.md`.
- If a role is changed, recommend the existing targeted `make molecule-test ROLE=<name>` command separately. Do not tell contributors to run every Molecule scenario locally.
- Do not change Makefile behavior or imply local parity is byte-for-byte identical to all remote CI.

**Verify**: canonical-pointer scan finds `make check` and `docs/TESTING.md`; the old `git push` hook claim is absent.

### Step 2: Replace the duplicated CI inventory with stable ownership pointers

Rewrite only the `## CI gates` section:

- State that `.github/workflows/ci.yml` owns the required PR workflow and its `required checks` aggregator fails unless every required job succeeds.
- State that `docs/TESTING.md` owns the human-readable coverage matrix, including default Molecule roles, non-default failure scenarios, CI-only services, and local-vs-remote boundaries.
- Tell contributors to update the workflow and canonical testing row together when changing required coverage; the existing governance test checks the Molecule membership relationship.
- Remove “12+ jobs,” “matrix: 9 roles,” the hand-maintained bullet inventory, and the separate informational list. Do not replace them with new numeric totals or a new role list.
- Preserve the existing link to `docs/TESTING.md`, now as the authoritative source rather than a secondary “full matrix” after a stale summary.

**Verify**: fragile-count scan has no matches and a manual read confirms no default-role/job enumeration remains in `CONTRIBUTING.md`.

### Step 3: Extend the existing governance test to protect the ownership chain

Within `test_governance_counts_match_live_repository` in `tests/unit/test_governance_counts.py`, after the existing `testing`/CI matrix assertions:

1. Read `CONTRIBUTING.md` and isolate text between `## Local pre-flight` and `## Adding a new role / template / script` so assertions cover only the relevant two sections.
2. Assert the slice contains ``make check``, `.github/workflows/ci.yml`, `docs/TESTING.md`, and the phrase `required checks`.
3. Assert `Makefile` contains the exact target relationship `check: validate ci-fast`.
4. Assert the contributor slice does not match case-insensitive numeric inventory patterns such as `\b\d+\+? jobs\b` or `matrix:\s*\d+\s+roles`.
5. Assert the full contributor document still contains `Renovate PRs` and the repository-native data-plane rationale fragment `Ansible plus systemd own runtime state`, protecting the applied dependencies.

Do not assert the full CI prose, exact line numbers, individual role names, or job names. Do not add a test function or change test collection count.

**Verify**: focused governance test passes as one test.

### Step 4: Run regression and commit the incremental slice normally

Run the full unit suite. Inspect the full dependency history and the Plan 016 diff separately:

- `git diff --stat 7bdba37..HEAD` may include dependency files; this is expected.
- Before committing Plan 016, `git diff --stat` must list exactly the two in-scope files.
- After committing, `git diff-tree --no-commit-id --name-only -r HEAD | sort` must list exactly the two Plan 016 files.
- Confirm `git merge-base --is-ancestor` succeeds for all three dependency commit identities.

Stage exactly the two files and run `git diff --check --cached`. Commit with hooks enabled using `docs(contributing): defer CI coverage to canonical matrix`; never skip hooks. Run commit-scoped gitleaks and confirm the isolated worktree is clean.

## Test plan

- The existing CI-to-`docs/TESTING.md` assertions continue verifying every live default and non-default Molecule scenario.
- New assertions verify that contributor guidance points at that canonical matrix and the actual `make check` dependency relationship instead of duplicating mutable counts.
- Dependency-preservation assertions prevent the combined baseline from regressing Renovate ownership or repository-native architecture wording.
- Full unit regression verifies governance, documented counts, and all existing repository contracts without adding a test.

## Done criteria

- [ ] Contributor setup accurately describes commit-time hooks rather than a push hook.
- [ ] Local pre-flight leads with `make check`, explains its union and exclusions, and retains targeted Molecule guidance.
- [ ] CI guidance names the live workflow, required aggregator, and `docs/TESTING.md` as canonical without numeric job/role inventories.
- [ ] The governance test protects the contributor-to-canonical ownership chain, actual Makefile target relationship, absence of fragile counts, and all dependency wording.
- [ ] Plans 010, 013, and 015 are ancestors of the Plan 016 commit.
- [ ] Focused governance and full unit tests pass; diff hygiene, hooks, and scoped gitleaks pass.
- [ ] Exactly two Plan 016 files are committed; the executor reports the commit SHA; the isolated worktree is clean.

## STOP conditions

Stop and report instead of improvising if:

- Any dependency commit does not apply cleanly to `7bdba37`, is missing, or its expected wording/test block is absent after preparation.
- `make check` no longer equals `validate ci-fast`, or `docs/TESTING.md` no longer owns/accurately reflects the live CI matrix.
- Accurate contributor guidance requires changing CI, Makefile, pre-commit hooks, testing docs, branch protection, or any third file.
- A robust test requires enumerating individual roles/jobs again or adding a new test that changes documented counts.
- Focused/full tests, hooks, scans, or ancestry checks fail twice after one reasonable two-file correction.
- A generated artifact, dependency change, network lookup, secret, external knowledge-store reference, or runtime behavior change is required.

## Maintenance notes

The ownership chain is intentional: `.github/workflows/ci.yml` defines required execution, `docs/TESTING.md` is the canonical human matrix and is checked against that workflow, and `CONTRIBUTING.md` points contributors to those sources without repeating counts. Future CI changes should update the workflow and testing matrix together; contributor guidance should change only when that ownership model changes.
