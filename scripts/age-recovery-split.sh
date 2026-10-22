#!/usr/bin/env bash
# Split the operator's age private key into k-of-n Shamir shares using ssss.
# Without this, losing the age key means full credential rotation
# (docs/how-to/incident.md § "Lost age key").
#
# Usage:
#   scripts/age-recovery-split.sh <threshold> <total_shares>
# Example: 2-of-3 (any 2 shares can reconstruct the key):
#   scripts/age-recovery-split.sh 2 3
#
# Output: shares printed to stdout. Each share goes to a different
# storage location (1Password vault, Bitwarden Send, sealed envelope in a
# safe, etc.). NEVER store all shares together — that defeats the point.
set -euo pipefail

T="${1:-}"
N="${2:-}"

if [[ -z "$T" || -z "$N" ]]; then
  echo "usage: $0 <threshold> <total_shares>" >&2
  echo "example: $0 2 3   # 2-of-3 reconstruction" >&2
  exit 1
fi

if (( T < 2 )) || (( T > N )) || (( N > 9 )); then
  echo "constraint violated: 2 <= T <= N, N <= 9 (ssss limit)" >&2
  exit 1
fi

command -v ssss-split >/dev/null 2>&1 || {
  echo "missing: ssss-split" >&2
  echo "install: brew install ssss   |   apt install ssss" >&2
  exit 1
}

AGE_KEY="${AGE_KEY:-${HOME}/.config/vpn-provision/age.key}"
if [[ ! -f "$AGE_KEY" ]]; then
  echo "missing $AGE_KEY" >&2
  exit 1
fi

# ssss-split limit: 128 chars per secret. age private key is short enough
# (AGE-SECRET-KEY-1… ~74 chars). Strip the comment lines first.
SECRET="$(grep -v '^#' "$AGE_KEY" | grep AGE-SECRET-KEY | head -1 | tr -d '\n')"
if [[ -z "$SECRET" ]]; then
  echo "could not extract AGE-SECRET-KEY from $AGE_KEY" >&2
  exit 1
fi

echo "Splitting age private key into ${T}-of-${N} shares."
echo
echo "ssss-split output (each line is one share — distribute separately):"
echo
echo "$SECRET" | ssss-split -t "$T" -n "$N" -Q 2>&1 | grep -E '^[0-9]+-'
echo
cat <<EOF

IMPORTANT:
  - Hand each share to a *different* storage location. Anyone holding T
    shares can reconstruct the full key.
  - Do NOT screenshot the terminal. Do NOT paste into chat.
  - To reconstruct: scripts/age-recovery-combine.sh
  - Test the reconstruction NOW, before you need it. See docs/how-to/age-recovery.md.
EOF
