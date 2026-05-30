#!/usr/bin/env bash
# Per-ASN payload-size throttling probe. Some transit paths apply a
# silent rate/throughput penalty once a single response body crosses a
# size threshold near ~16 KiB — small requests clear cleanly, larger
# ones stall, time out, or have their RTT inflated. This script drives
# an escalating ladder of payload sizes against an operator-supplied
# endpoint, measures per-size completion + RTT, and classifies the
# path's behaviour by the OBSERVED SIGNATURE (size threshold, RTT
# spike, completion cliff) keyed to the target ASN — never to a carrier
# or geographic name (root CLAUDE.md hard rule).
#
# Run from a client network you care about — NOT from the VPS itself,
# exactly like scripts/test-tls-policing.sh. A common pattern is to ssh
# into a low-cost box inside the cohort's path and run this against an
# operator-controlled echo/download endpoint.
#
# Contract: emit exactly one JSON object on stdout matching the project
# probe schema —
#   {"verdict": "ok|throttled|blocked|unknown|error", "rtt_ms": <int|null>}
# with an "asn" field keyed to AS<num>, a "threshold_bytes" signature,
# and a per-size "sizes" breakdown. "error_kind" is populated only when
# verdict == error. All diagnostic noise goes to stderr; a non-zero exit
# is interpreted by orchestrators as error.
#
# Usage:
#   scripts/probe-payload-throttle.sh --host endpoint.example.com
#   scripts/probe-payload-throttle.sh --host 1.2.3.4 --port 443 \
#       --sizes 1024,4096,8192,16384,24576,32768
#   scripts/probe-payload-throttle.sh --host h --asn AS64500   # skip lookup
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

HOST=""
PORT=443
# Escalating ladder straddling the ~16 KiB step. Small sizes establish
# the baseline; the >=16384 steps are the throttle-detection window.
SIZES="1024,4096,8192,16384,24576,32768"
SCHEME="https"
# Operator endpoint path that echoes/serves a body of the requested
# size. The byte count is appended as the query value "bytes".
ECHO_PATH="/__throttle_probe"
TIMEOUT=15
ASN_OVERRIDE=""
NO_STATE=0
# A size step counts as a completion cliff if its completion fraction
# drops below this relative to the small-payload baseline.
CLIFF_FRACTION=70   # percent
# A size step counts as an RTT spike if its P50 exceeds the baseline
# P50 by this multiple.
SPIKE_FACTOR=3      # integer multiple

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d' >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)       HOST="$2"; shift 2 ;;
    --port)       PORT="$2"; shift 2 ;;
    --sizes)      SIZES="$2"; shift 2 ;;
    --scheme)     SCHEME="$2"; shift 2 ;;
    --echo-path)  ECHO_PATH="$2"; shift 2 ;;
    --timeout)    TIMEOUT="$2"; shift 2 ;;
    --asn)        ASN_OVERRIDE="$2"; shift 2 ;;
    --no-state)   NO_STATE=1; shift ;;
    -h|--help)    usage; exit 1 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

emit_error() {
  # $1 = error_kind string
  local kind="$1"
  printf '{"verdict": "error", "rtt_ms": null, "error_kind": "%s"}\n' "$kind"
  exit 0
}

[[ -n "$HOST" ]] || { echo "--host required" >&2; emit_error "missing host"; }

for tool in curl python3; do
  command -v "$tool" >/dev/null 2>&1 || emit_error "missing tool: $tool"
done

# --- ASN resolution (technical key only; ORG/COUNTRY never propagated) ---
asn="$ASN_OVERRIDE"
prefix=""
if [[ -z "$asn" ]]; then
  command -v whois >/dev/null 2>&1 || emit_error "missing tool: whois"
  # probe-asn.sh prints: IP \t ASN \t PREFIX \t COUNTRY \t ORG
  if ! asn_line="$("${REPO_ROOT}/scripts/probe-asn.sh" "$HOST" 2>/dev/null)"; then
    emit_error "asn lookup failed"
  fi
  asn="$(printf '%s' "$asn_line" | awk -F'\t' '{print $2}')"
  prefix="$(printf '%s' "$asn_line" | awk -F'\t' '{print $3}')"
  [[ -n "$asn" ]] || emit_error "asn lookup empty"
  asn="AS${asn}"
fi
# Normalise an operator-supplied override that may already carry "AS".
case "$asn" in AS*) ;; *) asn="AS${asn}" ;; esac

WORK="$(mktemp -d -t payload-throttle.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

now_ms() { python3 -c 'import time; print(int(time.time()*1000))'; }

# Drive one request that forces ~N bytes of response body and record
# "<size>,<ok>,<ms>" to the per-size result file. ok=1 on a clean
# completion, ok=0 on timeout/reset/non-2xx.
one_request() {
  local size="$1"
  local out="${WORK}/body-${size}"
  local url t0 t1 ms ok=0
  # printf '%q' so an operator-supplied host can never break out of the
  # URL; the size is integer-validated below before reaching here.
  url="$(printf '%s://%s:%s%s?bytes=%s' \
    "$SCHEME" "$HOST" "$PORT" "$ECHO_PATH" "$size")"
  t0="$(now_ms)"
  if curl -fsS --max-time "$TIMEOUT" \
        --output "$out" \
        "$url" >/dev/null 2>&1; then
    ok=1
  fi
  t1="$(now_ms)"
  ms=$(( t1 - t0 ))
  printf '%s,%s,%s\n' "$size" "$ok" "$ms" > "${WORK}/r-${size}"
}

# Validate + walk the ladder.
IFS=',' read -r -a size_list <<< "$SIZES"
for s in "${size_list[@]}"; do
  [[ "$s" =~ ^[0-9]+$ ]] || emit_error "non-integer size: $s"
  one_request "$s"
done

# Aggregate the per-size results and classify in python3. The detection
# logic lives here so the median/threshold arithmetic is robust:
#   baseline  = small sizes (< 16384)
#   suspect   = sizes >= 16384
#   blocked   = no size completed at all
#   ok        = all sizes completed and no suspect-step RTT spike
#   throttled = baseline mostly completes but a suspect step shows a
#               completion cliff OR a P50 RTT spike
#   unknown   = indeterminate (e.g. no baseline samples to compare)
RESULTS="${WORK}/results.csv"
cat "${WORK}"/r-* > "$RESULTS" 2>/dev/null || true
verdict_json="$(
  ASN="$asn" PREFIX="$prefix" RESULTS_FILE="$RESULTS" \
    CLIFF_FRACTION="$CLIFF_FRACTION" SPIKE_FACTOR="$SPIKE_FACTOR" \
    python3 - <<'PY'
import json, os, statistics, sys

THRESHOLD = 16384
cliff_frac = int(os.environ["CLIFF_FRACTION"])
spike_factor = int(os.environ["SPIKE_FACTOR"])
asn = os.environ.get("ASN", "")
prefix = os.environ.get("PREFIX", "")

rows = []
try:
    with open(os.environ["RESULTS_FILE"], encoding="ascii") as fh:
        raw = fh.read()
except OSError:
    raw = ""
for line in raw.splitlines():
    line = line.strip()
    if not line:
        continue
    size_s, ok_s, ms_s = line.split(",")
    rows.append((int(size_s), int(ok_s), int(ms_s)))
rows.sort(key=lambda r: r[0])

sizes_out = []
for size, ok, ms in rows:
    sizes_out.append({
        "bytes": size,
        "completed": bool(ok),
        "rtt_ms": ms if ok else None,
    })

def out(verdict, rtt_ms, threshold=None, error_kind=None):
    obj = {"verdict": verdict, "rtt_ms": rtt_ms}
    obj["asn"] = asn
    if prefix:
        obj["prefix"] = prefix
    obj["threshold_bytes"] = threshold
    obj["sizes"] = sizes_out
    if error_kind is not None:
        obj["error_kind"] = error_kind
    print(json.dumps(obj, separators=(",", ":"), sort_keys=True))

if not rows:
    out("unknown", None)
    sys.exit(0)

baseline = [r for r in rows if r[0] < THRESHOLD]
suspect = [r for r in rows if r[0] >= THRESHOLD]

any_ok = any(r[1] for r in rows)
# Representative RTT: median of all completed steps, or null.
ok_ms = [r[2] for r in rows if r[1]]
rep_rtt = int(statistics.median(ok_ms)) if ok_ms else None

# No completion at any size → the path is dropping the connection
# outright, not selectively throttling by payload size.
if not any_ok:
    out("blocked", None)
    sys.exit(0)

# Need a usable baseline to make a relative throttle judgement.
if not baseline:
    out("unknown", rep_rtt)
    sys.exit(0)

base_ok = [r for r in baseline if r[1]]
base_completion = 100 * len(base_ok) // len(baseline)
base_ms = [r[2] for r in base_ok]
base_p50 = statistics.median(base_ms) if base_ms else None

# If even the small payloads can't clear, the signal is ambiguous
# (connectivity problem, not size throttling).
if base_completion < cliff_frac:
    out("unknown", rep_rtt)
    sys.exit(0)

# Examine each suspect (>=16 KiB) step for a completion cliff or an
# RTT spike relative to the small-payload baseline.
throttle_threshold = None
for size, ok, ms in suspect:
    if ok == 0:
        throttle_threshold = size
        break
    if base_p50 is not None and base_p50 > 0 and ms >= spike_factor * base_p50:
        throttle_threshold = size
        break

if throttle_threshold is not None:
    out("throttled", rep_rtt, threshold=throttle_threshold)
else:
    out("ok", rep_rtt)
PY
)"

# Guard: if the python classifier produced nothing, surface unknown
# rather than an empty stdout the orchestrator would read as error.
if [[ -z "$verdict_json" ]]; then
  printf '{"verdict": "unknown", "rtt_ms": null}\n'
  exit 0
fi

# --- Optional atomic state persistence, keyed by AS<num> only ---------
if (( ! NO_STATE )); then
  STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/vpn-deploy/payload-throttle"
  if mkdir -p "$STATE_DIR" 2>/dev/null; then
    state_file="${STATE_DIR}/${asn}.json"
    tmp_state="$(mktemp -t payload-throttle-state.XXXXXX)"
    printf '%s\n' "$verdict_json" > "$tmp_state"
    chmod 0600 "$tmp_state"
    mv -f "$tmp_state" "$state_file"
  fi
fi

printf '%s\n' "$verdict_json"
