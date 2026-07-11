#!/usr/bin/env bash
# SNI-variant TSPU-survival probe for REALITY target selection.
#
# For each REALITY server_name, probes BOTH the bare and the `www.`-prefixed
# SNI variant against the exit IP with a TLS ClientHello and records which
# variant survives. Repository-local filtered-vantage measurements show that
# TSPU on several non-CF
# paths matches the SNI by EXACT dot-component string, not by suffix: the bare
# `foo.com` and `www.foo.com` forms of the same name can have very different
# survival, in either direction. The "topologically equivalent" variants are
# NOT equivalent to the classifier.
#
# CRITICAL — VANTAGE MATTERS. The asymmetry is observable ONLY from inside an
# RU TSPU path. Run this from the FILTERED vantage you want to characterise.
# From a non-RU / unfiltered vantage every variant will "survive" and the
# result is a reachability/hygiene baseline ONLY — never a survival verdict.
# The decision of which variant to put in `xray.server_names` MUST come from a
# filtered RU-vantage run of this probe (see docs/TRANSPORT-REACHABILITY-MATRIX.md).
#
# This is the survival counterpart to `scripts/validate-reality-target.sh`,
# which can only test TLS/cert hygiene locally and explicitly does NOT decide
# RU survival.
#
# Usage:
#   scripts/probe-sni-survival.sh <exit-ip> [options]
#
# Options / env:
#   --server-names "a.com b.com"   explicit SNI list (else SERVER_NAMES env,
#                                  else xray.server_names from --secrets)
#   --secrets <path>               decrypted secrets (JSON or YAML) to read
#                                  xray.server_names from
#   --out <path>                   write the JSON report here (else stdout only)
#   --port <n>                     TLS port (default 443)
#   --timeout <s>                  per-probe timeout seconds (default 8)
#   --vantage <label>             free-form vantage label recorded verbatim
#                                  (default: $VANTAGE or "unfiltered")
#
# Verdicts per variant:
#   survived — TLS ServerHello / certificate came back: the ClientHello reached
#              the endpoint and was answered. (From an RU vantage this means the
#              SNI string is NOT on the exact-match drop table for this path.)
#   blocked  — TCP connected but the TLS handshake was dropped past ClientHello
#              (reset / silent stall → timeout). The TSPU SNI-drop signature.
#   error    — could not even establish TCP (port closed / DNS) — not a TSPU
#              signal; the probe could not measure this variant.
set -euo pipefail

EXIT_IP="${1:-}"
[[ -n "$EXIT_IP" && "$EXIT_IP" != --* ]] || {
  echo "usage: $0 <exit-ip> [--server-names <list>] [--secrets <path>] [--out <path>] [--port <n>] [--timeout <s>] [--vantage <label>]" >&2
  exit 2
}
shift

SERVER_NAMES="${SERVER_NAMES:-}"
SECRETS=""
OUT=""
PORT=443
TIMEOUT=8
VANTAGE="${VANTAGE:-unfiltered}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-names) SERVER_NAMES="$2"; shift 2 ;;
    --secrets)      SECRETS="$2"; shift 2 ;;
    --out)          OUT="$2"; shift 2 ;;
    --port)         PORT="$2"; shift 2 ;;
    --timeout)      TIMEOUT="$2"; shift 2 ;;
    --vantage)      VANTAGE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

command -v openssl >/dev/null 2>&1 || { echo "missing: openssl" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "missing: python3" >&2; exit 1; }

# Portable bounded-runtime wrapper. The "blocked" classification depends on a
# silent in-path drop hitting a timeout, so a timeout tool is mandatory; macOS
# ships it as `gtimeout` (coreutils).
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_BIN="gtimeout"
else
  echo "missing: timeout (install coreutils; macOS provides 'gtimeout')" >&2
  exit 1
fi

# server_names resolution: explicit > env > secrets file.
if [[ -z "$SERVER_NAMES" ]]; then
  if [[ -n "$SECRETS" && -f "$SECRETS" ]]; then
    if command -v jq >/dev/null 2>&1 && jq -e . "$SECRETS" >/dev/null 2>&1; then
      SERVER_NAMES="$(jq -r '.xray.server_names | join(" ")' "$SECRETS")"
    else
      # YAML fallback via python (stdlib has no YAML; do a narrow grep parse
      # of the `server_names:` list to avoid a PyYAML dependency).
      SERVER_NAMES="$(python3 - "$SECRETS" <<'PY'
import sys, re
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'(?ms)^\s*server_names\s*:\s*(.*?)(?:^\S|\Z)', text)
names = []
if m:
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith("-"):
            names.append(line[1:].strip().strip('"\''))
print(" ".join(n for n in names if n))
PY
)"
    fi
  fi
fi

[[ -n "$SERVER_NAMES" ]] || { echo "no server_names: pass --server-names, set SERVER_NAMES, or give --secrets with xray.server_names" >&2; exit 1; }

echo "SNI-variant survival probe → ${EXIT_IP}:${PORT}  (vantage: ${VANTAGE})"
if [[ "$VANTAGE" == "unfiltered" ]]; then
  echo "NOTE: vantage=unfiltered — results are a reachability baseline, NOT an RU-survival verdict." >&2
fi

# Deduplicated (bare, www.) variants for a name. Strips a single leading www.
sni_variants() {
  local n="${1#www.}"
  printf '%s\n%s\n' "$n" "www.$n"
}

# Classify one SNI: echoes "survived" | "blocked" | "error".
classify_sni() {
  local sni="$1" out
  out="$("$TIMEOUT_BIN" "$TIMEOUT" openssl s_client \
          -connect "${EXIT_IP}:${PORT}" -servername "$sni" \
          -tls1_3 -alpn h2 </dev/null 2>&1 || true)"
  # A returned server certificate PEM is the ONLY reliable survival signal: it
  # is printed only when the endpoint completed enough of the TLS handshake to
  # send its certificate. Do NOT match `Verify return code:` or `SSL-Session:`
  # — openssl prints both in its trailer even on a fully failed handshake
  # (e.g. against a non-TLS port), which would be a false "survived".
  if printf '%s' "$out" | grep -q -- '-----BEGIN CERTIFICATE-----'; then
    echo "survived"
  elif printf '%s' "$out" | grep -q '^CONNECTED'; then
    echo "blocked"
  else
    echo "error"
  fi
}

# Collect TSV: server_name \t sni \t verdict
TSV="$(mktemp -t sni-survival.XXXXXX)"
trap 'rm -f "$TSV"' EXIT

for sn in $SERVER_NAMES; do
  sn_clean="${sn//,/}"
  [[ -z "$sn_clean" ]] && continue
  while IFS= read -r variant; do
    [[ -z "$variant" ]] && continue
    verdict="$(classify_sni "$variant")"
    printf '%s\t%s\t%s\n' "$sn_clean" "$variant" "$verdict" >> "$TSV"
    echo "  ${sn_clean}: ${variant} → ${verdict}"
  done < <(sni_variants "$sn_clean" | sort -u)
done

# Assemble the JSON report (python3 for safe quoting + structure).
REPORT="$(EXIT_IP="$EXIT_IP" PORT="$PORT" VANTAGE="$VANTAGE" python3 - "$TSV" <<'PY'
import json, os, sys, datetime

tsv = sys.argv[1]
rows = []
with open(tsv, encoding="utf-8") as fh:
    for line in fh:
        parts = line.rstrip("\n").split("\t")
        if len(parts) == 3:
            rows.append(parts)

by_name = {}
order = []
for sname, sni, verdict in rows:
    if sname not in by_name:
        by_name[sname] = {}
        order.append(sname)
    by_name[sname][sni] = verdict

results = []
for sname in order:
    variants = by_name[sname]
    survived = sorted(s for s, v in variants.items() if v == "survived")
    results.append({
        "server_name": sname,
        "variants": variants,
        "survived": survived,
    })

report = {
    "schema_version": 1,
    "vantage": os.environ["VANTAGE"],
    "exit_ip": os.environ["EXIT_IP"],
    "port": int(os.environ["PORT"]),
    "captured_at": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0).isoformat(),
    "results": results,
}
print(json.dumps(report, indent=2))
PY
)"

if [[ -n "$OUT" ]]; then
  printf '%s\n' "$REPORT" > "$OUT"
  echo "wrote $OUT"
else
  printf '%s\n' "$REPORT"
fi

# Operator guidance on asymmetry — only meaningful from a filtered vantage.
if [[ "$VANTAGE" != "unfiltered" ]]; then
  echo
  echo "Pick the SURVIVED variant for xray.server_names. If both survive, prefer"
  echo "the one already covered by the target certificate SAN (validate-reality-target.sh)."
  echo "If bare and www. disagree, that disagreement is the whole point — do not"
  echo "assume the 'canonical' form; use what survived from this vantage."
fi
