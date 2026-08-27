# Change: Make vpnd the single authority for the decrypted secrets path and redaction

Task ID: `VPD-1787496384518490`

## Why

The deep audit found that when XDG_RUNTIME_DIR is unset (macOS default), vpnd computes the decrypted-secrets path from cache_dir while `make decrypt` writes to TMPDIR, so share/preflight re-decrypt and fail and reconverge hands a wrong VPN_SECRETS_FILE to ansible-playbook. The doctor redaction control only matches the legacy /tmp path shape, so it silently protects nothing on current systems, and the --ai prompt path skips redaction entirely while the tarball path applies it. Additionally secure_secrets_file swallows chmod failures and the secrets permission gate is check-then-read.

## What Changes

- Every vpnd-invoked make target that consumes or produces the decrypted file receives SECRETS_FILE=<vpnd-resolved path> explicitly; vpnd's resolution becomes the single source of truth on all platforms.
- Doctor redaction masks any line containing the resolved secrets_file path (plus the legacy patterns), and the --ai prompt applies the same redaction as the bundle before printing/copying.
- secure_secrets_file returns a Result; callers propagate instead of proceeding on failure.
- Secrets::load and share-token loading atomically reject symlinks and nonblocking special-file opens, then check type/owner/private mode and read through the same held descriptor. Hardening also chmods the held descriptor and rejects missing files.

## Capabilities

### New Capabilities

- `vpnd/secrets-path`: How the decrypted runtime secrets path is resolved, communicated to make/ansible, and kept out of exported diagnostics.

### Modified Capabilities

- None

## Impact

- vpnd runner/make builder signatures, config.rs, doctor.rs, secrets.rs, share/preflight/reconverge call sites; vpnd/CLAUDE.md pitfall text updated to the new contract.
- Behavior change: on macOS without XDG_RUNTIME_DIR, share/preflight/reconverge start working against the same file make decrypt writes.
