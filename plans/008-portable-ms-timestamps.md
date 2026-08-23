# Plan 008: Replace GNU-only millisecond timestamps in idle-cycle-measure.sh

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- scripts/idle-cycle-measure.sh scripts/test-tls-policing.sh`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug (portability)
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

`date +%s%3N` is a GNU coreutils extension. On BSD/macOS date — the documented "filtered-residential vantage" workstation — `%N` expands to a literal `N`, producing timestamps like `17562…N`. Those strings are fed to `jq --argjson`, which fails JSON parsing; under the script's `set -euo pipefail` the first measurement cycle dies at the cold probe AFTER its 5-minute sleep: no report, wasted idle window, exit 1, all collected schedule data lost.

## Current state

- `scripts/idle-cycle-measure.sh` — measures TLS probe latency across an idle cycle and emits one JSON report via jq.
- The two GNU-only sites (verified excerpt):

  ```bash
    local pre_ms post_ms elapsed verdict err
    pre_ms="$(date +%s%3N)"
    …
    post_ms="$(date +%s%3N)"
    elapsed=$(( post_ms - pre_ms ))
  ```

  followed by `jq -nc --argjson pre_ms "$pre_ms" …` (~lines 129–132).
- In-repo portable pattern to copy: `scripts/test-tls-policing.sh` (~line 77) derives milliseconds with python3 stdlib (`int(time.time()*1000)`). Repo rule from `scripts/CLAUDE.md`: operator Python must run under venv-less system python3, stdlib only.
- Demonstration of the bug class on macOS: `/bin/date +%s%3N` prints e.g. `1755…N` (literal N), GNU date prints 13 digits.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Portable ms helper sanity | `python3 -c 'import time; print(int(time.time()*1000))'` | 13-digit integer |
| Show non-portability | `/bin/date +%s%3N` | ends in literal `N` on macOS/BSD |
| Syntax | `bash -n scripts/idle-cycle-measure.sh` | exit 0 |
| Lint | `make shellcheck` | exit 0 |
| No stragglers | `grep -n "%3N" scripts/` | only acceptable leftovers documented below |

## Scope

**In scope**:
- `scripts/idle-cycle-measure.sh`

**Out of scope**:
- Any other script using `%3N` UNLESS your Step 0 sweep finds one on a cron path — then report, don't expand scope silently.
- The jq report schema / measurement logic / sleep schedule.

## Git workflow

- Branch: `advisor/008-portable-ms-timestamps`
- Commit: `fix(scripts): use portable millisecond clock in idle-cycle-measure.sh`

## Steps

### Step 1: Add a portable now_ms helper

Near the top of `scripts/idle-cycle-measure.sh` (after `set -euo pipefail` and required-tool checks), mirroring the test-tls-policing.sh pattern:

```bash
# Millisecond clock portable across GNU/BSD date (macOS %N is a literal 'N').
now_ms() { python3 -c 'import time; print(int(time.time()*1000))'; }
```

Confirm `python3` is already among the script's checked tools (it uses jq; add `python3` to the existing tool loop if absent).

### Step 2: Swap both call sites

Replace both assignments:

```bash
  pre_ms="$(now_ms)"
  …
  post_ms="$(now_ms)"
```

Leave `elapsed=$(( post_ms - pre_ms ))` and all jq plumbing unchanged — values remain integer epoch-ms strings.

**Verify**:
- `bash -n scripts/idle-cycle-measure.sh` → exit 0
- `make shellcheck` → exit 0
- `grep -n "%3N" scripts/idle-cycle-measure.sh` → no matches
- Helper smoke: `bash -c 'source <(sed -n "/^now_ms()/,/}/p" scripts/idle-cycle-measure.sh); now_ms'` → 13-digit number (adjust sed range if helper formatting differs)

### Step 3: Prove the arithmetic path end-to-end without waiting for the cycle

The full cycle sleeps minutes by design — do NOT run it. Instead replicate the exact consumption shape:

```bash
pre="$(python3 -c 'import time; print(int(time.time()*1000))')"; sleep 0.2; \
post="$(python3 -c 'import time; print(int(time.time()*1000))')"; \
jq -nc --argjson pre "$pre" --argjson post "$post" '{pre:$pre,post:$post,elapsed:($post-$pre)}'
```

Expected: valid JSON with a small positive `elapsed`. This proves argjson accepts the produced integers — the precise failure point being fixed.

## Test plan

No bats/unit layer covers this script today (audit-verified). Static checks + Step 3 arithmetic proof constitute the net. If a maintainer later adds a probe-script harness, port Step 3 into it as a regression case.

## Done criteria

- [ ] No `%3N` remains in `scripts/idle-cycle-measure.sh`
- [ ] Both timestamp sites use `now_ms`; helper defined once
- [ ] `bash -n` + `make shellcheck` clean
- [ ] Step 3 command emits valid JSON with positive elapsed
- [ ] Only the one file modified; `plans/README.md` row updated

## STOP conditions

- The file drifted so the excerpted lines no longer exist.
- The script's tool-check loop rejects adding python3 (would contradict repo conventions elsewhere) — report instead of forcing it.
- Your sweep finds `%3N` in OTHER cron-path scripts — list them in your report; they get their own change.

## Maintenance notes

- If the repo ever grows a shared `lib/` for such helpers (direction item), move `now_ms()` there and update both consumers.
- Reviewers: confirm no site still passes the value through `date` before jq.
