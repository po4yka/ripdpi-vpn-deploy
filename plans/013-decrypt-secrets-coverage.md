# Plan 013: Add automated coverage for decrypt-secrets.sh

> **Executor instructions**: Follow this plan step by step; run every
> verification command. On any STOP condition, stop and report. When done,
> update your row in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 15267007..HEAD -- scripts/decrypt-secrets.sh`
> Re-read the script if it changed since `15267007`.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security / assurance
- **Planned at**: commit `15267007`, 2026-09-09

## Why this matters

`scripts/decrypt-secrets.sh` turns the SOPS-encrypted secrets file into a 0600
plaintext cache. It guards the highest-value asset in the repo. The script
enforces output-directory ownership, rejects symlinks and group-writable
locations, stages atomically, and cleans up on failure. None of this has
automated coverage: a regression that silently drops one guard would not fail
any gate. This finding came out of the 2026-08-23 plumbing audit
(OPS-1787495860232652).

## Current state

- `scripts/decrypt-secrets.sh` — 45 lines, bash, `set -euo pipefail`.
- Guards verified at `15267007`:
  - missing SOPS file → exit 1 with creation guidance;
  - output dir must be a real, owner-owned, non-symlink directory;
  - output dir must not be group- or other-writable;
  - output must be a regular non-symlink file;
  - mktemp staging beside the destination, `trap` cleanup, `chmod 0600`,
    atomic `mv -f`.
- The only external process is `sops`; a PATH stub can emulate success and
  failure. Precedent: the xray docker shim and the bats stub suites under
  `tests/bats/` (see `age_recovery_roundtrip.bats` for fixture style).
- Zero coverage today: `scripts/tests/` holds only `test_taskctl.py`.

## Implementation

1. Create `tests/bats/decrypt_secrets.bats` with a `setup()` that builds a
   temp output dir, a fixture SOPS file, and a stub `sops` on `PATH`.
2. Happy path: run against the stub; assert the output file exists, content
   matches the fixture, permissions are 0600, and no `.vpn-*.secrets.*`
   staging files remain.
3. Negative paths, each asserting exit 1 and no output file:
   - missing SOPS file;
   - group-writable output directory;
   - symlinked output directory;
   - stub `sops` fails → exit non-zero, staging file removed.
4. Cover overrides: `SECRETS_FILE`, `SOPS_FILE`, and `ENV` naming.

## Verification

- `bats tests/bats/decrypt_secrets.bats` — green.
- `make shellcheck` — green.
- CI `bats shell tests` job — green on the implementing PR.

## STOP conditions

- The script's guard semantics change upstream → re-derive the case list.
- A new `sops` flag cannot be emulated faithfully by the stub → stop and
  report instead of weakening the test.
