#!/usr/bin/env bash
# Decrypt the SOPS-encrypted secrets file into a temporary plaintext file with
# 0600 perms. Caller is responsible for shredding it after use (see Makefile
# target `clean`).
#
# The plaintext cache lives in a volatile location by default:
# XDG_RUNTIME_DIR when present, else a TMPDIR path. Both are excluded from
# desktop backup agents (Time Machine etc.) and cleared on reboot, unlike
# ~/.cache, which backup tools routinely include.
set -euo pipefail

ENV="${ENV:-prod}"
SOPS_FILE="${SOPS_FILE:-${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml}"
RUNTIME_DIR="${VPN_RUNTIME_DIR:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}/vpn-provision}}"
OUT="${SECRETS_FILE:-${RUNTIME_DIR}/vpn-${ENV}.secrets.yaml}"

if [[ ! -f "$SOPS_FILE" ]]; then
  echo "missing SOPS file: $SOPS_FILE" >&2
  echo "create it with: sops --encrypt --age <recipient> ~/.config/vpn-provision/${ENV}.secrets.yaml > ${SOPS_FILE}" >&2
  exit 1
fi

umask 077
mkdir -p "$RUNTIME_DIR"
chmod 0700 "$RUNTIME_DIR"
[[ -d "$RUNTIME_DIR" && ! -L "$RUNTIME_DIR" ]] || { echo "unsafe runtime directory: $RUNTIME_DIR" >&2; exit 1; }
tmp="$(mktemp "${RUNTIME_DIR}/.vpn-${ENV}.secrets.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
sops --decrypt "$SOPS_FILE" > "$tmp"
chmod 0600 "$tmp"
mv -f "$tmp" "$OUT"
trap - EXIT

echo "decrypted to $OUT"
echo "remember to shred after use: shred -u $OUT"
