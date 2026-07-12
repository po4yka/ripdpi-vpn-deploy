# Plan 004: Validate fleet rotation plans before deriving paths or control values

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md` unless a reviewer dispatched you and told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- scripts/fleet-rotate.sh tests/bats/fleet_rotate_dryrun.bats tests/bats/input_validation.bats`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

`scripts/fleet-rotate.sh` trusts YAML fields before using them in a state filename, shell arithmetic, provider/environment routing, and the rotation loop. A malformed or tampered plan can currently escape `.omc/state` through `id`, feed non-integers into arithmetic, or defer invalid providers and environment labels until after state has been created. The script must reject the complete plan before deriving a state path, creating `.omc/state`, calling Terraform, or invoking `blue-green.sh`.

## Current state

- `scripts/fleet-rotate.sh` is the fleet plan parser and destructive orchestrator. Its YAML loader currently only converts input to JSON, after `STATE_DIR` has already been created:

```bash
# scripts/fleet-rotate.sh:52-82
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="${REPO_ROOT}/.omc/state"
mkdir -p "$STATE_DIR"

plan_json="$(python3 - "$PLAN" <<'PY'
import json
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.dumps(yaml.safe_load(handle) or {}))
PY
)"
plan_id="$(jq -r '.id // "unnamed"' <<< "$plan_json")"
min_active="$(jq -r '.min_active // 1' <<< "$plan_json")"
total="$(jq -r '.rotations | length' <<< "$plan_json")"
STATE="${STATE_DIR}/fleet-rotate-${plan_id}.json"
```

- `scripts/fleet-rotate.sh:130-145` later passes plan values into `seq`, string slicing, and arithmetic without checking their types.
- `scripts/terraform-env.sh:17-27` is the canonical downstream provider/environment contract. Match its provider enumeration (`upcloud`, `hetzner`, `vultr`) and environment pattern (`^[A-Za-z0-9][A-Za-z0-9-]*$`).
- `tests/bats/fleet_rotate_dryrun.bats` is the focused hermetic suite for this script. It loads `bats-support` and `bats-assert`, routes external commands through `tests/stubs/bin`, and uses `tests/fixtures/fleet-plan-sample.yaml` as the valid-plan fixture.
- `tests/bats/input_validation.bats:9-16` verifies that a metacharacter-bearing plan path is passed as one argv value, but its plan currently contains an empty rotation list. Update that inline fixture to remain valid under the new non-empty plan contract while preserving the metacharacter-bearing pathname.
- Shell scripts use `set -euo pipefail`; operator validation fails before side effects; Python is appropriate for non-trivial YAML data shaping. Match the input-validation approach in `scripts/bootstrap-secrets.sh:80-130`: validate types and full-string patterns, emit a concise error to stderr, and exit nonzero.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | `git diff --stat 7bdba37..HEAD -- scripts/fleet-rotate.sh tests/bats/fleet_rotate_dryrun.bats tests/bats/input_validation.bats` | no output |
| Bash syntax | `bash -n scripts/fleet-rotate.sh` | exit 0 |
| Shell lint | `shellcheck -s bash -S warning scripts/fleet-rotate.sh` | exit 0, no warnings |
| Focused Bats | `bats tests/bats/fleet_rotate_dryrun.bats tests/bats/input_validation.bats` | all tests pass |
| Full shell regression | `bats tests/bats/` | all tests pass |
| Audit-hook regression | `mise exec -- python3 -m pytest tests/unit/test_audit_log_hooks.py -q` | all tests pass |
| Diff hygiene | `git diff --check` | exit 0, no output |

## Scope

**In scope** (the only source/test files you should modify):

- `scripts/fleet-rotate.sh`
- `tests/bats/fleet_rotate_dryrun.bats`
- `tests/bats/input_validation.bats`

**Out of scope** (do not modify):

- `scripts/blue-green.sh`, `scripts/terraform-env.sh`, or any other operator script. This plan validates their existing input contract at the fleet boundary; it does not refactor downstream scripts.
- `tests/fixtures/fleet-plan-sample.yaml`. It already satisfies the intended strict contract and remains the valid fixture.
- `Makefile`, documentation, provider Terraform, Ansible, secrets, and generated artifacts.
- The state/resume format and approval sequence. Existing valid plans and state files must retain their behavior.

## Git workflow

- Branch: `codex/advisor-004-fleet-plan-validation`
- Create one focused commit using Conventional Commits, for example `fix(scripts): validate fleet rotation plans`.
- Do not push, merge, or open a pull request.

## Steps

### Step 1: Validate and normalize the complete YAML document before side effects

Extend the existing Python YAML-to-JSON block in `scripts/fleet-rotate.sh`; do not add a new runtime dependency or a new source file. The Python block must either print one normalized JSON object to stdout or exit nonzero with a concise `invalid fleet plan: ...` diagnostic on stderr. Catch YAML/parser and file-decoding errors so the operator does not receive an unhandled traceback.

Require a top-level mapping with exactly the required keys `id`, `min_active`, and `rotations`; reject unknown top-level keys. Apply all of these rules, explicitly rejecting Python `bool` wherever an integer is expected:

- `id`: string, 1-64 characters, matching `^[A-Za-z0-9][A-Za-z0-9-]*$`.
- `rotations`: non-empty list.
- `min_active`: integer from 1 through `len(rotations)` inclusive.
- Each rotation: mapping with required `current` and `new_env`, optional `new_zone`, and no unknown keys.
- `current`: string containing exactly one `:`; provider is one of `upcloud`, `hetzner`, `vultr`; current environment matches `^[A-Za-z0-9][A-Za-z0-9-]*$`.
- `new_env`: string matching the same environment pattern and different from the current environment.
- `new_zone`: when present, a non-empty string matching `^[A-Za-z0-9][A-Za-z0-9-]*$`; preserve absence as absence or normalize it consistently with the existing `jq '.new_zone // ""'` consumer.
- Reject duplicate `current` entries so one live environment cannot be rotated twice in a single plan.

Move `mkdir -p "$STATE_DIR"` until after validation and after the dry-run early exit, so invalid plans and dry runs do not create state directories. Continue passing the plan path as `sys.argv[1]`; never interpolate YAML values into Python or shell source.

**Verify**: `bash -n scripts/fleet-rotate.sh && shellcheck -s bash -S warning scripts/fleet-rotate.sh` → exit 0 with no output.

### Step 2: Constrain the state path before reading or writing it

After validation and the dry-run early exit, derive `STATE` from the validated `plan_id`, create `STATE_DIR`, and verify the resolved state parent is exactly the resolved `STATE_DIR`. Refuse a pre-existing symlink at the state-file path before either resume reads it or a normal run truncates it. Keep the state filename shape `fleet-rotate-<id>.json` and preserve all existing resume behavior for regular files.

The path check is defense in depth even though the validated ID excludes separators. It must fail before `jq > "$STATE"`, Terraform, `blue-green.sh`, or audit logging.

**Verify**: `bash -n scripts/fleet-rotate.sh && shellcheck -s bash -S warning scripts/fleet-rotate.sh` → exit 0 with no output.

### Step 3: Add meaningful invalid-plan regressions

Extend `tests/bats/fleet_rotate_dryrun.bats` with a helper that writes a supplied YAML document to `BATS_TEST_TMPDIR`, runs the script with `--dry-run`, and asserts failure. Cover at least these classes:

1. Traversal/unsafe ID such as `../../escape`.
2. `min_active` as a string, as a boolean, zero, and greater than the number of rotations.
3. Missing, empty, or non-list `rotations`.
4. A rotation that is not a mapping; missing required keys; and an unknown key.
5. Unsupported provider, malformed `current`, unsafe current/new environment, unsafe zone, and identical current/new environments.
6. Duplicate `current` entries.

For every invalid case, assert nonzero status and an `invalid fleet plan:` diagnostic. For the traversal case, also assert no escaped state file was created. Preserve the existing valid fixture tests and their no-external-action assertions.

Update only the inline YAML in `tests/bats/input_validation.bats` so its plan-path argv test contains one valid rotation and continues to prove the semicolon in the filename is inert.

**Verify**: `bats tests/bats/fleet_rotate_dryrun.bats tests/bats/input_validation.bats` → all tests pass, including the original valid dry-run and argv-path cases plus the new invalid-plan cases.

### Step 4: Run the complete regression gates and commit

Run every done criterion below. Review `git status --short` and confirm only the three in-scope files changed. Commit the validated slice with the prescribed Conventional Commit message.

**Verify**: `git diff --check && git diff --name-only | sort` → no diff errors, and the file list is exactly `scripts/fleet-rotate.sh`, `tests/bats/fleet_rotate_dryrun.bats`, and `tests/bats/input_validation.bats` before committing.

## Test plan

- Keep the existing valid fixture as the happy path and preserve its two rendered entries.
- Add table-driven or helper-driven Bats cases that prove every typed field and identifier boundary rejects malformed input before external actions.
- Assert the failure message prefix, not Python implementation details or an entire exact diagnostic.
- Keep the plan-path metacharacter regression meaningful by using a syntactically and semantically valid plan at that filename.
- Run the complete Bats directory because `fleet-rotate.sh` participates in shared shell stubs and governance counts.

## Done criteria

- [ ] Invalid YAML and every malformed field class listed in Step 3 exit nonzero with `invalid fleet plan:` and no traceback.
- [ ] Unsafe `id` cannot escape `.omc/state`; invalid plans and dry runs do not create the state directory; pre-existing state-file symlinks are refused.
- [ ] Valid dry-run output and valid resume/state semantics remain unchanged.
- [ ] `bash -n scripts/fleet-rotate.sh` exits 0.
- [ ] `shellcheck -s bash -S warning scripts/fleet-rotate.sh` exits 0 with no warnings.
- [ ] `bats tests/bats/fleet_rotate_dryrun.bats tests/bats/input_validation.bats` passes.
- [ ] `bats tests/bats/` passes.
- [ ] `mise exec -- python3 -m pytest tests/unit/test_audit_log_hooks.py -q` passes.
- [ ] `git diff --check` exits 0.
- [ ] No files outside the three-file scope are modified, the worktree is clean after commit, and the executor reports the commit SHA.

## STOP conditions

Stop and report instead of improvising if:

- Any in-scope file differs from the current-state excerpts because of committed drift after `7bdba37`.
- Existing checked-in fleet fixtures or documented examples require providers, environment labels, zone labels, or additional keys that violate the proposed contract.
- Preserving valid resume behavior requires changing the state document format or an out-of-scope script.
- The validation cannot run with the repository's existing Python/PyYAML dependencies.
- A verification gate fails twice after a reasonable in-scope correction.
- The implementation requires modifying any file outside the three-file scope.

## Maintenance notes

Future additions to the fleet-plan format must update the validator and negative tests together. Reviewers should scrutinize validation order: no state directory/file, provider command, blue-green invocation, or audit entry may occur before the whole document is accepted. The path-containment and symlink checks are intentional defense in depth and should not be removed merely because the ID regex already excludes slashes.
