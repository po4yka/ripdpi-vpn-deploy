# Plan 012: Skip age-recovery roundtrip suite when ssss-combine is absent

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- tests/bats/age_recovery_roundtrip.bats scripts/age-recovery-combine.sh`

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests (first-contact DX)
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

`tests/bats/age_recovery_roundtrip.bats` shells out to `scripts/age-recovery-combine.sh`, which exits 1 when the `ssss-combine` binary is missing. The suite has no tool guard, so on a fresh macOS workstation — where the repo advertises `make ci-fast` as the portable pre-PR gate and CI's `apt-get install ssss` does not apply — all three tests fail with misleading reconstruction errors instead of a clean skip. Inconsistent with the repo's own convention elsewhere (`tests/zizmor_gate_runtime.py` skips cleanly when zizmor is absent).

## Current state

- `tests/bats/age_recovery_roundtrip.bats` (verified head):

  ```bash
  load 'test_helper/bats-support/load'
  load 'test_helper/bats-assert/load'

  REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
  SCRIPT="${REPO_ROOT}/scripts/age-recovery-combine.sh"
  SHARES_DIR="${REPO_ROOT}/tests/fixtures/age-recovery-shares"
  AGE_KEY_FILE="${REPO_ROOT}/tests/fixtures/age-test.key"
  EXPECTED_KEY="AGE-SECRET-KEY-…"   # test fixture identity; do not quote further

  setup() {
    : # nothing to set up per-test
  }
  ```

  Three `@test` blocks call `_combine` → `run bash "${SCRIPT}" …`.
- `scripts/age-recovery-combine.sh` (~lines 20–22): exits 1 with `missing: ssss-combine` when the binary is absent.
- CI installs it (`.github/workflows/ci.yml`: `apt-get install -y bats ssss`) — CI behavior must remain "run", not skip.
- Skip idiom available in these suites: bats-core's `skip` (already used in this repo's Python layer via `tests/zizmor_gate_runtime.py`; bats `skip` works inside `setup()`).

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Suite as-is (tools present) | `bats tests/bats/age_recovery_roundtrip.bats` | all pass |
| Simulated absence | `PATH="/usr/bin:/bin" bats tests/bats/age_recovery_roundtrip.bats` | all skipped, exit 0 |
| Local gate slice | `bats tests/bats/` | pass |

## Scope

**In scope**:
- `tests/bats/age_recovery_roundtrip.bats` (setup function only)

**Out of scope**:
- `scripts/age-recovery-combine.sh` (its fail-loud exit is correct for direct operator use).
- Any other bats file.
- Fixture contents under `tests/fixtures/age-recovery-shares/`.

## Git workflow

- Branch: `advisor/012-ssss-skip-guard`
- Commit: `test(bats): skip age-recovery roundtrip when ssss-combine is missing`

## Steps

### Step 1: Add the tool guard to setup()

Replace the placeholder setup:

```bash
setup() {
  command -v ssss-combine >/dev/null 2>&1 \
    || skip "ssss-combine not installed; install it (e.g. 'brew install ssss' / 'apt-get install ssss') to run the recovery roundtrip"
}
```

Keep the message actionable (install hint), matching how other tool-absent messages read in this repo.

**Verify**: `bash -n tests/bats/age_recovery_roundtrip.bats` → exit 0.

### Step 2: Prove both modes

```bash
# Tools present → real run (macOS with brew ssss or Linux):
bats tests/bats/age_recovery_roundtrip.bats

# Simulated absence (hide brew paths so ssss-combine is not found):
PATH="/usr/bin:/bin:/usr/sbin:/sbin" bats tests/bats/age_recovery_roundtrip.bats
```

Expected: first invocation passes all tests; second reports every test as skipped and exits 0.

Note where `ssss-combine` actually lives first (`command -v ssss-combine`) and adjust the reduced PATH so it is genuinely excluded on your machine.

### Step 3: Full local slice unaffected

```bash
bats tests/bats/
```

Expected: no regressions in the other suites.

## Test plan

The two-mode proof in Step 2 IS the test plan (the change is itself test infrastructure). No new assertions needed beyond the guard.

## Done criteria

- [ ] Guard present in `setup()`; no other lines of the suite changed
- [ ] Absence simulation → all skipped, exit 0
- [ ] Presence → all pass, exit 0
- [ ] `bats tests/bats/` fully green on your machine
- [ ] Only the one file modified; `plans/README.md` row updated

## STOP conditions

- `skip` is not recognized by the installed bats version (`bats --version` < 1.0) — report the version instead of shimming a custom skip.
- Tests FAIL (not skip) under the reduced PATH — the guard isn't being reached; check you edited `setup()` and not a helper.
- Your machine lacks `ssss` entirely AND you cannot verify the presence mode — report; presence-mode proof can be deferred to CI evidence.

## Maintenance notes

- If more suites shell out to optional binaries (audit found none today), copy this exact guard shape rather than inventing per-suite variants.
- Reviewers: confirm CI still RUNS (not skips) the suite — i.e., the guard triggers only on genuine absence, since ci.yml installs ssss before invoking bats.
