---
name: bash-scripting
description: Shell conventions for this repo's operator scripts and role-deployed shell templates, with real exemplar scripts for secrets, locking, and checksums. Use when writing or reviewing scripts/*.sh, an ansible/roles/*/templates/*.sh.j2 script, or a non-trivial Makefile shell recipe. Not for scripts/*.py.
---

# Shell scripts (vpn-deploy)

Operators run these scripts on both macOS and Linux workstations, and several handle decrypted secrets. `scripts/CLAUDE.md` holds the per-script pitfalls; this skill covers the conventions that apply to every shell file.

## Conventions

- `#!/usr/bin/env bash` and `set -euo pipefail` (58 of 59 scripts). The one exception, `scripts/restore.sh`, is deliberately POSIX `#!/bin/sh` with `set -eu` and says why in its header; follow that pattern only when bash is genuinely unavailable.
- Resolve the repo root the way existing scripts do: `REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"`. Most scripts take their inputs from environment variables set by the Makefile (`PROVIDER`, `ENV`, `HOSTS`, `SOPS_FILE`, ...) rather than flags.
- Quote every expansion, never `eval` operator input, and use `printf '%q'` when forwarding values into a nested shell.
- `shellcheck -s bash -S warning` must pass (`make shellcheck`, pre-commit, and CI run it on `scripts/*.sh` and `terraform/exception/cascade-ingress/*.sh`). A `# shellcheck disable=` needs a one-line justification above it. Role `*.sh.j2` templates are Jinja and are not shellchecked, so review them by hand.
- Plain `exit 1` is the norm. Use distinct exit codes only when a caller branches on them, and document them in the script header.
- Stay portable: `command -v`, not `which`; explicit `mktemp` templates (macOS `mktemp -t` ignores `TMPDIR`); `sha256sum` with a `shasum -a 256` fallback; `flock` with a `lockf` fallback.

## Secrets and side effects

- Never re-implement decryption. Pipe `sops --decrypt --output-type json ... | python3 ...` when the plaintext is consumed once (`new-client.sh`, `issue-sub-token.sh`). When a file is unavoidable, follow `decrypt-secrets.sh`: runtime dir `${VPN_RUNTIME_DIR:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}/vpn-provision-$(id -u)}}`, `mktemp` inside it, `chmod 0600` at once, `trap 'rm -f "$tmp"' EXIT`, then an atomic `mv`.
- No `set -x` in scripts that can see secrets; gate debug output behind an explicit opt-in.
- Downloads are pinned and checksum-verified before execution (`install-vpnd.sh`); never pipe a remote installer into a shell.
- Lock the resource being protected, not a synthetic name: `new-client.sh` opens `${SOPS_FILE}.new-client.lock` on FD 9 and takes `flock -n 9` or `lockf -s -t 0 9`. Shared SOPS writers must use that same lock file.
- Destructive scripts append to the audit log with `audit-log.sh append-best-effort` so a logging failure never fails the operation.
- Trap `EXIT` for cleanup; `ERR` alone misses signal-driven exits.

## Tests

bats suites live in `tests/bats/` (run with `bats tests/bats/`; part of `make ci-fast`). Add one when a script gains non-trivial argument validation or a dry-run mode; see `fleet_rotate_dryrun.bats` and `blue_green_dryrun.bats` for the stub-binary pattern in `tests/stubs/bin/`.
