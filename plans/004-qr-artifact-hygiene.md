# Plan 004: Lock down and gitignore credential-bearing QR artifacts

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a0ff105..HEAD -- scripts/emit-qr.sh scripts/issue-sub-token.sh scripts/issue-bootstrap.sh .gitignore`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: 001 (both edit `.gitignore`; land sequentially to avoid conflicts)
- **Category**: security
- **Planned at**: commit `a0ff105`, 2026-08-23

## Why this matters

Three operator scripts render PNG QR codes whose payloads ARE credentials: the full sing-box client JSON / VLESS URI (private-key-bearing) or long-lived bearer subscription/bootstrap URLs. Today these files are written into the current working directory with the process umask (typically 022 → mode 0644), readable by any local account and swept by backup/sync agents. Run from repo root — the documented `make issue-sub-token CLIENT=…` flow — they are untracked-but-unignored, one careless `git add .` away from a commit that gitleaks CANNOT flag (the embedded tokens are high-entropy random strings matching no rule).

## Current state

- `scripts/emit-qr.sh` (~72 lines) — renders client config/URI as PNG. Default output written without any umask/chmod (verified excerpt):

  ```bash
  if [[ -z "$OUT" ]]; then
    OUT="${CLIENT}.qr.png"
  fi
  echo "$payload" | qrencode -t PNG -o "$OUT"
  ```

  File starts with `set -euo pipefail`; no `umask` anywhere.
- `scripts/issue-sub-token.sh` — after installing the token hash server-side, renders the bearer subscription URL:

  ```bash
  qr_out="${CLIENT}.sub.qr.png"
  echo "$url" | qrencode -t PNG -o "$qr_out"
  echo "QR rendered: $qr_out"
  ```

- `scripts/issue-bootstrap.sh` — same shape for the bootstrap URL (`${CLIENT}.bootstrap.qr.png`, ~lines 103–104).
- `.gitignore` has an "Operator-side artifacts" block (`state-backups/ share/ output/ tmp/ …`) but NO `*.qr.png` rule (full file read at planning).
- Repo conventions: `set -euo pipefail` everywhere; secrets discipline per `scripts/CLAUDE.md` ("SOPS gate everywhere", runtime-materialized artifacts are same-owner 0600 files); Conventional Commits.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax | `bash -n scripts/emit-qr.sh && bash -n scripts/issue-sub-token.sh && bash -n scripts/issue-bootstrap.sh` | exit 0 |
| Lint | `make shellcheck` | exit 0 |
| Ignore contract test | `python3 -m pytest tests/unit/test_gitignore_contracts.py -q` | all pass |
| Perms assertion (static) | `grep -n "^umask 077" scripts/emit-qr.sh scripts/issue-sub-token.sh scripts/issue-bootstrap.sh` | 3 matches |

## Scope

**In scope**:
- `scripts/emit-qr.sh`
- `scripts/issue-sub-token.sh`
- `scripts/issue-bootstrap.sh`
- `.gitignore` (one line)
- `tests/unit/test_gitignore_contracts.py` (extend the file created by Plan 001)

**Out of scope**:
- Changing WHERE the QR files are written by default (CWD default stays; relocating defaults is a UX decision for the maintainer).
- The `--stdout` path of emit-qr.sh (piped output, no file perms involved).
- Server-side templates under `ansible/roles/subscription-host/**`.

## Git workflow

- Branch: `advisor/004-qr-artifact-hygiene`
- Commit: `fix(secrets): restrict and ignore credential-bearing QR artifacts`

## Steps

### Step 1: Set a restrictive umask in all three scripts

Immediately after each script's `set -euo pipefail` line add:

```bash
# QR payloads carry credentials (client keys / bearer URLs) — keep them
# owner-only on disk regardless of the caller's umask.
umask 077
```

**Verify**: `grep -n "^umask 077" scripts/emit-qr.sh scripts/issue-sub-token.sh scripts/issue-bootstrap.sh` → exactly one match per file; `bash -n` on all three → exit 0.

### Step 2: Belt-and-braces chmod after each qrencode write

After every `-o "$out_file"` invocation add `chmod 0600 "$out_file"` (covers exotic qrencode wrappers that might not honor umask). Do NOT touch the `--stdout` branch of emit-qr.sh.

**Verify**: `grep -n "qrencode -t PNG -o \"" scripts/emit-qr.sh scripts/issue-sub-token.sh scripts/issue-bootstrap.sh` and confirm each non-stdout site is followed by a `chmod 0600` of the same variable within 2 lines; `make shellcheck` → exit 0.

### Step 3: Ignore the default artifact names

Append to the "Operator-side artifacts" block of `.gitignore`:

```gitignore

# Client credential QR codes (default names carry keys/bearer URLs)
*.qr.png
```

Then extend `tests/unit/test_gitignore_contracts.py` (from Plan 001) with:

```python
def test_qr_artifacts_are_ignored() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.qr.png" in text
```

**Verify**: `python3 -m pytest tests/unit/test_gitignore_contracts.py -q` → all pass; `touch phone.qr.png && git check-ignore -v phone.qr.png && rm phone.qr.png` → matched by `.gitignore`.

### Step 4: Manual end-to-end perm proof (no secrets needed)

Render a throwaway QR from a harmless literal payload using the same write path:

```bash
cd "$(mktemp -d)" && printf 'test' | qrencode -t PNG -o probe.qr.png
```

is NOT the code path — instead verify statically per Done criteria (running the three scripts end-to-end requires live SOPS material + a deployed node; do not attempt).

## Test plan

Static contract tests as above. Runtime behavior is exercised only with real credentials by design; the umask+chmod pattern mirrors `bootstrap-secrets.sh` (`PLAINTEXT` handling) which already follows it — reviewers can diff against that exemplar.

## Done criteria

- [ ] `umask 077` present exactly once near the top of each of the three scripts
- [ ] Every file-writing `qrencode` call followed by `chmod 0600` on the target variable
- [ ] `*.qr.png` ignored by repo `.gitignore`; contract test passes
- [ ] `bash -n` clean ×3; `make shellcheck` exit 0
- [ ] Only in-scope files modified; `plans/README.md` row updated

## STOP conditions

- Any of the three scripts already sets a umask or writes its QR through a helper you cannot find — report the actual structure.
- A fourth script writing `*.qr.png` appears during your grep sweep (`grep -rn "qr.png" scripts/`) — report it; scope grows only with maintainer approval.

## Maintenance notes

- Custom `--out /path/name.png` outputs bypass the `*.qr.png` ignore rule by design; the maintainer may later want a louder warning when the custom path lives inside the repo tree.
- If QR generation ever moves into Python, preserve both guards there; the static greps in this plan's verification will need updating alongside.

## Implementation refinement (2026-08-27)

The legacy-output regression proved that umask plus post-write chmod leaves an
existing 0644 output exposed during overwrite. File output now renders into an
exclusive mode-0600 temporary file beside the destination and uses os.replace
only after successful encoding. The subshell cleanup trap preserves the issuer
registry cleanup trap and removes only its own temporary file. Standard output
is unchanged. Real script-path tests cover both fresh and legacy 0644 outputs.
