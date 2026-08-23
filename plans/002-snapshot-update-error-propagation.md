# Plan 002: Make snapshot-update fail loudly on render errors

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. On
> any STOP condition, stop and report. When done, update your row in
> `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- scripts/render-snapshots.py tests/unit/test_render_snapshots.py`
> If `scripts/render-snapshots.py` changed since `a0ff105`, re-read it and
> verify the "Current state" excerpts still match; otherwise treat as STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug (false-green tooling)
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

`scripts/render-snapshots.py --update` is the tool operators run to refresh golden snapshots. Today, when a template fails to render (Jinja2 `UndefinedError` or any exception), the error is recorded into the `diffs` list — but the update-mode epilogue never reads `diffs`: it prints "no goldens needed updating." and exits 0. A broken template plus a golden refresh produces a success message while the stale golden stays in place, so the subsequent `make snapshot-check` can pass against output the broken template never produced. The module docstring promises drift surfacing; the update path violates that contract.

## Current state

- `scripts/render-snapshots.py` — renders every `ansible/roles/**/*.j2` template with the canonical Ansible context (`template_render.py`) and byte-compares/writes goldens under `tests/snapshot/golden/`.
- Render loop records errors but continues (verified excerpt, lines ~55–62):

  ```python
  try:
      output = render_template(tpl, vars_)
  except UndefinedError as exc:
      diffs.append(f"{rel}: undefined — {exc}")
      continue
  except Exception as exc:
      diffs.append(f"{rel}: render error — {exc}")
      continue
  ```

- Update path writes goldens for successful renders (lines ~65–70):

  ```python
  if args.update:
      golden.parent.mkdir(parents=True, exist_ok=True)
      if not golden.exists() or golden.read_text() != output:
          golden.write_text(output)
          updated.append(rel)
      continue
  ```

- Update epilogue consults only `updated`/`stale`, then unconditionally `return 0` (lines ~88–108). `diffs` is printed ONLY in check mode ("Snapshot drift detected:", after the `if args.update:` block returns).
- Repo conventions: stdlib-only Python, no emoji, explicit types where they aid readability; unit tests are plain pytest under `tests/unit/` using `tmp_path`. Exemplar of a small CLI-style module test: `tests/unit/test_repository_identifier_policy.py` style (import module, call function, assert).

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax | `python3 -m py_compile scripts/render-snapshots.py` | exit 0 |
| Check mode still green | `python3 scripts/render-snapshots.py` | exit 0 (repo is currently consistent) |
| New unit tests | `python3 -m pytest tests/unit/test_render_snapshots.py -q` | all pass |
| Local gate slice | `make shellcheck && python3 -m pytest tests/unit -q -k "render or snapshot"` | pass |

## Scope

**In scope**:
- `scripts/render-snapshots.py`
- `tests/unit/test_render_snapshots.py` (create)

**Out of scope**:
- `scripts/template_render.py` (render engine itself — separate audit findings exist, do not touch).
- Golden files under `tests/snapshot/golden/**`.
- `check-templates-render.py`.

## Git workflow

- Branch: `advisor/002-snapshot-update-errors`
- Commit style: `fix: surface render errors in snapshot-update mode` (+ optional second `test:` commit). No Co-Authored-By.

## Steps

### Step 1: Restructure main() so the update/check paths share an error report

Read the whole file first. Refactor minimally: keep the loop as-is, but in the update-mode epilogue, AFTER writing successful goldens and removing stale ones, add:

```python
if diffs:
    print(
        f"{len(diffs)} template(s) failed to render; goldens for them were "
        "NOT refreshed:",
        file=sys.stderr,
    )
    for d in diffs:
        print(d, file=sys.stderr)
    return 1
```

placed immediately before the final `return 0` of the `args.update` branch. Semantics: successful goldens ARE written (operator keeps legitimate refreshes), broken templates are loudly reported with non-zero exit.

**Verify**: `python3 -m py_compile scripts/render-snapshots.py` → exit 0; then `python3 scripts/render-snapshots.py` → exit 0 (healthy repo unaffected).

### Step 2: Make the behavior unit-testable without touching real goldens

If the script's body already runs at import inside a `main()`-style function taking no arguments, extract the core into:

```python
def run(roles_dir: Path, golden_dir: Path, *, update: bool) -> int: ...
```

with the module entry point delegating to the real directories. Do NOT change rendering semantics, ordering (`sorted`), or the synthetic-facts context wiring.

**Verify**: `python3 scripts/render-snapshots.py` → exit 0 (behavior unchanged); `python3 -m py_compile scripts/render-snapshots.py` → exit 0.

### Step 3: Write the regression tests

Create `tests/unit/test_render_snapshots.py` using `tmp_path`:

1. Build a fake roles tree: `<tmp>/roles/demo/templates/x.conf.j2` containing `ok={{ synth_hostname }}` (any variable the renderer provides) and a second BROKEN template `bad.j2` containing `{{ this_does_not_exist }}`.
2. Seed a golden dir with one stale-but-valid golden for `demo/templates/x.conf.j2`.
3. Case A (the bug): `run(..., update=True)` returns **1**, stderr mentions `bad.j2`, AND the valid golden WAS updated.
4. Case B: healthy tree + `update=True` → returns 0.
5. Case C: healthy tree + `update=False` (check mode) with drifted content → returns non-zero with "drift" output (protects existing semantics while you refactor).

Model the test file structure after any existing `tests/unit/test_check_*.py` (plain functions, tmp_path, no mocks beyond writing files).

**Verify**: `python3 -m pytest tests/unit/test_render_snapshots.py -q` → all pass (≥3 tests).

## Test plan

Covered by Step 3 cases A–C. Run full slice before finishing: `python3 -m pytest tests/unit -q -k "render or snapshot"` plus one manual end-to-end `python3 scripts/render-snapshots.py` from repo root.

## Done criteria

- [ ] Update mode with a broken template exits 1 and names the template on stderr (test proves it)
- [ ] Healthy-repo behaviors unchanged: check-mode drift detection still works (Case C), clean runs exit 0
- [ ] `python3 scripts/render-snapshots.py` exits 0 on the real repo
- [ ] `git status --porcelain` limited to in-scope files
- [ ] `plans/README.md` status row updated

## STOP conditions

- The live file does not match the excerpts above (drift since planning).
- Extracting `run()` would require changing how `template_render.load_role_defaults()` or the canonical context is wired — that is another finding's territory; report instead.
- Real-repo check mode starts failing after your refactor with NO code change other than the extraction — report the diff.

## Maintenance notes

- Reviewers: scrutinize that Case A asserts BOTH non-zero exit AND partial-write behavior — losing either halves the fix's value.
- Follow-up deferred deliberately: orphan-golden visibility in CHECK mode and `encoding=`/newline hardening are separate small findings; do not fold them here.
