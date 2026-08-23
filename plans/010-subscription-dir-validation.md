# Plan 010: Validate SUBSCRIPTION_DIR before it enters remote root commands

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- scripts/issue-sub-token.sh scripts/issue-bootstrap.sh`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (independent of Plan 004 even though both touch these files — different hunks; land sequentially)
- **Category**: security (defense-in-depth)
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

Both issuer scripts interpolate the env-overridable `SUBSCRIPTION_DIR` into single-quoted positions of an ssh remote command executed under `sudo install` on the VPS. A value containing a single quote or shell metacharacter breaks out inside a ROOT remote shell. Today only the operator sets it, so exploitation means self-harm — but it violates the repo's own rule ("printf %q when forwarding to nested shells", `scripts/CLAUDE.md`), produces baffling remote sudo errors on benign typos (apostrophes are legal in macOS paths), and becomes a real boundary break the moment either script is wrapped by cron/CI where env comes from elsewhere.

## Current state

- `scripts/issue-sub-token.sh`: default assignment (~line 56 area) then two remote uses:

  ```bash
  SUBSCRIPTION_DIR="${SUBSCRIPTION_DIR:-/var/lib/vpn-subscription}"
  …
  remote_path="${SUBSCRIPTION_DIR}/sub/${token_hash}"

  printf '%s' "$payload" | ssh "${admin_user}@${server_ip}" \
    "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '${remote_path}'"
  ```

  (second identical site for `${remote_path}.meta`, ~lines 88–89). `token_hash` is sha256 hex — safe; only the directory component is attacker-influenced.
- `scripts/issue-bootstrap.sh`: same pattern with `/bootstrap/${token_hash}` (~lines 43, 76–77, 82–83).
- In-repo validation exemplar — `scripts/backup-tf-state.sh` (~line 23):

  ```bash
  if [[ ! "$ENV" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
    echo "ENV must contain only letters, numbers, and hyphens: $ENV" >&2
    exit 2
  fi
  ```

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax ×2 | `bash -n scripts/issue-sub-token.sh && bash -n scripts/issue-bootstrap.sh` | exit 0 |
| Lint | `make shellcheck` | exit 0 |
| Rejection probe | see Step 2 | exit 2, guard message, NO terraform/ssh output |
| Accept probe (regex only) | see Step 2b | passes guard, proceeds to next stage |

## Scope

**In scope**:
- `scripts/issue-sub-token.sh`
- `scripts/issue-bootstrap.sh`

**Out of scope**:
- The remote command construction itself (quoting style stays; validation is the fix per repo convention).
- `token_hash` handling; server-side templates.
- Plan 004's umask/QR hunks in the same files — do not merge them into this change.

## Git workflow

- Branch: `advisor/010-subscription-dir-guard`
- Commit: `fix(security): validate SUBSCRIPTION_DIR before remote sudo use`

## Steps

### Step 1: Add the guard immediately after each default assignment

Insert right below `SUBSCRIPTION_DIR="${SUBSCRIPTION_DIR:-/var/lib/vpn-subscription}"` in BOTH scripts (before any terraform/sops/ssh activity):

```bash
# Interpolated single-quoted into remote root shells below; allow only a
# conservative absolute-path charset so metacharacters can never cross.
if [[ ! "$SUBSCRIPTION_DIR" =~ ^/[A-Za-z0-9_][A-Za-z0-9_./-]*$ ]] || [[ "$SUBSCRIPTION_DIR" == *..* ]]; then
  echo "SUBSCRIPTION_DIR must be an absolute path using only [A-Za-z0-9_./-], no '..': ${SUBSCRIPTION_DIR}" >&2
  exit 2
fi
```

Notes: leading `/` enforced; no quotes/backslashes/spaces possible; explicit `..` rejection even though dots are allowed.

**Verify**: `bash -n` ×2 → exit 0; `make shellcheck` → exit 0.

### Step 2: Prove rejection happens BEFORE any network/terraform side effect

```bash
SUBSCRIPTION_DIR="/opt/o'brien" PROVIDER=upcloud ENV=prod \
  timeout 10 scripts/issue-sub-token.sh probe-client --print-token-only; echo "exit=$?"
```

Expected: ONLY the guard message on stderr, `exit=2`, within ~1 second — no `terraform-env.sh` output, no ssh attempt. Repeat with `SUBSCRIPTION_DIR="relative/path"` and `SUBSCRIPTION_DIR="/opt/../evil"` → same rejection.

Run the analogous probe against `issue-bootstrap.sh`.

### Step 3: Prove legitimate values pass the guard

Regex-only check without deploying anything (the scripts need live state beyond the guard, which is fine — we assert they get PAST the guard):

```bash
SUBSCRIPTION_DIR="/var/lib/vpn-subscription" PROVIDER=upcloud ENV=prod \
  timeout 20 scripts/issue-sub-token.sh probe-client --print-token-only 2>&1 | head -3
```

Expected output must NOT contain "SUBSCRIPTION_DIR must be". It may fail later for environmental reasons (no secrets material) — that is acceptable and proves ordering. Record what the later failure was.

### Step 4: Confirm no other unguarded interpolations of this variable

```bash
grep -rn "SUBSCRIPTION_DIR" scripts/ ansible/ | grep -v "^Binary"
```

Expected: only the two scripts (+docs). Any third consumer → STOP and report rather than silently extending scope.

## Test plan

Inline probes above. No bats layer covers these scripts' network halves by design; the guard's placement (before all side effects) is what makes the probes conclusive.

## Done criteria

- [ ] Guard present exactly once per script, positioned before first external call
- [ ] All three malicious-value probes exit 2 with zero side effects
- [ ] Legitimate value passes the guard (Step 3)
- [ ] `bash -n` ×2 + `make shellcheck` clean
- [ ] Only the two files modified (Plan 004's hunks absent); `plans/README.md` row updated

## STOP conditions

- Either script already validates the variable somewhere else (dedupe instead of double-guarding).
- Step 3 shows the guard firing on a value your regex should accept — quote the exact value; do not widen the regex blindly.
- A third SUBSCRIPTION_DIR consumer appears (Step 4) — report for scope decision.

## Maintenance notes

- If issuers gain more remote-installed artifacts, keep building their paths from the now-validated variable only.
- Reviewers: confirm the error message names the offending value (operator typo UX) but never logs any token material.
