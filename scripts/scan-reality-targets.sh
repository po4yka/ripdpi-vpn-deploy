#!/usr/bin/env bash
# Operator-side REALITY-target discovery via XTLS/RealiTLScanner.
#
# Runs on the operator workstation, NEVER on the VPS itself. RealiTLScanner's
# README is explicit: "running the scanner in the cloud may cause the VPS to
# be flagged" — same OPSEC rule we follow elsewhere.
#
# Flow:
#   1. Ensure the pinned RealiTLScanner binary exists at $TOOL_CACHE.
#      On Linux: download the prebuilt v0.2.1 asset, verify sha256.
#      On macOS: build from source via `go install` at the same tag.
#   2. Run a scan against $SEEDS (file with CIDRs/IPs/domains, one per line)
#      or against the seed flags below. RealiTLScanner already filters for
#      TLS 1.3 + ALPN h2.
#   3. Post-filter the CSV: drop the over-template list (cloudflare.com,
#      microsoft.com, apple.com, google.com, discord.com); drop the "Avoid"
#      ASN tier from docs/PROVIDER-NOTES.md when GEO_CODE is missing — IP
#      ASN is checked separately via whois.cymru.com for the top candidates.
#   4. Print the top candidates with ASN + ALPN + CN + issuer columns.
#   5. Optional: feed the top result back through validate-reality-target.sh
#      for the full 9-step audit.
#
# Usage:
#   scripts/scan-reality-targets.sh --seeds my-seeds.txt
#   scripts/scan-reality-targets.sh --cidr 107.172.103.0/24
#   scripts/scan-reality-targets.sh --crawl https://launchpad.net/ubuntu/+archivemirrors
#   scripts/scan-reality-targets.sh --seeds seeds.txt --threads 20 --timeout 5
#   scripts/scan-reality-targets.sh --seeds seeds.txt --top 5 --validate
#
# Environment:
#   TOOL_CACHE   override the binary location (default ~/.cache/vpn-deploy)
#   VPS_ASN      if exported, candidates whose ASN does not match get
#                demoted (re-uses validate-reality-target.sh's heuristic).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOL_CACHE="${TOOL_CACHE:-${HOME}/.cache/vpn-deploy}"
mkdir -p "$TOOL_CACHE"

REALI_VERSION="v0.2.1"
REALI_LINUX_SHA256="3127c612c98ded9b07612ab8500a110a379cc0ab4342174ee026d913961fe834"
REALI_LINUX_URL="https://github.com/XTLS/RealiTLScanner/releases/download/${REALI_VERSION}/RealiTLScanner-linux-64"
REALI_BIN="${TOOL_CACHE}/RealiTLScanner-${REALI_VERSION}"

# Over-template list — repository-owned REALITY target heuristic. Keep it in
# sync with validate-reality-target.sh and docs/PROVIDER-NOTES.md.
OVERUSED_RE='^(([a-zA-Z0-9_-]+\.)+)?(cloudflare\.com|microsoft\.com|apple\.com|google\.com|discord\.com|icloud\.com)$'

# ASN tier blocklist (see docs/PROVIDER-NOTES.md).
AVOID_ASNS=(13335 16276 24940 14061 26383 216071)

usage() {
  sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Arg parse
# ---------------------------------------------------------------------------
SEEDS=""; CIDR=""; CRAWL=""; THREADS=10; TIMEOUT=5; TOP=5; VALIDATE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --seeds)    SEEDS="$2"; shift 2 ;;
    --cidr)     CIDR="$2"; shift 2 ;;
    --crawl)    CRAWL="$2"; shift 2 ;;
    --threads)  THREADS="$2"; shift 2 ;;
    --timeout)  TIMEOUT="$2"; shift 2 ;;
    --top)      TOP="$2"; shift 2 ;;
    --validate) VALIDATE=1; shift ;;
    -h|--help)  usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

if [[ -z "$SEEDS" && -z "$CIDR" && -z "$CRAWL" ]]; then
  echo "error: pick one of --seeds <file>, --cidr <range>, --crawl <url>" >&2
  usage
fi

# ---------------------------------------------------------------------------
# Ensure binary
# ---------------------------------------------------------------------------
install_reali() {
  if [[ -x "$REALI_BIN" ]]; then return; fi

  local uname_s
  uname_s="$(uname -s)"
  if [[ "$uname_s" == "Linux" ]]; then
    echo "fetching RealiTLScanner ${REALI_VERSION} (Linux amd64)" >&2
    curl -fsSL --retry 3 -o "${REALI_BIN}.tmp" "$REALI_LINUX_URL"
    local got
    got="$(shasum -a 256 "${REALI_BIN}.tmp" | awk '{print $1}')"
    if [[ "$got" != "$REALI_LINUX_SHA256" ]]; then
      rm -f "${REALI_BIN}.tmp"
      echo "sha256 mismatch for RealiTLScanner ${REALI_VERSION}" >&2
      echo "  expected: $REALI_LINUX_SHA256" >&2
      echo "  got:      $got" >&2
      exit 1
    fi
    mv "${REALI_BIN}.tmp" "$REALI_BIN"
    chmod 0755 "$REALI_BIN"
  elif [[ "$uname_s" == "Darwin" ]]; then
    if ! command -v go >/dev/null 2>&1; then
      echo "macOS has no prebuilt RealiTLScanner binary; install Go and retry." >&2
      echo "  brew install go" >&2
      exit 1
    fi
    echo "building RealiTLScanner ${REALI_VERSION} via go install (macOS)" >&2
    GOBIN="$TOOL_CACHE" go install "github.com/XTLS/RealiTLScanner@${REALI_VERSION}"
    mv "${TOOL_CACHE}/RealiTLScanner" "$REALI_BIN"
  else
    echo "unsupported OS: $uname_s" >&2
    exit 1
  fi
  echo "installed: $REALI_BIN" >&2
}

install_reali

# ---------------------------------------------------------------------------
# Run scan
# ---------------------------------------------------------------------------
WORK="$(mktemp -d -t vpn-reali.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
OUT_CSV="${WORK}/scan.csv"

run_args=(-thread "$THREADS" -timeout "$TIMEOUT" -out "$OUT_CSV")
if [[ -n "$SEEDS" ]]; then
  run_args+=(-in "$SEEDS")
elif [[ -n "$CIDR" ]]; then
  run_args+=(-addr "$CIDR")
elif [[ -n "$CRAWL" ]]; then
  run_args+=(-url "$CRAWL")
fi
echo ">>> $REALI_BIN ${run_args[*]}" >&2
"$REALI_BIN" "${run_args[@]}" >&2 || {
  echo "RealiTLScanner exited non-zero (some scanners always do at end)" >&2
}

if [[ ! -s "$OUT_CSV" ]]; then
  echo "no candidates produced — scanner output empty" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Post-filter — CSV header is IP,ORIGIN,CERT_DOMAIN,CERT_ISSUER,GEO_CODE
# ---------------------------------------------------------------------------
filtered="${WORK}/filtered.csv"
{
  head -1 "$OUT_CSV"
  tail -n +2 "$OUT_CSV" | awk -F',' -v overused="$OVERUSED_RE" '
    {
      cert = $3
      gsub(/"/, "", cert)
      sub(/^\*\./, "", cert)
      if (cert !~ overused) print
    }'
} > "$filtered"

candidates_n=$(($(wc -l < "$filtered") - 1))
echo "candidates after over-template filter: $candidates_n / $(($(wc -l < "$OUT_CSV") - 1))" >&2

# ---------------------------------------------------------------------------
# ASN annotate + AVOID-tier demote (top N only — whois is slow)
# ---------------------------------------------------------------------------
echo
printf '%-18s %-30s %-30s %-8s %-7s %s\n' \
  IP CERT_DOMAIN CERT_ISSUER GEO ASN STATUS
printf '%s\n' "---------------------------------------------------------------------------------------------------"

i=0
while IFS=, read -r ip origin cert issuer geo && (( i < TOP )); do
  cert_clean="${cert//\"/}"
  issuer_clean="${issuer//\"/}"
  geo_clean="${geo//\"/}"
  asn=""
  status=ok
  asn_line="$(whois -h whois.cymru.com " -v $ip" 2>/dev/null | tail -1 || true)"
  if [[ -n "$asn_line" ]] && ! echo "$asn_line" | grep -qiE '^bulk|^error|<html'; then
    asn="$(echo "$asn_line" | awk -F'|' '{gsub(/^ +| +$/,"",$1); print $1}')"
  fi
  if [[ -n "$asn" ]]; then
    for bad in "${AVOID_ASNS[@]}"; do
      [[ "$asn" == "$bad" ]] && status="AVOID-ASN"
    done
    if [[ -n "${VPS_ASN:-}" && "$asn" != "$VPS_ASN" && "$status" == "ok" ]]; then
      status="ASN-mismatch"
    fi
  fi
  printf '%-18s %-30s %-30s %-8s %-7s %s\n' \
    "$ip" "${cert_clean:0:30}" "${issuer_clean:0:30}" \
    "${geo_clean:0:8}" "AS${asn:--}" "$status"
  if [[ $i -eq 0 ]]; then
    top_host="${origin:-$cert_clean}"
    top_host_clean="${top_host//\"/}"
  fi
  i=$((i+1))
done < <(tail -n +2 "$filtered")

# ---------------------------------------------------------------------------
# Optional: full 9-step audit on the top candidate
# ---------------------------------------------------------------------------
if [[ "$VALIDATE" == 1 && -n "${top_host_clean:-}" ]]; then
  echo
  echo ">>> validating top candidate via validate-reality-target.sh: $top_host_clean"
  TARGET="${top_host_clean}:443" SERVER_NAMES="$top_host_clean" \
    "${REPO_ROOT}/scripts/validate-reality-target.sh" || true
fi

echo
echo "full CSV at ${OUT_CSV} (will be cleaned on exit)"
cp "$OUT_CSV" "${TOOL_CACHE}/last-scan.csv"
echo "persisted copy: ${TOOL_CACHE}/last-scan.csv"
