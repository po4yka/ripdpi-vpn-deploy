#!/usr/bin/env bash
# Verify exact bounded payloads from an owned HTTP(S) origin. Run on the
# client path, optionally through --socks-port; --upload also checks POST.
# Emits one redacted JSON verdict; local/endpoint errors never prove censorship.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' '{"verdict":"error","rtt_ms":null,"error_kind":"missing-python"}'
  exit 0
fi
exec python3 "${REPO_ROOT}/scripts/payload_probe_content.py" "$@"
