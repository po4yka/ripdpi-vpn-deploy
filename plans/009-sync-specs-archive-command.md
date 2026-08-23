# Plan 009: Fix the rejected `openspec cli archive` references in generated sync-specs skill

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- .agents/skills/openspec-sync-specs/SKILL.md tools/tasking/generated-assets.lock.json scripts/tasks/taskctl.py`

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug (generated-doc drift)
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

The generated skill `.agents/skills/openspec-sync-specs/SKILL.md` instructs agents to run `./taskctl openspec cli archive …` — but `archive` is absent from `SAFE_OPENSPEC_COMMANDS` in the taskctl engine, so that passthrough hard-fails mid-workflow and points to `./taskctl openspec archive`. An agent following the skill hits a wall; worse, the dead-end invites fallback to raw `openspec archive`, which repo policy explicitly forbids. The layer's own docs teaching a forbidden command erodes the fail-closed story.

## Current state

- The three offending sites in `.agents/skills/openspec-sync-specs/SKILL.md` (verified):
  - line 143: `(this is what \`./taskctl openspec cli archive\` does; it warns and moves on)`
  - line 148: `(this is what \`./taskctl openspec cli archive\` does); only write a brief TBD placeholder when it does not`
  - line 229: `…\`./taskctl openspec cli validate\` and \`./taskctl openspec cli archive\` both reject one that drops a scenario…`
- Allow-list in `scripts/tasks/taskctl.py` (~lines 98–101):

  ```python
  SAFE_OPENSPEC_COMMANDS = frozenset(
      ("list", "show", "status", "instructions", "templates", "schemas", "schema", "validate", "doctor", "context", "new", "change", "spec")
  )
  ```

  → `validate` passes; only `archive` fails. The correct invocation per taskctl's own error message is `./taskctl openspec archive`.
- Generated assets are hash-pinned by `tools/tasking/generated-assets.lock.json` (`"files": { ".agents/skills/openspec-sync-specs/SKILL.md": "<sha256>", … }`), enforced by `validate_generated_assets()` in taskctl.py — editing the SKILL.md without updating its lock hash makes `./taskctl validate` (and `make task-check`) FAIL. The lock update is therefore part of this fix, not optional.
- Skills are produced from the pinned upstream packages (`tools/tasking/package.json`: mdtask 0.1.17, @fission-ai/openspec 1.8.0) with repo-policy edits applied post-generation.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Find all bad refs | `grep -rn "openspec cli archive" .agents/skills/` | hits shrink to zero after fix |
| Recompute hash | `shasum -a 256 .agents/skills/openspec-sync-specs/SKILL.md` | new digest |
| Contract gate | `OPENSPEC_TELEMETRY=0 ./taskctl validate` | exit 0 AFTER lock update; exit ≠ 0 between edit and lock update |
| Full gate | `make task-check` | exit 0 |

## Scope

**In scope**:
- `.agents/skills/openspec-sync-specs/SKILL.md`
- `tools/tasking/generated-assets.lock.json` (single file-entry hash)

**Out of scope**:
- `SAFE_OPENSPEC_COMMANDS` itself — do NOT add `archive` to the allow-list; archiving must go through the dedicated subcommand.
- Other skills' store-flow drift (separate finding, TASKING-13).
- Regeneration tooling.

## Git workflow

- Branch: `advisor/009-sync-specs-archive-cmd`
- Commit: `fix(tasking): point sync-specs skill at the supported archive command`

## Steps

### Step 1: Sweep for every affected phrase

```bash
grep -rn "openspec cli archive" .agents/skills/
```

Expected today: 3 hits, all in `openspec-sync-specs/SKILL.md`. If other skills appear, include them (same mechanical substitution) and note them in the commit body.

### Step 2: Rewrite each reference to the supported command

Replace `./taskctl openspec cli archive` with `./taskctl openspec archive`, preserving surrounding prose. Sanity-check each edited sentence still reads correctly in context (lines 143, 148, 229). Do NOT touch `cli validate` mentions — that form is allow-listed and correct.

**Verify**: `grep -rn "openspec cli archive" .agents/skills/` → no matches; `grep -c "taskctl openspec archive" .agents/skills/openspec-sync-specs/SKILL.md` → ≥3.

### Step 3: Update the asset-lock hash

```bash
NEWHASH="$(shasum -a 256 .agents/skills/openspec-sync-specs/SKILL.md | awk '{print $1}')"
```

Update ONLY the value of the key `".agents/skills/openspec-sync-specs/SKILL.md"` inside `tools/tasking/generated-assets.lock.json`, preserving JSON formatting/key order (edit by hand or with jq; verify with `python3 -m json.tool tools/tasking/generated-assets.lock.json >/dev/null`).

**Verify**: `python3 -m json.tool tools/tasking/generated-assets.lock.json > /dev/null && echo valid-json`.

### Step 4: Let the validator be the oracle

```bash
OPENSPEC_TELEMETRY=0 ./taskctl validate && make task-check
```

The engine recomputes every pinned hash and byte-compares — if your hash or formatting is off, it names the drifted asset. Expected: `Task contracts valid (10 tasks, 49 steps)` / exit 0.

## Test plan

The validator IS the test (tamper-evident lock). No unit additions needed; Step 4 doubles as regression proof since a stale hash previously failed closed.

## Done criteria

- [ ] Zero `openspec cli archive` references remain under `.agents/skills/`
- [ ] Lock entry updated; JSON parses; `./taskctl validate` exit 0
- [ ] `make task-check` exit 0
- [ ] Diff limited to one SKILL.md + one lock-file line; `plans/README.md` row updated

## STOP conditions

- Your sweep finds the phrase in files OUTSIDE `.agents/skills/` (e.g. vendored templates inside node_modules are fine to leave; tracked repo sources are not) — report any tracked source hit.
- `./taskctl validate` reports drift on an asset you did NOT touch — someone regenerated skills concurrently; stop and report.
- Editing the sentence breaks its meaning (e.g. the passage describes CLI internals, not an operator command) — quote the full paragraph in your report instead of forcing the substitution.

## Maintenance notes

- Regenerating skills from upstream will re-introduce the wrong command. Add this patch step to whatever regeneration runbook exists BEFORE the next regeneration, or the drift returns silently.
- Reviewers: confirm no `archive` was added to SAFE_OPENSPEC_COMMANDS as a shortcut.
