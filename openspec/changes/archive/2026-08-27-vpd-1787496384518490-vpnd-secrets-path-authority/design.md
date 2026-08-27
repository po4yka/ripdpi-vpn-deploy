# Design

## Boundaries

- `vpnd/` resolves the plaintext path and passes it to Make/Ansible. `scripts/decrypt-secrets.sh` creates the actual output parent and stages plaintext beside its destination before atomic publication. Direct Make users keep the same runtime-directory default.

## Decisions

- make::target gains the SECRETS_FILE kv for targets whose recipes read or produce the decrypted file (decrypt at minimum; audit-log style consumers get it where the recipe references it). This keeps ENV/PROVIDER discipline and adds one more explicit env rather than relying on ambient agreement.
- Redaction compares against ctx.secrets_file display string case-sensitively plus the historical /tmp pattern; applied in a shared helper used by both bundle entries and ai_prompt.
- Permission gate: use the safe `rustix` filesystem API to open with `NOFOLLOW | NONBLOCK | CLOEXEC`, then evaluate regular-file type, current UID, and private mode bits on the held descriptor before reading. `File::open` followed by metadata alone cannot reject a symlink swap. A private read-only file remains a valid read input.
- Hardening opens the same way and applies mode 0600 through the held descriptor. Missing, symlink, special, foreign-owner, or failed-chmod inputs abort; explain mode performs no filesystem mutation.
- The user approved direct `rustix` 1.x with its `fs` feature. The locked version was already transitive; adding the direct edge does not add a new package version or project unsafe code.
- `make emit-singbox` passes the resolved plaintext as `VPN_SECRETS_FILE`. The emitter validates and converts that document once for all selected hosts; it never falls back to SOPS for an invalid explicit input. Combining this shared document with per-host `SOPS_FILES` is rejected. Direct script invocation without a plaintext input still supports independent encrypted documents.

## Migration / Rollback

No state migration. Direct `make emit-singbox` now requires `make decrypt` first;
run `make clean` after use. Call the emitter script directly for per-host SOPS
documents. This prevents recipient metadata and payload from using different
secret generations.

## Validation

Focused cargo tests: config path resolution matrix (XDG set/unset), doctor redaction with resolved paths incl. --ai branch, actual fd chmod-failure propagation, fstat gate rejecting symlink/mode swap; clippy -D warnings. Actual Make decrypt-to-emitter tests count SOPS invocations and verify the payload uses the authoritative plaintext.
