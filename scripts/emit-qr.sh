#!/usr/bin/env bash
# Emit a PNG QR code carrying either a VLESS+REALITY URI or the full
# sing-box client JSON for a given client name. Outputs the PNG to a
# file or to stdout (when --stdout is given, useful for piping to img2sixel
# / displays).
#
# Usage:
#   scripts/emit-qr.sh phone                          # default: sing-box JSON, PNG to phone.qr.png
#   scripts/emit-qr.sh phone --type uri               # VLESS+REALITY URI form
#   scripts/emit-qr.sh phone --out laptop.png
#   scripts/emit-qr.sh phone --stdout | img2sixel
#
# Picks up the same PROVIDER / ENV / HOSTS env vars as emit-singbox.sh
# and new-client.sh.
set -euo pipefail

CLIENT="${1:-}"
[[ "$CLIENT" =~ ^[A-Za-z0-9_-]{1,64}$ ]] || { echo "client name must contain only letters, digits, underscores, or dashes" >&2; exit 1; }
[[ -n "$CLIENT" && "$CLIENT" != "-h" && "$CLIENT" != "--help" ]] || {
  sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2
  exit 1
}
shift

TYPE=singbox
OUT=""
STDOUT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --type)   TYPE="$2"; shift 2 ;;
    --out)    OUT="$2"; shift 2 ;;
    --stdout) STDOUT=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

command -v qrencode >/dev/null 2>&1 || {
  echo "missing tool: qrencode (brew install qrencode / apt install qrencode)" >&2
  exit 1
}

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

case "$TYPE" in
  singbox)
    payload="$("${REPO_ROOT}/scripts/emit-singbox.sh" "$CLIENT")"
    ;;
  uri)
    payload="$(SOPS_FILE="${SOPS_FILE:-${HOME}/.config/vpn-provision/${ENV:-prod}.secrets.sops.yaml}" \
                "${REPO_ROOT}/scripts/new-client.sh" --emit-uri "$CLIENT")"
    ;;
  *)
    echo "unknown --type: $TYPE (expected singbox|uri)" >&2
    exit 1
    ;;
esac

if [[ -z "$payload" ]]; then
  echo "empty payload from upstream emitter — refuse to render an empty QR" >&2
  exit 1
fi

if (( STDOUT )); then
  echo "$payload" | qrencode -t PNG -o -
  exit 0
fi

if [[ -z "$OUT" ]]; then
  OUT="${CLIENT}.qr.png"
fi
echo "$payload" | qrencode -t PNG -o "$OUT"
echo "wrote: $OUT  (type=$TYPE, $(wc -c < "$OUT" | tr -d ' ') bytes)"
