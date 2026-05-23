#!/usr/bin/env bash
# Deploy-side regression baseline. Runs `rkn-block-checker` against the
# canonical URL set (21 whitelist controls + 15 blacklist tests) and
# diffs the verdicts against the previous run for the same exit IP.
#
# Usage:
#   scripts/run-rkn-block-checker.sh <exit-ip> [--proxy <socks5-url>]
#                                    [--url-set <path>]
#                                    [--state-dir <path>]
#                                    [--no-archive]
#
# Layered verdict taxonomy (per upstream):
#   DNS_BLOCK   — resolver returned a stub / no answer / loopback
#   TCP_RESET   — TCP handshake completed then RST mid-flow
#   TLS_BLOCK   — TLS ClientHello terminated (RST, FIN, or stall)
#   HTTP_STUB   — TLS handshake completed, HTTP body is a censorship stub
#   OK          — every layer reached the origin
#
# JSON contract assumed (per --json output of rkn-block-checker):
#   {
#     "url": "https://...",
#     "verdicts": { "dns": "...", "tcp": "...", "tls": "...", "http": "..." },
#     "elapsed_ms": <int>
#   }
# If upstream cuts a release with a different shape, the wrapper's
# `assemble_report` step will fail loud. Bump RKN_BLOCK_CHECKER_VERSION
# in lockstep with any breaking schema change.
#
# Install once per operator workstation:
#   pipx install rkn-block-checker==${RKN_BLOCK_CHECKER_VERSION}
# (or: pip install --user rkn-block-checker==${RKN_BLOCK_CHECKER_VERSION})

set -euo pipefail

RKN_BLOCK_CHECKER_VERSION="${RKN_BLOCK_CHECKER_VERSION:-0.1.0}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_URL_SET="${REPO_ROOT}/scripts/rkn-block-checker-url-set.yaml"
DEFAULT_STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/vpn-deploy/rkn-baseline"

usage() {
  cat >&2 <<'EOF'
usage: run-rkn-block-checker.sh <exit-ip> [--proxy <socks5-url>]
                                          [--url-set <path>]
                                          [--state-dir <path>]
                                          [--no-archive]
EOF
  exit 2
}

EXIT_IP="${1:-}"
[[ -z "$EXIT_IP" ]] && usage
shift

PROXY=""
URL_SET="$DEFAULT_URL_SET"
STATE_DIR="$DEFAULT_STATE_DIR"
ARCHIVE=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --proxy)     PROXY="$2";     shift 2 ;;
    --url-set)   URL_SET="$2";   shift 2 ;;
    --state-dir) STATE_DIR="$2"; shift 2 ;;
    --no-archive) ARCHIVE=0;     shift ;;
    -h|--help)   usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

for tool in jq python3 rkn-block-checker; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "missing: $tool" >&2
    if [[ "$tool" == "rkn-block-checker" ]]; then
      echo "install with: pipx install rkn-block-checker==${RKN_BLOCK_CHECKER_VERSION}" >&2
    fi
    exit 1
  fi
done

[[ -f "$URL_SET" ]] || { echo "missing URL set: $URL_SET" >&2; exit 1; }

mkdir -p "${STATE_DIR}/${EXIT_IP}/runs"
LATEST="${STATE_DIR}/${EXIT_IP}/latest.json"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE_PATH="${STATE_DIR}/${EXIT_IP}/runs/${TIMESTAMP}.json"

# ---------------------------------------------------------------------------
# Load URL set into a tab-separated stream (url <TAB> group <TAB> expected).
# ---------------------------------------------------------------------------
URL_STREAM="$(python3 - "$URL_SET" <<'PY'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as handle:
    data = yaml.safe_load(handle) or {}

for group in ("whitelist_controls", "blacklist_tests"):
    for entry in data.get(group) or []:
        url = entry.get("url", "")
        expected = entry.get("expected", "")
        if not url or not expected:
            continue
        print(f"{url}\t{group}\t{expected}")
PY
)"

if [[ -z "$URL_STREAM" ]]; then
  echo "URL set produced no entries: $URL_SET" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Run rkn-block-checker per URL. Aggregating one-shot calls is safer than
# relying on a --batch flag that may not exist in the pinned version.
# ---------------------------------------------------------------------------
RESULTS_JSON='[]'
while IFS=$'\t' read -r url group expected; do
  echo "probing $url …" >&2
  args=(rkn-block-checker --json "$url")
  [[ -n "$PROXY" ]] && args+=(--proxy "$PROXY")

  if ! verdict_json="$("${args[@]}" 2>/dev/null)"; then
    verdict_json='{"verdicts":{"dns":"ERROR","tcp":"ERROR","tls":"ERROR","http":"ERROR"},"elapsed_ms":0,"error":"tool exited non-zero"}'
  fi

  # Normalise into the contract shape; jq fails loud if the upstream
  # JSON is missing the verdicts block.
  norm_json="$(jq -e --arg url "$url" --arg group "$group" --arg expected "$expected" '
    {
      url: $url,
      group: $group,
      expected: $expected,
      verdicts: (.verdicts // (.verdict // null)),
      elapsed_ms: (.elapsed_ms // 0),
      error: (.error // null)
    }
    | if .verdicts == null then
        error("rkn-block-checker JSON missing .verdicts for " + $url)
      else . end
  ' <<< "$verdict_json")"

  RESULTS_JSON="$(jq --argjson r "$norm_json" '. += [$r]' <<< "$RESULTS_JSON")"
done <<< "$URL_STREAM"

# ---------------------------------------------------------------------------
# Roll up + write report.
# ---------------------------------------------------------------------------
REPORT="$(jq -n --arg exit_ip "$EXIT_IP" --arg ts "$TIMESTAMP" --arg proxy "$PROXY" \
            --argjson results "$RESULTS_JSON" '
  {
    schema_version: 1,
    exit_ip: $exit_ip,
    timestamp: $ts,
    proxy: (if $proxy == "" then null else $proxy end),
    results: $results,
    summary: {
      total:      ($results | length),
      ok:         ([$results[] | select(
                     (.verdicts.dns == "OK") and
                     (.verdicts.tcp == "OK") and
                     (.verdicts.tls == "OK") and
                     (.verdicts.http == "OK")
                   )] | length),
      whitelist:  ([$results[] | select(.group == "whitelist_controls")] | length),
      blacklist:  ([$results[] | select(.group == "blacklist_tests")] | length)
    }
  }
')"

if (( ARCHIVE == 1 )); then
  printf '%s\n' "$REPORT" > "$ARCHIVE_PATH"
fi

# ---------------------------------------------------------------------------
# Diff against previous LATEST.
# ---------------------------------------------------------------------------
if [[ -f "$LATEST" ]]; then
  DIFF="$(jq -n --argjson prev "$(cat "$LATEST")" --argjson curr "$REPORT" '
    def verdict_str:
      "dns=" + (.verdicts.dns // "?") +
      " tcp=" + (.verdicts.tcp // "?") +
      " tls=" + (.verdicts.tls // "?") +
      " http=" + (.verdicts.http // "?");
    def index(arr): arr | map({ key: .url, value: . }) | from_entries;

    ($prev.results | index($prev.results)) as $p
    | ($curr.results | index($curr.results)) as $c
    | [
        ($c | to_entries[] | .key as $u
          | if ($p | has($u)) then
              ($p[$u]) as $pv
              | ($c[$u]) as $cv
              | if ($pv.verdicts != $cv.verdicts) then
                  { url: $u, from: ($pv | verdict_str), to: ($cv | verdict_str) }
                else empty end
            else
              { url: $u, from: "(absent)", to: ($c[$u] | verdict_str) }
            end
        )
      ]
  ')"
  shift_count="$(jq 'length' <<< "$DIFF")"
else
  DIFF='[]'
  shift_count=0
fi

# Persist latest atomically.
printf '%s\n' "$REPORT" > "${LATEST}.tmp"
mv -f "${LATEST}.tmp" "$LATEST"

# ---------------------------------------------------------------------------
# Human-readable changelog to stdout.
# ---------------------------------------------------------------------------
{
  printf 'rkn-block-checker baseline %s (exit %s)\n' "$TIMESTAMP" "$EXIT_IP"
  jq -r '
    "  total: \(.summary.total)  ok-everywhere: \(.summary.ok)  whitelist: \(.summary.whitelist)  blacklist: \(.summary.blacklist)"
  ' <<< "$REPORT"
  if [[ -n "$PROXY" ]]; then
    printf '  proxy: %s\n' "$PROXY"
  fi
  printf '\n'
  if (( shift_count == 0 )); then
    printf 'no verdict shifts vs previous run\n'
  else
    printf 'verdict shifts (%d):\n' "$shift_count"
    jq -r '.[] | "  \(.url)\n    from: \(.from)\n    to:   \(.to)"' <<< "$DIFF"
  fi
} >&1

# Exit non-zero when verdict shifts occurred — wraps cleanly into CI.
(( shift_count == 0 ))
