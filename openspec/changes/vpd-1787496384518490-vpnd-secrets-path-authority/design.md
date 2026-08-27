# Design

## Boundaries

- `vpnd/` resolves the plaintext path and passes it to Make/Ansible. `scripts/decrypt-secrets.sh` creates the actual output parent and stages plaintext beside its destination before atomic publication. Direct Make users keep the same runtime-directory default.

## Decisions

- make::target gains the SECRETS_FILE kv for targets whose recipes read or produce the decrypted file (decrypt at minimum; audit-log style consumers get it where the recipe references it). This keeps ENV/PROVIDER discipline and adds one more explicit env rather than relying on ambient agreement.
- Redaction compares against ctx.secrets_file display string case-sensitively plus the historical /tmp pattern; applied in a shared helper used by both bundle entries and ai_prompt.
- Permission gate: use the safe `rustix` filesystem API to open with `NOFOLLOW | NONBLOCK | CLOEXEC`, then evaluate regular-file type, current UID, and private mode bits on the held descriptor before reading. `File::open` followed by metadata alone cannot reject a symlink swap. A private read-only file remains a valid read input.
- Hardening opens the same way and applies mode 0600 through the held descriptor. Missing, symlink, special, foreign-owner, or failed-chmod inputs abort; explain mode performs no filesystem mutation.
- The user approved direct `rustix` 1.x with its `fs` feature. The locked version was already transitive; adding the direct edge does not add a new package version or project unsafe code.

## Migration / Rollback

No state migration. Single-commit revert restores previous resolution order.

## Validation

Focused cargo tests: config path resolution matrix (XDG set/unset), doctor redaction with resolved paths incl. --ai branch, chmod-failure propagation (error injected via read-only parent), fstat gate rejecting symlink/mode swap; clippy -D warnings.
