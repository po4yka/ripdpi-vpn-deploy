#!/usr/bin/env bash
# Emit a client AmneziaWG wg-quick .conf (INI) for a named peer.
#
# The emitted file mirrors the server-side awg0.conf.j2 template field-for-field
# but from the client perspective: Interface uses the *client* address (peer
# allowed_ips from secrets) and Peer points at the server.
#
# Usage:
#   PROVIDER=upcloud ENV=prod  scripts/emit-awg.sh phone
#   SOPS_FILE=~/.config/vpn-provision/prod.secrets.sops.yaml \
#     PROVIDER=upcloud ENV=prod  scripts/emit-awg.sh phone
#
# Obfuscation parameter precedence (mirrors tasks/main.yml set_fact):
#   amneziawg_secrets.{jc,jmin,jmax,s1,s2,h1..h4}   (SOPS — highest)
#   amneziawg_cohort.{…}  from vars/cohorts/<AWG_COHORT>.yml (if AWG_COHORT set)
#   hard defaults: jc=4 jmin=40 jmax=70 s1=50 s2=100 (h1..h4 have no default)
#
# The client PrivateKey is NEVER stored in SOPS. The emitted config contains a
# clearly-marked placeholder. The operator must fill it in from the secure
# channel used during key hand-off (see scripts/new-client.sh output).
#
# Environment variables:
#   CLIENT_NAME  — name arg (positional $1)
#   PROVIDER     — terraform provider dir under terraform/providers/ (default: upcloud)
#   ENV          — environment label used for SOPS file path lookup (default: prod)
#   SOPS_FILE    — explicit path to the SOPS-encrypted secrets file
#                  (default: ~/.config/vpn-provision/<ENV>.secrets.sops.yaml)
#   AWG_COHORT   — cohort slug to load obfuscation defaults from
#                  vars/cohorts/<slug>.yml (optional; falls back to hard defaults)
#
# Requires: sops, terraform, awg or wg, python3, jq
set -euo pipefail

CLIENT_NAME="${1:-}"
if [[ -z "$CLIENT_NAME" ]]; then
  echo "usage: $0 <client_name>" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for tool in sops terraform python3 jq; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing: $tool" >&2; exit 1; }
done

# awg or wg — prefer awg (AmneziaWG tools), fall back to wg (standard WireGuard)
AWG_PUBKEY_CMD=""
if command -v awg >/dev/null 2>&1; then
  AWG_PUBKEY_CMD="awg pubkey"
elif command -v wg >/dev/null 2>&1; then
  AWG_PUBKEY_CMD="wg pubkey"
else
  echo "missing: awg or wg (needed to derive server public key from private key)" >&2
  exit 1
fi

ENV="${ENV:-prod}"
PROVIDER="${PROVIDER:-upcloud}"
SOPS_FILE="${SOPS_FILE:-${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml}"

if [[ ! -f "$SOPS_FILE" ]]; then
  echo "missing $SOPS_FILE (set SOPS_FILE= or ENV= to override)" >&2
  exit 1
fi

# Decrypt secrets to a temp file; shred on exit regardless of success or failure.
WORK="$(mktemp -d -t vpn-awg.XXXXXX)"
trap 'find "$WORK" -type f -exec shred -u {} + 2>/dev/null; rm -rf "$WORK"' EXIT

SECRETS_TMP="${WORK}/secrets.json"
sops --decrypt --output-type json "$SOPS_FILE" > "$SECRETS_TMP"
chmod 0600 "$SECRETS_TMP"

# ---------------------------------------------------------------------------
# Resolve peer entry from secrets
# ---------------------------------------------------------------------------
peer_json="$(jq --arg name "$CLIENT_NAME" \
  '.amneziawg_secrets.peers[]? | select(.name == $name)' "$SECRETS_TMP")"

if [[ -z "$peer_json" || "$peer_json" == "null" ]]; then
  echo "no AmneziaWG peer named '$CLIENT_NAME' in amneziawg_secrets.peers in ${SOPS_FILE}" >&2
  exit 1
fi

peer_psk="$(jq -r '.preshared_key' <<< "$peer_json")"
peer_allowed_ips="$(jq -r '.allowed_ips' <<< "$peer_json")"

# The client Interface.Address is the peer's own IP (with /32 → /32 preserved).
client_address="$peer_allowed_ips"

# ---------------------------------------------------------------------------
# Derive server public key from server_private_key via awg/wg pubkey
# ---------------------------------------------------------------------------
server_priv="$(jq -r '.amneziawg_secrets.server_private_key // empty' "$SECRETS_TMP")"
if [[ -z "$server_priv" ]]; then
  echo "amneziawg_secrets.server_private_key is missing or empty in ${SOPS_FILE}" >&2
  exit 1
fi

server_pubkey_file="${WORK}/server.pub"
printf '%s' "$server_priv" | $AWG_PUBKEY_CMD > "$server_pubkey_file"
server_pubkey="$(cat "$server_pubkey_file")"

# ---------------------------------------------------------------------------
# Resolve server endpoint: server_ip:listen_port from terraform + secrets
# ---------------------------------------------------------------------------
tf_dir="${REPO_ROOT}/terraform/providers/${PROVIDER}"
server_ip="$(terraform -chdir="$tf_dir" output -raw server_ipv4)"

listen_port="$(jq -r '.amneziawg_secrets.listen_port // empty' "$SECRETS_TMP")"
if [[ -z "$listen_port" ]]; then
  # Fall back to the Ansible role default (amneziawg.listen_port)
  listen_port=51820
fi

# ---------------------------------------------------------------------------
# Resolve obfuscation parameters (mirrors tasks/main.yml set_fact precedence):
#   1. amneziawg_secrets.* (SOPS — highest priority)
#   2. amneziawg_cohort.* from vars/cohorts/<AWG_COHORT>.yml
#   3. hard role defaults (jc=4 jmin=40 jmax=70 s1=50 s2=100)
# H1..H4 have no hard default — must come from secrets or cohort.
# ---------------------------------------------------------------------------
AWG_COHORT="${AWG_COHORT:-}"
cohort_yml=""
if [[ -n "$AWG_COHORT" ]]; then
  cohort_file="${REPO_ROOT}/ansible/roles/amneziawg/vars/cohorts/${AWG_COHORT}.yml"
  if [[ ! -f "$cohort_file" ]]; then
    echo "cohort file not found: $cohort_file" >&2
    exit 1
  fi
  cohort_yml="$cohort_file"
fi

resolve_param() {
  # Resolve one obfuscation parameter with the three-level precedence.
  # Args: <param_name> <default_value_or_empty>
  local param="$1"
  local default="$2"

  # Level 1: amneziawg_secrets.<param> from SOPS
  local val
  val="$(jq -r --arg p "$param" '.amneziawg_secrets[$p] // empty' "$SECRETS_TMP")"
  if [[ -n "$val" ]]; then
    echo "$val"
    return
  fi

  # Level 2: amneziawg_cohort.<param> from cohort YAML (parsed via python3)
  if [[ -n "$cohort_yml" ]]; then
    val="$(python3 - "$cohort_yml" "$param" <<'PY'
import sys
import yaml
data = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
cohort = data.get("amneziawg_cohort") or {}
v = cohort.get(sys.argv[2])
if v is not None:
    print(v)
PY
)"
    if [[ -n "$val" ]]; then
      echo "$val"
      return
    fi
  fi

  # Level 3: hard default
  if [[ -n "$default" ]]; then
    echo "$default"
    return
  fi

  # No value found — caller must handle
  echo ""
}

jc="$(resolve_param jc 4)"
jmin="$(resolve_param jmin 40)"
jmax="$(resolve_param jmax 70)"
s1="$(resolve_param s1 50)"
s2="$(resolve_param s2 100)"
h1="$(resolve_param h1 "")"
h2="$(resolve_param h2 "")"
h3="$(resolve_param h3 "")"
h4="$(resolve_param h4 "")"

if [[ -z "$h1" || -z "$h2" || -z "$h3" || -z "$h4" ]]; then
  echo "H1..H4 are required but could not be resolved from secrets or cohort." >&2
  echo "Set amneziawg_secrets.h1..h4 in SOPS or specify AWG_COHORT=<slug>." >&2
  exit 1
fi

# AWG 2.0 requires that H1..H4 are pairwise distinct (non-overlapping header magic).
# Duplicate values cause the server to mis-classify handshake packet types.
# POSIX sort|uniq -d keeps this portable (no bash-4 associative array).
_dup_h="$(printf '%s\n' "$h1" "$h2" "$h3" "$h4" | sort | uniq -d | head -1)"
if [[ -n "$_dup_h" ]]; then
  echo "H1..H4 must be pairwise distinct: value ${_dup_h} is used more than once" >&2
  exit 1
fi
unset _dup_h

# Optional I1..I5 (init-packet size overrides) — present in some cohorts.
# Emit only when the param is present in secrets or cohort; no hard default.
# (Resolved inline in the "Emit I1..I5" loop below.)

# DNS servers come from the role defaults (not cohort-specific).
dns_servers="1.1.1.1, 1.0.0.1"

# MTU: AmneziaWG default is 1420 (same as WireGuard).
mtu=1420

# ---------------------------------------------------------------------------
# Emit the wg-quick .conf
# ---------------------------------------------------------------------------
cat <<EOF
[Interface]
# PrivateKey: the client private key is NOT stored in SOPS and is NEVER
# committed to the repository. Fill in the private key that was generated
# by scripts/new-client.sh and handed to this device through a secure
# channel (Signal, in-person QR, encrypted notes app).
PrivateKey = PASTE_CLIENT_PRIVATE_KEY_HERE
Address    = ${client_address}
DNS        = ${dns_servers}
MTU        = ${mtu}

# AmneziaWG obfuscation parameters — must match the server awg0.conf exactly.
Jc   = ${jc}
Jmin = ${jmin}
Jmax = ${jmax}
S1   = ${s1}
S2   = ${s2}
H1   = ${h1}
H2   = ${h2}
H3   = ${h3}
H4   = ${h4}
EOF

# Emit I1..I5 only when they are configured.
for i_param in i1 i2 i3 i4 i5; do
  i_val="$(resolve_param "$i_param" "")"
  if [[ -n "$i_val" ]]; then
    upper_param="$(echo "$i_param" | tr '[:lower:]' '[:upper:]')"
    printf '%s = %s\n' "$upper_param" "$i_val"
  fi
done

cat <<EOF

[Peer]
# Server public key derived from amneziawg_secrets.server_private_key via ${AWG_PUBKEY_CMD%% *} pubkey.
PublicKey           = ${server_pubkey}
PresharedKey        = ${peer_psk}
Endpoint            = ${server_ip}:${listen_port}
AllowedIPs          = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
EOF
