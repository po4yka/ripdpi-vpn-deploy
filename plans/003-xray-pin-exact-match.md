# Plan 003: Match the pinned Xray version exactly in probe-matrix-driver

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- scripts/probe-matrix-driver.py scripts/emit-probe-matrix-profile.py tests/unit | head -20`
> Re-read the cited regions if the driver changed since `a0ff105`.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug (gate correctness)
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

The probe matrix validates that the installed Xray binary matches the version pinned in the secrets document (`xray.version`, e.g. `v26.3.27`) before trusting a cell's evidence. The current check is substring containment: pin `v26.3.2` "matches" an installed `v26.3.27` because the shorter string appears inside the longer banner. Xray uses date-based versions where prefixes are realistic, so a stale pin silently passes, probe reports imply pin compliance, and the `version-mismatch` verdict that should stop the cell never fires.

## Current state

- `scripts/probe-matrix-driver.py` — drives per-cell Xray probes and emits verdict JSON.
- The buggy check (verified excerpt, line ~240):

  ```python
      try:
          version = subprocess.run([binary, "version"], text=True, capture_output=True, timeout=5, check=False)
      except (OSError, subprocess.TimeoutExpired):
          return verdict("error", error_kind="dependency-missing")
      if version.returncode != 0 or expected_version not in version.stdout + version.stderr:
          return verdict("error", error_kind="version-mismatch")
  ```

- Pin source: `scripts/emit-probe-matrix-profile.py` writes `"expected_xray_version": xray.get("version")` into the profile document (~line 46).
- In-repo exemplar for exact comparison style: the mtproto helper check later in the same driver (~line 322) compares its helper version with exact equality — match that spirit.
- Parsing exemplar: `scripts/check-xray-breaking-changes.py:160-165`:

  ```python
  def parse_version(value: str) -> tuple[int, int, int]:
      """Parse an exact Xray release tag into a numerically comparable tuple."""
      match = VERSION.fullmatch(value)
      if match is None:
          raise ValueError(f"invalid Xray version {value!r}; expected vX.Y.Z")
      return tuple(int(part) for part in match.groups())
  ```

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax | `python3 -m py_compile scripts/probe-matrix-driver.py` | exit 0 |
| Existing driver tests | `python3 -m pytest tests/unit -q -k probe_matrix` | all pass |
| Full unit slice | `python3 -m pytest tests/unit -q` | all pass |

## Scope

**In scope**:
- `scripts/probe-matrix-driver.py`
- The existing probe-matrix unit test file(s) under `tests/unit/` (locate via `glob tests/unit/*probe*matrix*`; extend, don't duplicate)

**Out of scope**:
- `scripts/emit-probe-matrix-profile.py` (pin emission stays as-is)
- `scripts/check-xray-breaking-changes.py` (only referenced as a pattern)
- Any verdict enum/error_kind vocabulary — `version-mismatch` keeps its name.

## Git workflow

- Branch: `advisor/003-xray-pin-exact`
- Commit: `fix(probe-matrix): compare pinned xray version exactly, not by substring`

## Steps

### Step 1: Extract the version token from the banner instead of substring-scanning

Replace the containment condition at ~line 240 with token extraction + exact comparison:

```python
banner = version.stdout + version.stderr
match = re.search(r"Xray\s+(\S+)", banner)
installed = match.group(1) if match else ""
if version.returncode != 0 or installed != expected_version.lstrip("v"):
```

Rationale: the real binary prints e.g. `Xray 26.3.27 ...` (version without leading `v`); the pin stores `v26.3.27`. Normalizing exactly one side (`lstrip("v")`) keeps the comparison anchored to a whole token. First run the real command once on a machine that has xray (`xray version`) to confirm the banner shape; record what you saw in the test fixture string.

**Verify**: `python3 -m py_compile scripts/probe-matrix-driver.py` → exit 0.

### Step 2: Pin the behavior with tests

Extend the existing driver test module (or create `tests/unit/test_probe_matrix_driver_versions.py` following the same stubbing pattern the file already uses for `subprocess.run`):

1. Banner `Xray 26.3.27 (…)`, pin `v26.3.27` → passes (no version-mismatch).
2. Banner `Xray 26.3.27 …`, pin `v26.3.2` → **must** yield `error/version-mismatch` (the regression this plan fixes).
3. Banner without any `Xray` token → `version-mismatch`.
4. Non-zero returncode → `version-mismatch` unchanged.

**Verify**: `python3 -m pytest tests/unit -q -k probe_matrix` → all pass, including ≥4 new/updated cases.

## Test plan

As Step 2. Then full `python3 -m pytest tests/unit -q`. No bats/snapshot layer covers this path (verified during audit), so the unit cases above are the entire net — make them precise.

## Done criteria

- [ ] No substring containment against the version banner remains in the driver (`grep -n "expected_version not in" scripts/probe-matrix-driver.py` → no matches)
- [ ] Prefix-pin case returns `version-mismatch` (test proves it)
- [ ] `python3 -m pytest tests/unit -q` → all pass
- [ ] Only in-scope files modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- The live code at ~line 240 differs from the excerpt (drift).
- The banner regex does not match a real `xray version` output you can observe — capture the actual banner text and STOP (do not guess the format into tests).
- Existing driver tests stub `subprocess.run` in a way incompatible with adding a banner fixture — report the pattern you found instead of rewriting their harness.

## Maintenance notes

- If Xray ever changes its banner prefix (not just the number), the extraction regex needs updating — the new test with the recorded real banner will fail loudly first.
- Reviewers: confirm the normalization direction (strip `v` from the PIN side only) is applied once, not symmetrically on both sides.
