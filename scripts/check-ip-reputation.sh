#!/usr/bin/env bash
# Check the deployed VPS public IP against well-known reputation lists.
# Daily run cadence — costs three DNS queries plus one HTTPS call when
# ABUSEIPDB_KEY is set.
#
# Lists consulted:
#   Spamhaus DROP / EDROP (DNS RBL: zen.spamhaus.org)
#   FireHOL Level 1 IP set (optional local netset via FIREHOL_NETSET_FILE)
#   AbuseIPDB confidence-of-abuse score (HTTPS; needs ABUSEIPDB_KEY)
#
# SCOPE — HOSTING-ABUSE HYGIENE, NOT RU/TSPU BURN STATE.
# Hits on Spamhaus, FireHOL, or AbuseIPDB indicate that the IP has been
# associated with spam, malware, or generic hosting abuse. This is DISTINCT
# from TSPU burn. TSPU burn is AS-level behavioural scoring derived from
# traffic observation on RU paths — it is independent of these abuse feeds
# and an IP can be TSPU-burned while appearing clean here, or vice versa.
# For actual RU burn detection, use RU-vantage reachability probing via
# scripts/burn-check.sh (see docs/TRANSPORT-REACHABILITY-MATRIX.md).
#
# On finding, exits 1 and (when ntfy is configured) sends an alert.
#
# Usage:
#   PROVIDER=upcloud ENV=prod scripts/check-ip-reputation.sh
#   IP=1.2.3.4 scripts/check-ip-reputation.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE_DIR="${HOME}/.cache/vpn-deploy"
mkdir -p "$CACHE_DIR"

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"

if [[ -z "${IP:-}" ]]; then
  TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"
  IP="$(terraform -chdir="$TF_DIR" output -raw server_ipv4 2>/dev/null || true)"
fi
if [[ -z "${IP:-}" ]]; then
  echo "no IP available (terraform output missing? export IP=… to override)" >&2
  exit 2
fi

# Reverse the IP for RBL lookups.
IFS=. read -r a b c d <<< "$IP"
rev="${d}.${c}.${b}.${a}"

findings=()

# ---------------------------------------------------------------------------
# Spamhaus zen — DNS query; A response means listed.
# ---------------------------------------------------------------------------
spamhaus_q="${rev}.zen.spamhaus.org"
spam_resp="$(dig +short "$spamhaus_q" A 2>/dev/null | head -1 || true)"
if [[ -n "$spam_resp" ]]; then
  # Spamhaus refuses responses to public/open resolvers and signals it with
  # 127.255.255.x sentinel codes. Don't treat those as a real listing —
  # they mean "lookup unreliable from this resolver".
  if [[ "$spam_resp" =~ ^127\.255\.255\. ]]; then
    echo "  (info) Spamhaus zen returned the open-resolver sentinel ${spam_resp};" \
         "lookup unreliable — use a private DNS resolver or DNSBL contributor account" >&2
  else
    findings+=("Spamhaus zen: listed (response=$spam_resp)")
  fi
fi

# ---------------------------------------------------------------------------
# FireHOL Level 1 — optional local IP set. CI/CD policy forbids this script
# from downloading and trusting a mutable external netset at runtime; operators
# who want this check should refresh the file out-of-band and point to it.
# ---------------------------------------------------------------------------
fh_cache="${FIREHOL_NETSET_FILE:-${CACHE_DIR}/firehol_level1.netset}"
if [[ ! -f "$fh_cache" ]]; then
  echo "  (info) FireHOL netset not present; set FIREHOL_NETSET_FILE to enable that check" >&2
fi
if [[ -f "$fh_cache" ]] && python3 -c "
import ipaddress, pathlib, sys
ip = ipaddress.ip_address('$IP')
for line in pathlib.Path('$fh_cache').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#'): continue
    if ip in ipaddress.ip_network(line, strict=False):
        sys.exit(0)
sys.exit(1)
"; then
  findings+=("FireHOL Level 1: listed in $fh_cache")
fi

# ---------------------------------------------------------------------------
# AbuseIPDB — optional, only if key is provided.
# ---------------------------------------------------------------------------
if [[ -n "${ABUSEIPDB_KEY:-}" ]]; then
  score="$(ABUSEIPDB_KEY="${ABUSEIPDB_KEY}" IP="${IP}" python3 - <<'PY' 2>/dev/null || true
import json
import os
import urllib.parse
import urllib.request

query = urllib.parse.urlencode({"ipAddress": os.environ["IP"], "maxAgeInDays": "30"})
request = urllib.request.Request(
    f"https://api.abuseipdb.com/api/v2/check?{query}",
    headers={"Key": os.environ["ABUSEIPDB_KEY"], "Accept": "application/json"},
)
with urllib.request.urlopen(request, timeout=10) as response:
    print(json.load(response)["data"]["abuseConfidenceScore"])
PY
  )"
  if [[ "${score:-0}" =~ ^[0-9]+$ ]] && (( score >= 25 )); then
    findings+=("AbuseIPDB: abuseConfidenceScore=${score}")
  fi
fi

echo "IP=${IP}  provider=${PROVIDER}  env=${ENV}"
if (( ${#findings[@]} == 0 )); then
  echo "OK — IP reputation clean"
  exit 0
fi

printf '  - %s\n' "${findings[@]}"

if [[ -n "${NTFY_TOPIC:-}" ]]; then
  NTFY_URL="${NTFY_URL:-https://ntfy.sh}"
  auth=()
  [[ -n "${NTFY_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer ${NTFY_TOKEN}")
  msg="IP reputation finding on ${PROVIDER}:${ENV} IP=${IP}
$(printf '%s\n' "${findings[@]}")"
  curl -fsS -X POST \
    -H "Title: IP reputation: ${PROVIDER}:${ENV}" \
    -H "Priority: high" \
    -H "Tags: warning,vpn,ip-reputation" \
    "${auth[@]}" \
    --data "$msg" \
    "${NTFY_URL%/}/${NTFY_TOPIC}" >/dev/null || true
fi
exit 1
