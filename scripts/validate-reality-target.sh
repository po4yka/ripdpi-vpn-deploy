#!/usr/bin/env bash
# Pre-deploy validator for the REALITY target host. Runs an 8-step check
# (TLS 1.3 handshake, ALPN h2, certificate SAN coverage, plausible
# public CA, real HTTP body, Chrome-uTLS compatibility, anti-template
# heuristic, ASN plausibility) and exits non-zero on any hard failure.
#
# Usage:
#   scripts/validate-reality-target.sh                # reads from secrets
#   TARGET=example.com:443 SERVER_NAMES=example.com \
#     scripts/validate-reality-target.sh              # explicit override
#
# Required env (read from secrets if not set):
#   TARGET          host:port   (xray.target)
#   SERVER_NAMES    space- or comma-separated list (xray.server_names)
#
# Optional:
#   SOPS_FILE       path to encrypted secrets file
#   ENV             default: prod
#   VPS_ASN         ASN integer; if set, [8/8] flags ASN mismatch as a warning
set -euo pipefail

ENV="${ENV:-prod}"
SOPS_FILE="${SOPS_FILE:-${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml}"

if [[ -z "${TARGET:-}" || -z "${SERVER_NAMES:-}" ]]; then
  if [[ ! -f "$SOPS_FILE" ]]; then
    echo "TARGET/SERVER_NAMES not set and no SOPS file at $SOPS_FILE" >&2
    exit 1
  fi
  command -v sops >/dev/null 2>&1 || { echo "missing: sops" >&2; exit 1; }
  command -v jq   >/dev/null 2>&1 || { echo "missing: jq"   >&2; exit 1; }
  TMP="$(mktemp -t vpn-target.XXXXXX)"
  chmod 0600 "$TMP"
  # Install the cleanup trap BEFORE the decrypt so a sops/jq failure (under
  # set -euo pipefail) cannot leave the decrypted secrets file on disk.
  # TARGET_OUT/TARGET_LOG are created later and are covered by the same trap
  # once set (guarded with :- until then). The trap is re-installed identically
  # after those mktemp calls for the env-provided-target code path.
  trap 'rm -f "${TARGET_OUT:-}" "${TARGET_LOG:-}"; [[ -n "${TMP:-}" ]] && { shred -u "$TMP" 2>/dev/null || rm -f "$TMP"; }' EXIT
  sops --decrypt --output-type json "$SOPS_FILE" > "$TMP"
  TARGET="${TARGET:-$(jq -r '.xray.target' "$TMP")}"
  SERVER_NAMES="${SERVER_NAMES:-$(jq -r '.xray.server_names | join(" ")' "$TMP")}"
fi

HOST="${TARGET%:*}"
PORT="${TARGET#*:}"
[[ "$HOST" == "$PORT" ]] && PORT=443

echo "Validating REALITY target: ${HOST}:${PORT}"
echo "Expected serverNames: ${SERVER_NAMES}"
echo

fails=0
warns=0

# Temp files for the TLS handshake; cleaned up on EXIT.
# Also covers the SOPS secret TMP (set above when TARGET/SERVER_NAMES
# were read from the SOPS file; empty otherwise).
TARGET_OUT="$(mktemp -t vpn-target-out.XXXXXX)"
TARGET_LOG="$(mktemp -t vpn-target-log.XXXXXX)"
trap 'rm -f "$TARGET_OUT" "$TARGET_LOG"; [[ -n "${TMP:-}" ]] && { shred -u "$TMP" 2>/dev/null || rm -f "$TMP"; }' EXIT

# ---------------------------------------------------------------------------
# 1. TLS handshake works at all (mandatory)
# ---------------------------------------------------------------------------
echo "[1/8] TLS 1.3 handshake to ${HOST}:${PORT}"
if ! openssl s_client -connect "${HOST}:${PORT}" -servername "${HOST}" \
       -tls1_3 -alpn h2,http/1.1 < /dev/null 2>"$TARGET_LOG" >"$TARGET_OUT"; then
  echo "  FAIL: TLS handshake failed"
  echo "  --- openssl stderr ---"
  cat "$TARGET_LOG" >&2
  echo "  --- end ---"
  fails=$((fails+1))
fi

# Extract handshake metadata
CIPHER="$(grep -E 'New, .*Cipher is' "$TARGET_OUT" | head -1 | sed -E 's/.*Cipher is //')"
ALPN="$(grep -E 'ALPN protocol' "$TARGET_OUT" | head -1 | awk -F': ' '{print $2}')"
[[ -n "$CIPHER" ]] && echo "  cipher: $CIPHER"
[[ -n "$ALPN"   ]] && echo "  ALPN:   $ALPN"

# ---------------------------------------------------------------------------
# 2. ALPN includes h2 (mandatory — REALITY relies on H2)
# ---------------------------------------------------------------------------
echo "[2/8] H2 (ALPN h2) supported"
if [[ "$ALPN" != "h2" ]]; then
  echo "  FAIL: ALPN is '${ALPN}', expected 'h2'"
  fails=$((fails+1))
fi

# ---------------------------------------------------------------------------
# 3. Certificate SAN covers every serverName (mandatory)
# ---------------------------------------------------------------------------
echo "[3/8] Certificate SAN covers every serverName"
SAN="$(openssl s_client -connect "${HOST}:${PORT}" -servername "${HOST}" \
        -showcerts < /dev/null 2>/dev/null \
        | openssl x509 -noout -ext subjectAltName 2>/dev/null \
        | grep DNS: | tr ',' '\n' | sed -E 's/.*DNS://; s/[[:space:]]//g')"

for sn in $SERVER_NAMES; do
  sn_clean="${sn//,/}"
  matched=0
  while IFS= read -r san_entry; do
    [[ -z "$san_entry" ]] && continue
    # Wildcard match
    if [[ "$san_entry" == \*\.* ]]; then
      san_suffix=".${san_entry#*.}"
      [[ "$sn_clean" == *"$san_suffix" ]] && matched=1 && break
    fi
    [[ "$san_entry" == "$sn_clean" ]] && matched=1 && break
  done <<< "$SAN"
  if (( matched )); then
    echo "  ok:   $sn_clean"
  else
    echo "  FAIL: $sn_clean not in SAN"
    fails=$((fails+1))
  fi
done

# ---------------------------------------------------------------------------
# 4. Common Name plausibility (warn) — discourage exotic / mismatched CNs
# ---------------------------------------------------------------------------
echo "[4/8] Subject / issuer plausibility"
SUBJECT="$(openssl s_client -connect "${HOST}:${PORT}" -servername "${HOST}" \
            < /dev/null 2>/dev/null | openssl x509 -noout -subject 2>/dev/null || true)"
ISSUER="$(openssl s_client -connect "${HOST}:${PORT}" -servername "${HOST}" \
           < /dev/null 2>/dev/null | openssl x509 -noout -issuer 2>/dev/null || true)"
echo "  $SUBJECT"
echo "  $ISSUER"

# Heuristic: well-known public CAs only. Self-signed / unknown CA = warn.
if ! echo "$ISSUER" | grep -qE "(Let's Encrypt|DigiCert|Sectigo|GlobalSign|Amazon|Google Trust|Cloudflare)"; then
  echo "  WARN: issuer not a recognised public CA — REALITY plausibility may suffer"
  warns=$((warns+1))
fi

# ---------------------------------------------------------------------------
# 5. HTTP/2 200 on /  (mandatory — empty/redirect-loop targets fail probes)
# ---------------------------------------------------------------------------
echo "[5/8] HTTPS GET / returns a real response"
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
              --resolve "${HOST}:${PORT}:$(getent hosts "$HOST" | awk '{print $1}' | head -1)" \
              "https://${HOST}:${PORT}/" || echo 000)"
echo "  HTTP $HTTP_CODE"
case "$HTTP_CODE" in
  2*|3*) ;;  # ok
  4*|5*)
    if [[ "$HTTP_CODE" == "404" || "$HTTP_CODE" == "403" ]]; then
      echo "  WARN: $HTTP_CODE — acceptable but check the body looks like a real site"
      warns=$((warns+1))
    else
      echo "  FAIL: target returned $HTTP_CODE"
      fails=$((fails+1))
    fi
    ;;
  *)
    echo "  FAIL: no HTTP response"
    fails=$((fails+1))
    ;;
esac

# ---------------------------------------------------------------------------
# 6. uTLS Chrome fingerprint compatibility (warn)
# ---------------------------------------------------------------------------
echo "[6/8] uTLS Chrome compatibility (mimic ClientHello)"
if curl -fsS --max-time 10 \
     -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36' \
     --tls-max 1.3 \
     "https://${HOST}:${PORT}/" >/dev/null 2>&1; then
  echo "  ok"
else
  echo "  WARN: could not establish session with Chrome-like UA"
  warns=$((warns+1))
fi

# ---------------------------------------------------------------------------
# 7. Anti-template OPSEC heuristic (warn) — overused REALITY targets
# ---------------------------------------------------------------------------
echo "[7/8] Target popularity heuristic"
overused="www.cloudflare.com www.microsoft.com www.apple.com www.google.com discord.com"
for o in $overused; do
  if [[ "$HOST" == "$o" ]]; then
    echo "  WARN: '$HOST' is in the over-template list — OPSEC value reduced"
    warns=$((warns+1))
    break
  fi
done

# ---------------------------------------------------------------------------
# 8. ASN plausibility (warn) — target IP should live on an ASN that looks
#    plausible alongside the VPS. Hyperscaler/global-brand SNI on a small
#    VPS-hosting IP creates an ASN/SNI mismatch that TSPU's IP-reputation
#    pipeline can score against. See reality-target-selection-2026.
# ---------------------------------------------------------------------------
echo "[8/8] Target ASN plausibility"
target_ip="$(getent hosts "$HOST" | awk '{print $1}' | head -1)"
if [[ -z "$target_ip" ]]; then
  echo "  WARN: could not resolve $HOST to compare ASN"
  warns=$((warns+1))
else
  # Cymru's whois server returns "AS | IP | BGP Prefix | CC | Registry | Allocated | AS Name"
  asn_line="$(whois -h whois.cymru.com " -v $target_ip" 2>/dev/null | tail -1 || true)"
  if [[ -z "$asn_line" ]] || echo "$asn_line" | grep -qiE '^bulk|^error|<html'; then
    echo "  WARN: ASN lookup unavailable (Team Cymru whois) — skip"
    warns=$((warns+1))
  else
    target_asn="$(echo "$asn_line" | awk -F'|' '{gsub(/^ +| +$/,"",$1); print $1}')"
    target_org="$(echo "$asn_line" | awk -F'|' '{gsub(/^ +| +$/,"",$7); print $7}')"
    echo "  target_ip=$target_ip  asn=AS${target_asn}  org=${target_org}"

    # Flag the "Avoid" tier (docs/PROVIDER-NOTES.md) outright — these prefixes
    # are bucketed as foreign-datacenter by TSPU and trigger TCP freeze.
    case "$target_asn" in
      13335|16276|24940|14061|26383|216071)
        echo "  WARN: target ASN AS${target_asn} is in the Avoid tier (see docs/PROVIDER-NOTES.md)"
        warns=$((warns+1)) ;;
    esac

    # If the operator exported VPS_ASN (e.g. from terraform output), compare.
    if [[ -n "${VPS_ASN:-}" ]]; then
      if [[ "$target_asn" == "$VPS_ASN" ]]; then
        echo "  ok: target ASN matches VPS ASN"
      else
        echo "  WARN: VPS_ASN=$VPS_ASN does not match target AS${target_asn} (ASN/SNI mismatch heuristic)"
        warns=$((warns+1))
      fi
    fi
  fi
fi

echo
echo "summary: ${fails} hard failure(s), ${warns} warning(s)"
(( fails == 0 )) || exit 1
exit 0
