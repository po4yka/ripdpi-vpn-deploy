#!/usr/bin/env bash
# Per-cell probe wrapper for `vpnd probe-matrix`. The vpnd orchestrator
# invokes this once per (protocol × destination) at each tick. The
# contract: emit exactly one JSON object on stdout matching
#   {"verdict": "ok|throttled|blocked|unknown|error", "rtt_ms": <int|null>}
# Anything else (stderr noise, non-zero exit) is reported by the
# orchestrator as verdict=error and recorded with error_kind.
#
# Required env (set by Make target `probe-matrix-cell`): MATRIX_CONFIG,
# TARGET_ID, PROTOCOL, and CONTROL_VERDICT. Secret-bearing target profiles are
# read from their permission-checked files and never passed through argv/env.

set -euo pipefail

: "${PROTOCOL:?missing PROTOCOL}"
: "${MATRIX_CONFIG:?missing MATRIX_CONFIG}"
: "${TARGET_ID:?missing TARGET_ID}"
: "${CONTROL_VERDICT:?missing CONTROL_VERDICT}"

case "$PROTOCOL" in
  mtproto|xhttp-vless|xhttp-trojan|tcp-trojan|tls-non-443) ;;
  *) echo '{"verdict":"error","rtt_ms":null,"error_kind":"protocol-unknown"}'; exit 0 ;;
esac

exec python3 "$(dirname "$0")/probe-matrix-driver.py" cell \
  --config "$MATRIX_CONFIG" \
  --target-id "$TARGET_ID" \
  --protocol "$PROTOCOL" \
  --control-verdict "$CONTROL_VERDICT"
