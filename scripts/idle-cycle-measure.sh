#!/usr/bin/env bash
# Idle-cycle measurement driver. Issues a TLS handshake against a bare-
# HTTPS endpoint after each idle duration in a configurable schedule
# and records the handshake latency. Output is a single JSON file per
# run keyed by ISO timestamp + the vantage label the operator supplies.
#
# Designed to surface a per-cycle latency pattern: if a filtering
# pipeline blocks the first access after a long idle and admits
# subsequent accesses inside a short window, the first-cycle latency
# is markedly larger than the immediate-followup latency, and the
# block re-applies as the idle gap grows.
#
# Run from the filtered-residential vantage. The server side carries
# its own SYN + TLS access logs that the correlation tool stitches in
# offline — see scripts/idle-cycle-server-correlate.py.
#
# Usage:
#   idle-cycle-measure.sh \
#     --target host.example.com:443 \
#     --sni '*.stackoverflow.com' \
#     --vantage 'residential-vantage-1' \
#     [--schedule 5m,30m,60m,4h,24h] \
#     [--followup-count 3] \
#     [--output ./idle-cycle-<timestamp>.json]

set -euo pipefail

# Portable bounded-run wrapper. macOS lacks `timeout` (coreutils ships it as
# `gtimeout`); use that, or run without a limit if neither is present. On Linux
# this resolves to `timeout`, so behaviour there is unchanged.
run_timeout() {
  local secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$secs" "$@"
  else
    "$@"
  fi
}

TARGET=""
SNI=""
VANTAGE=""
SCHEDULE="5m,30m,60m,4h,24h"
FOLLOWUP_COUNT=3
OUTPUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)         TARGET="$2";         shift 2 ;;
    --sni)            SNI="$2";            shift 2 ;;
    --vantage)        VANTAGE="$2";        shift 2 ;;
    --schedule)       SCHEDULE="$2";       shift 2 ;;
    --followup-count) FOLLOWUP_COUNT="$2"; shift 2 ;;
    --output)         OUTPUT="$2";         shift 2 ;;
    -h|--help)
      sed -n '1,/^set -euo/p' "$0" | sed '/^set -euo/d; s/^# \?//'
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -z "$TARGET"  ]] && { echo "missing --target"  >&2; exit 2; }
[[ -z "$SNI"     ]] && { echo "missing --sni"     >&2; exit 2; }
[[ -z "$VANTAGE" ]] && { echo "missing --vantage" >&2; exit 2; }

for tool in openssl jq python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing: $tool" >&2; exit 1; }
done

# Reject vantage labels that smuggle in carrier / ISP / operator /
# geographic identifiers. See root CLAUDE.md hard rules — pilot reports
# get cross-linked into the repo, and the vantage label propagates
# verbatim through the JSON output and the report template.
case "$(echo "$VANTAGE" | tr '[:upper:]' '[:lower:]')" in
  *rostelecom*|*beeline*|*megafon*|*mts*|*yandex*|*hetzner*|*ovh*|*digitalocean*)
    echo "vantage label '$VANTAGE' contains a carrier/operator identifier — describe by technical signature instead (see CLAUDE.md hard rules)" >&2
    exit 2 ;;
  *)
    ;;
esac

if [[ -z "$OUTPUT" ]]; then
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  OUTPUT="./idle-cycle-${ts}.json"
fi

# ---------------------------------------------------------------------------
# Duration parser — same NN{s,m,h,d} grammar as vpnd probe-matrix so
# operators can copy/paste schedules between the two tools.
# ---------------------------------------------------------------------------
parse_seconds() {
  local s="$1"
  local n="${s%[a-zA-Z]*}"
  local u="${s#"$n"}"
  case "$u" in
    s|"")  echo "$n" ;;
    m)     echo $(( n * 60 )) ;;
    h)     echo $(( n * 3600 )) ;;
    d)     echo $(( n * 86400 )) ;;
    *)     echo "unknown duration unit: '$u'" >&2; return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# Single-handshake probe. Records pre-connect timestamp + handshake
# elapsed ms. Exits non-zero only on a hard parse error; failed
# handshakes are recorded as `verdict: "failed"`.
# ---------------------------------------------------------------------------
probe() {
  local target="$1"
  local sni="$2"
  local host="${target%:*}"
  local port="${target#*:}"
  local pre_ms post_ms elapsed verdict err
  pre_ms="$(date +%s%3N)"
  if err="$(run_timeout 30 openssl s_client \
      -connect "$host:$port" -servername "$sni" \
      -verify_quiet -brief -no_ign_eof < /dev/null 2>&1)"; then
    verdict="ok"
  else
    verdict="failed"
  fi
  post_ms="$(date +%s%3N)"
  elapsed=$(( post_ms - pre_ms ))
  jq -nc \
    --arg sni "$sni" \
    --arg verdict "$verdict" \
    --argjson pre_ms "$pre_ms" \
    --argjson post_ms "$post_ms" \
    --argjson elapsed_ms "$elapsed" \
    --arg err "$err" \
    '{sni: $sni, verdict: $verdict, pre_ms: $pre_ms, post_ms: $post_ms, elapsed_ms: $elapsed_ms, error: $err}'
}

# ---------------------------------------------------------------------------
# Schedule walker. For each idle duration in the schedule:
#   1. Sleep for the duration.
#   2. Do one cold probe (the "first attempt after idle").
#   3. Do N follow-up probes immediately after.
# Records each as one record with `cycle_idx` + `attempt_idx`.
# ---------------------------------------------------------------------------
RESULTS='[]'
IFS=',' read -r -a schedule_arr <<< "$SCHEDULE"
START_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

for cycle_idx in "${!schedule_arr[@]}"; do
  raw="${schedule_arr[$cycle_idx]}"
  secs="$(parse_seconds "$raw")" || exit 1

  echo "cycle $cycle_idx: sleeping $raw ($secs s) before cold probe ..." >&2
  sleep "$secs"

  cold="$(probe "$TARGET" "$SNI")"
  cold="$(jq -c --argjson cycle "$cycle_idx" --arg dur "$raw" \
            '. + {cycle_idx: $cycle, idle_duration: $dur, attempt_idx: 0, attempt_kind: "cold"}' \
            <<< "$cold")"
  RESULTS="$(jq --argjson r "$cold" '. += [$r]' <<< "$RESULTS")"

  for f in $(seq 1 "$FOLLOWUP_COUNT"); do
    fu="$(probe "$TARGET" "$SNI")"
    fu="$(jq -c --argjson cycle "$cycle_idx" --arg dur "$raw" --argjson f "$f" \
            '. + {cycle_idx: $cycle, idle_duration: $dur, attempt_idx: $f, attempt_kind: "followup"}' \
            <<< "$fu")"
    RESULTS="$(jq --argjson r "$fu" '. += [$r]' <<< "$RESULTS")"
  done
done

END_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

REPORT="$(jq -n \
  --arg schema_version 1 \
  --arg target "$TARGET" \
  --arg sni "$SNI" \
  --arg vantage "$VANTAGE" \
  --arg schedule "$SCHEDULE" \
  --argjson followups "$FOLLOWUP_COUNT" \
  --arg start_ts "$START_TS" \
  --arg end_ts "$END_TS" \
  --argjson results "$RESULTS" '
  {
    schema_version: ($schema_version | tonumber),
    target: $target,
    sni: $sni,
    vantage: $vantage,
    schedule: $schedule,
    followup_count: $followups,
    started_at: $start_ts,
    finished_at: $end_ts,
    results: $results,
    summary: {
      cycles: (
        [$results[] | select(.attempt_kind == "cold")]
        | map({
            cycle_idx: .cycle_idx,
            idle_duration: .idle_duration,
            cold_ms: .elapsed_ms,
            cold_verdict: .verdict
          })
      ),
      followup_median_ms_by_cycle: (
        [$results[] | select(.attempt_kind == "followup")]
        | group_by(.cycle_idx)
        | map({
            cycle_idx: .[0].cycle_idx,
            median_ms: (sort_by(.elapsed_ms) | .[length / 2 | floor] | .elapsed_ms)
          })
      )
    }
  }')"

printf '%s\n' "$REPORT" > "$OUTPUT"
echo "wrote $OUTPUT" >&2

# Print the per-cycle summary on stdout so an operator running this
# from a tmux pane sees the pattern emerge in real time.
jq -r '
  "idle-cycle measurement summary (\(.vantage) -> \(.target)):" ,
  (
    .summary.cycles
    | map(
        "  cycle \(.cycle_idx) (\(.idle_duration) idle): cold = \(.cold_ms) ms (\(.cold_verdict))"
      )
    | .[]
  )
' "$OUTPUT"
