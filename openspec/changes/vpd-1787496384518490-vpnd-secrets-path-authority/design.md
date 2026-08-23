# Design

## Boundaries

- Rust-only change inside vpnd/. The Makefile default stays as-is for direct make users; scripts/decrypt-secrets.sh already honors an explicit SECRETS_FILE override, which becomes the integration seam.

## Decisions

- make::target gains the SECRETS_FILE kv for targets whose recipes read or produce the decrypted file (decrypt at minimum; audit-log style consumers get it where the recipe references it). This keeps ENV/PROVIDER discipline and adds one more explicit env rather than relying on ambient agreement.
- Redaction compares against ctx.secrets_file display string case-sensitively plus the historical /tmp pattern; applied in a shared helper used by both bundle entries and ai_prompt.
- Permission gate: File::open then metadata() on the held handle (rejects symlink via metadata kind check and mode bits), then read_to_string from the same handle.

## Migration / Rollback

No state migration. Single-commit revert restores previous resolution order.

## Validation

Focused cargo tests: config path resolution matrix (XDG set/unset), doctor redaction with resolved paths incl. --ai branch, chmod-failure propagation (error injected via read-only parent), fstat gate rejecting symlink/mode swap; clippy -D warnings.
