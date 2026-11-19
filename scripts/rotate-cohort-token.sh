#!/usr/bin/env bash
# Generate or rotate the shared field-report cohort token in the SOPS file.
# The old token stays accepted by the ingest as previous_cohort_token until
# previous_cohort_token_valid_until (now + OVERLAP_DAYS). A second rotation
# while that overlap is still open would cut off devices that hold the older
# token, so it is refused unless FORCE=1. No token value is printed or
# logged. Afterwards deploy the subscription host and export fresh bundles.
set -euo pipefail
umask 077

ENV="${ENV:-prod}"
PROVIDER="${PROVIDER:-upcloud}"
OVERLAP_DAYS="${OVERLAP_DAYS:-7}"
FORCE="${FORCE:-0}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOPS_FILE="${SOPS_FILE:-${HOME}/.config/vpn-provision/${ENV}.secrets.sops.yaml}"
SOPS_FILE="$(SOPS_FILE="$SOPS_FILE" python3 -c 'import os; print(os.path.realpath(os.environ["SOPS_FILE"]))')"

if [[ ! "$OVERLAP_DAYS" =~ ^[1-9][0-9]?$ ]] || (( OVERLAP_DAYS > 30 )); then
  echo 'error: OVERLAP_DAYS must be an integer from 1 to 30' >&2
  exit 2
fi
if [[ "$FORCE" != 0 && "$FORCE" != 1 ]]; then
  echo 'error: FORCE must be 0 or 1' >&2
  exit 2
fi
if [[ ! -f "$SOPS_FILE" ]]; then
  echo "missing SOPS file: $SOPS_FILE" >&2
  exit 1
fi

# The project-wide writer lock shared with rotate-secrets, new-client and token issuance.
SOPS_LOCK="${SOPS_FILE}.new-client.lock"
[[ ! -L "$SOPS_LOCK" ]] || { echo 'unsafe secrets writer lock' >&2; exit 1; }
exec 9<> "$SOPS_LOCK"
if ! python3 "$REPO_ROOT/scripts/private-operator-lock.py" "$SOPS_LOCK" 9; then
  echo 'error: another secrets transaction is active or its lock is unsafe' >&2
  exit 1
fi

# Same backup contract as rotate-secrets.sh: three sops set calls change the
# file, and any failure or interrupt restores the copy taken here.
for stale in "${SOPS_FILE}".rotate.*; do
  [[ ! -e "$stale" ]] || {
    echo "error: a killed rotation left ${stale}; it holds the file from before that run. Compare it with ${SOPS_FILE}, keep the right one, remove the copy and run again" >&2
    exit 1
  }
done
backup="$(mktemp "${SOPS_FILE}.rotate.XXXXXX")"
cp -p -- "$SOPS_FILE" "$backup"
restore() {
  [[ ! -e "$backup" ]] || mv -f -- "$backup" "$SOPS_FILE"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Values travel through pipes only, never argv, the environment or output.
current="$(sops --decrypt --output-type json "$SOPS_FILE" | FORCE="$FORCE" python3 -c '
import datetime, json, os, re, sys
field_report = json.load(sys.stdin).get("field_report") or {}
token = field_report.get("cohort_token", "")
if token and not re.fullmatch(r"[A-Za-z0-9_-]{22,64}", token):
    sys.exit("error: the current cohort token is malformed; fix it before rotating")
until = field_report.get("previous_cohort_token_valid_until")
if field_report.get("previous_cohort_token") and os.environ["FORCE"] != "1":
    try:
        end = datetime.datetime.fromisoformat(str(until).replace("Z", "+00:00"))
        open_overlap = end.tzinfo is None or end > datetime.datetime.now(datetime.timezone.utc)
    except ValueError:
        open_overlap = True
    if open_overlap:
        sys.exit("error: the previous cohort token is still accepted until " + re.sub(r"[^0-9TZ:-]", "?", str(until))
                 + "; rotating now cuts off devices that hold it. Wait for the overlap to end or run again with FORCE=1")
print(token)')"

set_key() {
  python3 -c 'import json, sys; print(json.dumps(sys.stdin.read()))' | sops set --value-stdin "$SOPS_FILE" "[\"field_report\"][\"$1\"]"
}

until_instant="$(python3 -c '
import datetime, sys
end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=int(sys.argv[1]))
print(end.strftime("%Y-%m-%dT%H:%M:%SZ"))' "$OVERLAP_DAYS")"

rotated=false
if [[ -n "$current" ]]; then
  printf '%s' "$current" | set_key previous_cohort_token
  printf '%s' "$until_instant" | set_key previous_cohort_token_valid_until
  rotated=true
fi
python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' | set_key cohort_token
unset current
rm -f -- "$backup"

if [[ "$rotated" == true ]]; then
  echo "rotated the field-report cohort token; the previous token is accepted until ${until_instant}"
else
  echo "generated the field-report cohort token"
fi
echo "next: deploy the subscription host, then export fresh bundles"

ENV="$ENV" PROVIDER="$PROVIDER" \
  "${REPO_ROOT}/scripts/audit-log.sh" append-best-effort \
    --action rotate-cohort-token \
    --note "sops_file=${SOPS_FILE##*/}"
