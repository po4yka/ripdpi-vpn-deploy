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
# User-specific fallback: a shared predictable directory would be owned by
# whichever local account created it first, locking every other one out.
RUNTIME_DIR="${VPN_RUNTIME_DIR:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}/vpn-provision-$(id -u)}}"
OUT="${SECRETS_FILE:-${RUNTIME_DIR}/vpn-${ENV}.secrets.yaml}"

if [[ ! -f "$SOPS_FILE" ]]; then
  echo "missing SOPS file: $SOPS_FILE" >&2
  echo "create it with: sops --encrypt --age <recipient> ~/.config/vpn-provision/${ENV}.secrets.yaml > ${SOPS_FILE}" >&2
  exit 1
fi

umask 077
# The explicit output path is authoritative. Create its parent, and stage
# beside the destination so publication is atomic even across filesystems.
# Do not chmod an existing operator directory (it may have other users).
OUT_DIR="$(dirname "$OUT")"
mkdir -p "$OUT_DIR"
[[ -d "$OUT_DIR" && ! -L "$OUT_DIR" && -O "$OUT_DIR" ]] || { echo "unsafe secrets output directory" >&2; exit 1; }
if [[ -n "$(find "$OUT_DIR" -prune \( -perm -0020 -o -perm -0002 \) -print)" ]]; then
  echo "secrets output directory must not be writable by other users" >&2
  exit 1
fi
[[ ! -L "$OUT" && ( ! -e "$OUT" || -f "$OUT" ) ]] || { echo "secrets output must be a regular file" >&2; exit 1; }
tmp="$(mktemp "${OUT_DIR}/.vpn-${ENV}.secrets.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
sops --decrypt "$SOPS_FILE" > "$tmp"
chmod 0600 "$tmp"
mv -f "$tmp" "$OUT"
trap - EXIT

echo "decrypted secrets ready (0600)"
echo "remember to run make clean after use"
