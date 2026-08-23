# Plan 007: Bound every external curl with connect/total timeouts

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- scripts/burn-check.sh scripts/warm-spare-watcher.sh scripts/asn-drift.sh scripts/check-ip-reputation.sh scripts/tspu-canary.sh scripts/scan-reality-targets.sh scripts/install-vpnd.sh scripts/ci-bootstrap-secrets.sh`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug (cron reliability)
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

curl defaults to no overall timeout. Several cron-driven scripts call external endpoints (check-host.net, ntfy.sh, GitHub) with `-fsS` only; one stalled TCP connection hangs the run forever. Worst case is `warm-spare-watcher.sh` on a */2 schedule: hung processes stack every 2 minutes and the OTP/alert never goes out. `burn-check.sh` leaves its Prometheus textfile stale while leaking processes. The repo already knows the right pattern — `burn-check.sh` uses `--max-time 8` at one site — this plan applies it everywhere it's missing.

## Current state

Sites missing time bounds (verified during audit; re-confirm each with the grep in Step 0):

| File | Lines | Endpoint | Notes |
|---|---|---|---|
| `scripts/burn-check.sh` | ~136–137 | check-host.net `/check-tcp` | header says "Intended to run from cron" |
| `scripts/burn-check.sh` | ~152–153 | check-host.net `/check-result/…` poll loop | |
| `scripts/warm-spare-watcher.sh` | ~50 (`notify_operator`) | ntfy push | called from */2 cron |
| `scripts/warm-spare-watcher.sh` | ~225–231 | ntfy OTP push | |
| `scripts/asn-drift.sh` | ~70–76 | ntfy daily alert | |
| `scripts/check-ip-reputation.sh` | ~125–131 | ntfy daily alert | |
| `scripts/tspu-canary.sh` | ~158–164 | ntfy daily alert | |
| `scripts/scan-reality-targets.sh` | ~96 | binary download | already has `--retry 3`, no bound |
| `scripts/install-vpnd.sh` | ~89,92 | GitHub download | interactive, lower stakes but same fix |
| `scripts/ci-bootstrap-secrets.sh` | ~77–78 | network fetch | |

Good in-repo exemplar to match — `scripts/burn-check.sh` (~line 83): `curl -fsS --max-time 8 …`.
The ntfy sites build an optional auth array; keep that shape untouched:

```bash
    curl -fsS -X POST -H "Title: ${title}" … ${auth[@]+"${auth[@]}"} --data "$body" "${ntfy_url%/}/${NTFY_TOPIC}" >/dev/null || echo "warm-spare: ntfy push failed (will retry next run)" >&2
```

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Enumerate unbounded curls | Step 0 grep | list shrinks to zero after fix |
| Lint | `make shellcheck` | exit 0 |
| Syntax | `bash -n <each touched file>` | exit 0 |
| Bats suites touching these scripts | `bats tests/bats/input_validation.bats` | pass |

## Scope

**In scope**: the eight files above, curl invocations only.

**Out of scope**:
- Any retry/backoff logic changes (`--retry 3` on scan-reality-targets stays).
- The existing bounded site (`burn-check.sh` `--max-time 8`) — leave as-is.
- Notification payload/formatting logic.
- Python-side network calls (urllib timeouts are a separate finding).

## Git workflow

- Branch: `advisor/007-curl-timeouts`
- Commit: `fix(scripts): bound external curls with connect/max-time on cron paths`

## Steps

### Step 0: Reproduce the enumeration

```bash
grep -n "curl " scripts/{burn-check,warm-spare-watcher,asn-drift,check-ip-reputation,tspu-canary,scan-reality-targets,install-vpnd,ci-bootstrap-secrets}.sh \
  | grep -v -- "--max-time"
```

Expected: the table's sites. If you find additional unbounded EXTERNAL curls beyond this list, add them to the same fix (same flags) and note them in the commit body.

### Step 1: Apply flags per class

- check-host.net requests + polls (`burn-check.sh` both sites): add `--connect-timeout 5 --max-time 20`
- All ntfy pushes (`warm-spare-watcher.sh` ×2, `asn-drift.sh`, `check-ip-reputation.sh`, `tspu-canary.sh`): add `--connect-timeout 5 --max-time 15`
- Binary download (`scan-reality-targets.sh`): add `--connect-timeout 5 --max-time 30` alongside existing `--retry 3`
- `install-vpnd.sh`, `ci-bootstrap-secrets.sh`: add `--connect-timeout 5 --max-time 30`

Insert flags immediately after `-fsS` (or after `--retry 3` where present) so diffs read uniformly.

**Verify**: rerun the Step 0 grep → zero hits across these files.

### Step 2: Prove failure-path semantics survive

For one ntfy site, simulate an unreachable endpoint without sending anything:

```bash
NTFY_URL="https://10.255.255.1" NTFY_TOPIC=probe NTFY_TOKEN="" \
  timeout 25 bash -c 'source scripts/warm-spare-watcher.sh --help >/dev/null 2>&1 || true'
```

is NOT reliable (script needs args); instead verify statically that each modified curl retains its existing `|| echo … failed` continuation (grep shows the fallback line still present after every ntfy curl) so a timeout degrades to the existing retry-next-run path rather than aborting via `set -e`.

**Verify**: for warm-spare-watcher/asn-drift/check-ip-reputation/tspu-canary: `grep -n -A1 "ntfy" <file> | grep -c "push failed"` ≥ 1 per file (or equivalent existing message); `bash -n` all files exit 0.

## Test plan

No dedicated bats coverage exists for these curl sites (verified). Static verification above plus `make shellcheck`. Optional manual proof on any machine: point `NTFY_URL` at a blackholed IP and observe the push returns within ~15 s with the failure note instead of hanging.

## Done criteria

- [ ] Step 0 grep returns zero unbounded external curls in the eight files
- [ ] `make shellcheck` exit 0; `bash -n` clean on all touched files
- [ ] Existing error-continuation lines intact after every ntfy curl
- [ ] Only curl flag insertions changed (`git diff` shows no other edits)
- [ ] `plans/README.md` row updated

## STOP conditions

- A listed site has drifted (line numbers moved AND the curl semantics differ from the excerpt).
- Any site turns out to stream a long-lived response intentionally (none known) — report before bounding it.
- Adding flags trips shellcheck on a quoted-variable nuance twice in a row — report the exact warning.

## Maintenance notes

- If a shared notification helper is extracted later (direction item), fold these defaults into it and delete the per-site flags.
- Reviewers: confirm nobody "fixed" the hang by adding `-m 0` (infinite) anywhere.
