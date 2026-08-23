# Plan 005: Reject path-traversal values in `taskctl new --slug`

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- scripts/tasks/taskctl.py`
> Re-read the cited region if the file changed since `a0ff105`.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (a dedicated negative-path test harness is a separate plan; this fix ships with its own inline verification)
- **Category**: security / bug
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

`./taskctl new` builds the issue-file path by concatenating the user-supplied `--slug` into a fixed directory. An absolute slug or one containing `..` escapes `docs/tasks/issues/` entirely — an arbitrary local file write with template content, from a flag that agents routinely fill with model-generated values. The aftermath fails closed (the orphaned execution record breaks the next validate), but the out-of-tree write already happened. The repo's own tasking layer is advertised as fail-closed; this is a hole in that claim.

## Current state

- `scripts/tasks/taskctl.py` — stdlib-only validator/CLI, 2517 lines. Uses a `fail()` helper that prints to stderr and exits 2.
- Verified excerpt from `command_new` (~lines 2009–2016):

  ```python
      task_id = allocate_id(args.root, args.area, used, config)
      slug = args.slug or slugify(args.title)
      path = args.root / "docs/tasks/issues" / f"{slug}.md"
      if path.exists():
          fail(f"task file already exists: {path.relative_to(args.root)}")
  ```

  No validation of `args.slug`. With pathlib, joining an absolute component (`/tmp/evil`) or one containing `..` resets/escapes the base directory.
- The safe shape already exists in-repo: `slugify(args.title)` produces lowercase `[a-z0-9-]`; ID allocation and work-file creation stay untouched by this fix.
- Repo conventions for this file: fail-closed on every malformed input; errors via `fail()`; argparse subcommands under `scripts/tasks/taskctl.py`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax | `python3 -m py_compile scripts/tasks/taskctl.py` | exit 0 |
| Existing contracts still valid | `OPENSPEC_TELEMETRY=0 ./taskctl validate` | `Task contracts valid (10 tasks, 49 steps)`, exit 0 |
| Negative probe | see Step 2 | exit ≠ 0, message names the slug rule |
| Happy-path probe | see Step 3 | creates pair in temp root only |

## Scope

**In scope**:
- `scripts/tasks/taskctl.py` — `command_new` only

**Out of scope**:
- `slugify()` behavior itself
- Work-record path construction (`command_new`'s execution-file half) — it derives from the validated ID/slug and stays in place
- Any other command; the lockfile/board logic

## Git workflow

- Branch: `advisor/005-taskctl-slug-guard`
- Commit: `fix(tasking): reject slugs that escape the portfolio directory`

## Steps

### Step 1: Validate the slug before path construction

Insert immediately after the `slug = …` line:

```python
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        fail(
            f"invalid slug {slug!r}: must match [a-z0-9][a-z0-9-]* "
            "(no slashes, dots, '..' or absolute paths)"
        )
```

(`re` is already imported module-wide — confirm with `grep -n "^import re" scripts/tasks/taskctl.py`; do not add a second import.)

This validates BOTH the user-passed `--slug` and title-derived slugs (defense in depth at zero cost).

**Verify**: `python3 -m py_compile scripts/tasks/taskctl.py` → exit 0.

### Step 2: Prove the rejection without touching the real portfolio

```bash
TMPROOT="$(mktemp -d)"
OPENSPEC_TELEMETRY=0 ./taskctl new --root "$TMPROOT" --area TST --title "probe" \
  --kind chore --spec-mode not-required --slug "../evil" 2>&1; echo "exit=$?"
grep -R "evil" "$TMPROOT" ; ls "$TMPROOT/docs/tasks/issues/"
rm -rf "$TMPROOT"
```

Expected: message `invalid slug '../evil' …`, `exit=2`, NO file containing `evil`, issues dir empty or absent.

Repeat once with `--slug "/tmp/evil-abs"` → same rejection.

(If `new` requires additional mandatory flags beyond those above, consult `./taskctl new --help` first; adjust the probe flags accordingly.)

### Step 3: Prove the happy path still works inside a temp root

Same probe but `--slug "probe-slug"` → exit 0; verify `$TMPROOT/docs/tasks/issues/probe-slug.md` exists and its frontmatter `id:` matches the created execution record name; then `rm -rf "$TMPROOT"`.

### Step 4: Real-root contract intact

`OPENSPEC_TELEMETRY=0 ./taskctl validate` → exit 0 (validator's generated-asset and board checks unaffected).

## Test plan

Inline probes above ARE the verification net for now; the systematic negative-path test suite for the whole validator is tracked as a separate assurance plan and will absorb these cases (port Steps 2–3 verbatim into it then).

## Done criteria

- [ ] Slug regex guard present in `command_new`; `py_compile` clean
- [ ] Both traversal probes rejected with exit 2 and zero filesystem side effects outside the temp root
- [ ] Happy-path probe creates the expected pair inside the temp root
- [ ] `./taskctl validate` exit 0 on the real repo
- [ ] Only `scripts/tasks/taskctl.py` modified; `plans/README.md` row updated

## STOP conditions

- The excerpted lines differ from live code (drift).
- Adding the guard trips any existing consumer of `new` (search `git grep -n "taskctl new"` across docs/, .agents/, Makefile) that relies on currently-legal-but-now-rejected slug shapes — report each call site instead of loosening the regex.
- `re` is not imported module-wide and adding the import would violate the file's import conventions — report.

## Maintenance notes

- Reviewers: confirm the regex is anchored (`fullmatch`) so `foo/bar` and `..` both fail.
- When the validator test-harness plan lands, migrate the Step 2/3 probes into it as permanent regression cases.
