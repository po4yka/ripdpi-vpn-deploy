# Plan 001: Ignore tools/tasking/node_modules in the repository .gitignore

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- .gitignore tools/tasking`
> If `.gitignore` changed since `a0ff105`, re-read it and confirm the
> "Current state" facts still hold before proceeding.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug (repo hygiene / reproducibility)
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

The 80-package `tools/tasking/node_modules/` tree (installed by `make task-tools`) is currently excluded from git only by one operator's *global* git config (`~/.config/git/ignore`). On any fresh clone — another workstation, an agent worktree, a reinstall — the directory appears untracked, and a blanket `git add -A` commits platform-specific binaries into a reproducibility-focused IaC repo. The current cleanliness is an accident of one machine.

## Current state

- `.gitignore` — root ignore file. Verified contents contain NO `node_modules` pattern anywhere (sections: Terraform, Ansible, Secrets, Python, Molecule, Operator-side artifacts, OS, Editor, pre-commit, pytest, Claude/OMC state, SBOM). Tail excerpt:

  ```
  # SBOM artifacts (reproducible from secrets schema via make emit-sbom)
  sbom/*.json
  ```

- Evidence of the gap: `git check-ignore -v tools/tasking/node_modules` resolves to `/Users/<you>/.config/git/ignore:30` — the operator-global file, not any repo file.
- `tools/tasking/package.json` declares `"private": true`; node_modules is produced by `npm ci --prefix tools/tasking --ignore-scripts` (Makefile target `task-tools`).

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Confirm current gap | `git check-ignore -v tools/tasking/node_modules` | points at `~/.config/git/ignore` (or no match on clean machines) |
| Ignore-pattern syntax check | `git check-ignore -v tools/tasking/node_modules` after fix | points at `.gitignore:<line>` |
| Contract test | `python3 -m pytest tests/unit/test_gitignore_contracts.py -q` | all pass |
| Repo gate (tasking untouched, quick sanity) | `OPENSPEC_TELEMETRY=0 ./taskctl validate` | `Task contracts valid …`, exit 0 |

## Scope

**In scope** (the only files you should modify):
- `.gitignore`
- `tests/unit/test_gitignore_contracts.py` (create)

**Out of scope** (do NOT touch):
- `~/.config/git/ignore` — the operator's personal global config; never edit.
- `tools/tasking/**` contents, lockfiles, generated-assets lock.
- Any other ignore rules (secrets sections etc.).

## Git workflow

- Branch: `advisor/001-node-modules-gitignore`
- One commit: `fix: ignore tools/tasking/node_modules in repository gitignore`
  (Conventional Commits; no Co-Authored-By trailers; subject ≤72 chars.)
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add the ignore rule

Append a new section to `.gitignore`, right after the existing "Operator-side artifacts" block (`state-backups/ share/ output/ tmp/ …`):

```gitignore

# Tasking toolchain deps (reproducible via `make task-tools`; never committed)
tools/tasking/node_modules/
```

**Verify**: `git check-ignore -v tools/tasking/node_modules` → output references `.gitignore:` (not `~/.config/git/ignore`). On a machine WITHOUT the global ignore this previously returned nothing; after the fix it must always match the repo rule.

### Step 2: Pin the contract with a unit test

Create `tests/unit/test_gitignore_contracts.py`. Style: plain stdlib pytest reading repo files — model after `tests/unit/test_task_contract_workflow.py` (asserts literal strings in tracked files; no fixtures needed):

```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

def test_node_modules_is_ignored_by_repo_gitignore() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "tools/tasking/node_modules/" in text, (
        "tools/tasking/node_modules/ must stay ignored by the REPO .gitignore; "
        "relying on an operator-global git ignore silently breaks fresh clones"
    )
```

**Verify**: `python3 -m pytest tests/unit/test_gitignore_contracts.py -q` → `1 passed`.

## Test plan

- New test above covers exactly this regression class (rule removed → red).
- Negative sanity: temporarily comment the rule, re-run the test, observe failure, restore. Do not commit the commented state.

## Done criteria

- [ ] `git check-ignore -v tools/tasking/node_modules` names `.gitignore`
- [ ] `python3 -m pytest tests/unit/test_gitignore_contracts.py -q` → 1 passed
- [ ] `git status --porcelain` shows only `.gitignore` + the new test file
- [ ] `plans/README.md` status row updated

## STOP conditions

- `.gitignore` gained a `node_modules` rule from another source since planning (finding already fixed independently) — report instead of duplicating.
- `git check-ignore` behaves unexpectedly (e.g. matches but `git status` still lists files under the directory) — report; there may be negated rules elsewhere.

## Maintenance notes

- Reviewers: confirm the rule is anchored under `tools/tasking/` rather than a bare global `node_modules/` — the repo intentionally scopes ignores narrowly.
- If a future vendored dependency ever needs committed node artifacts, this rule will need an explicit negation; do not weaken it casually.
