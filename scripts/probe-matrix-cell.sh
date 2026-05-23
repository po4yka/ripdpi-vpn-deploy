#!/usr/bin/env bash
# Per-cell probe wrapper for `vpnd probe-matrix`. The vpnd orchestrator
# invokes this once per (protocol × destination) at each tick. The
# contract: emit exactly one JSON object on stdout matching
#   {"verdict": "ok|throttled|blocked|unknown|error", "rtt_ms": <int|null>}
# Anything else (stderr noise, non-zero exit) is reported by the
# orchestrator as verdict=error and recorded with error_kind.
#
# Required env (set by Make target `probe-matrix-cell`):
#   PROTOCOL    — one of: mtproto | xhttp-vless | xhttp-trojan | tcp-trojan | tls-non-443
#   DEST_CLASS  — one of: domestic-allowlisted | domestic-generic | foreign-non-allowlist
#   DEST        — endpoint literal (IP:port)
#   VANTAGE     — operator-supplied label for the probe origin VPS
#
# Today: every probe returns `unknown` because the protocol-specific
# probe drivers are not implemented yet. The contract is in place so
# downstream snapshot tests and the JSON schema lock; future PRs wire
# real probes (MTProto handshake / VLESS-XHTTP request / Trojan TLS /
# raw TLS on non-443) without changing this script's stdout shape.

set -euo pipefail

: "${PROTOCOL:?missing PROTOCOL}"
: "${DEST_CLASS:?missing DEST_CLASS}"
: "${DEST:?missing DEST}"
: "${VANTAGE:?missing VANTAGE}"

case "$PROTOCOL" in
  mtproto|xhttp-vless|xhttp-trojan|tcp-trojan|tls-non-443) ;;
  *) echo "{\"verdict\": \"error\", \"rtt_ms\": null, \"error_kind\": \"unknown protocol: $PROTOCOL\"}"; exit 0 ;;
esac

case "$DEST_CLASS" in
  domestic-allowlisted|domestic-generic|foreign-non-allowlist) ;;
  *) echo "{\"verdict\": \"error\", \"rtt_ms\": null, \"error_kind\": \"unknown destination class: $DEST_CLASS\"}"; exit 0 ;;
esac

# Placeholder — future PRs implement real per-protocol probes here.
# Emitting `unknown` (not `ok`) so a downstream alert that fires on
# unexpected-OK does not silently swallow the missing implementation.
printf '{"verdict": "unknown", "rtt_ms": null}\n'
