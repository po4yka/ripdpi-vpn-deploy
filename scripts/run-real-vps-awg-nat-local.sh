#!/usr/bin/env bash
# Fixed-command local executor for the recurring real-VPS AWG/NAT evidence lane.
set -euo pipefail

[[ $# -eq 0 ]] || { echo "this fixed-command runner accepts no arguments" >&2; exit 2; }

: "${RUNTIME_DIRECTORY:?systemd must provide RUNTIME_DIRECTORY}"
: "${STATE_DIRECTORY:?systemd must provide STATE_DIRECTORY}"

REPO_ROOT="$(readlink -f "${RIPDPI_AWG_EVIDENCE_REPO_ROOT:-/opt/ripdpi-real-vps-awg-nat/current}")"
RUNNER="/usr/local/libexec/ripdpi-real-vps-awg-nat"
CONFIG="/etc/ripdpi/real-vps-awg-nat-local.json"
ENTRYPOINT="scripts/run-real-vps-awg-nat-local.sh"
LOCK_DIR="/run/lock/ripdpi-real-vps-awg-nat"

umask 077
for tool in awk cmp find flock git install python3 readlink sha256sum stat; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing prerequisite: $tool" >&2; exit 75; }
done
[[ -d "$LOCK_DIR" ]] || { echo "shared lane lock directory is missing" >&2; exit 75; }
[[ "$(stat -c '%u:%a' "$LOCK_DIR")" == "0:700" ]] || { echo "shared lane lock directory is unsafe" >&2; exit 75; }
exec 9>"$LOCK_DIR/lane.lock"
flock -n 9 || { echo "real-VPS AWG/NAT lane is already running or being installed" >&2; exit 75; }

evidence_dir="$STATE_DIRECTORY/evidence"
quarantine_dir="$STATE_DIRECTORY/quarantine"
install -d -m 0700 "$evidence_dir" "$quarantine_dir"
rm -f -- "$evidence_dir/latest.json" "$evidence_dir/.latest.json.tmp"

[[ -x "$RUNNER" ]] || { echo "installed lane runner is missing" >&2; exit 75; }
[[ -f "$CONFIG" && ! -L "$CONFIG" ]] || { echo "private runner config is missing" >&2; exit 75; }
[[ -d "$REPO_ROOT/.git" ]] || { echo "root-owned source checkout is missing" >&2; exit 75; }
[[ "$(stat -c '%u' "$REPO_ROOT" "$REPO_ROOT/.git")" == $'0\n0' ]] || { echo "source checkout is not root-owned" >&2; exit 75; }
[[ -z "$(find "$REPO_ROOT" "$REPO_ROOT/.git" -maxdepth 0 -perm /022 -print -quit)" ]] || { echo "source checkout is group/other writable" >&2; exit 75; }
cmp -s "$RUNNER" "$REPO_ROOT/scripts/real-vps-awg-nat.py" || { echo "installed runner does not match checked-out source" >&2; exit 75; }
cmp -s "$0" "$REPO_ROOT/$ENTRYPOINT" || { echo "installed launcher does not match checked-out source" >&2; exit 75; }
cmp -s /etc/systemd/system/ripdpi-real-vps-awg-nat.service "$REPO_ROOT/scripts/systemd/ripdpi-real-vps-awg-nat.service" || { echo "installed service does not match checked-out source" >&2; exit 75; }
cmp -s /etc/systemd/system/ripdpi-real-vps-awg-nat.timer "$REPO_ROOT/scripts/systemd/ripdpi-real-vps-awg-nat.timer" || { echo "installed timer does not match checked-out source" >&2; exit 75; }
cmp -s /usr/lib/tmpfiles.d/ripdpi-real-vps-awg-nat.conf "$REPO_ROOT/scripts/tmpfiles.d/ripdpi-real-vps-awg-nat.conf" || { echo "installed tmpfiles policy does not match checked-out source" >&2; exit 75; }

source_sha="$(git -C "$REPO_ROOT" rev-parse --verify 'HEAD^{commit}')"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid checked-out source SHA" >&2; exit 75; }
git -C "$REPO_ROOT" diff-index --quiet HEAD -- || { echo "root-owned source checkout has tracked changes" >&2; exit 75; }

work="$RUNTIME_DIRECTORY/run"
rm -rf -- "$work"
install -d -m 0700 "$work"
cleanup() {
  rm -rf -- "$work"
}
trap cleanup EXIT
archive="$work/source.tar"
manifest="$work/manifest.json"
git -C "$REPO_ROOT" archive --format=tar "$source_sha" > "$archive"
archive_sha256="$(sha256sum "$archive" | awk '{print $1}')"

invocation_id="${INVOCATION_ID:-local-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
invocation_attempt="${RIPDPI_AWG_EVIDENCE_INVOCATION_ATTEMPT:-1}"

set +e
"$RUNNER" run \
  --config "$CONFIG" \
  --output "$manifest" \
  --source-sha "$source_sha" \
  --source-archive "$archive" \
  --executor local_systemd \
  --entrypoint-path "$ENTRYPOINT" \
  --invocation-id "$invocation_id" \
  --invocation-attempt "$invocation_attempt"
run_status=$?
set -e
rm -f -- "$archive"

structural_status=1
validate_status=1
if [[ -f "$manifest" ]]; then
  set +e
  "$RUNNER" validate \
    --manifest "$manifest" \
    --expected-source-sha "$source_sha" \
    --expected-source-archive-sha256 "$archive_sha256" \
    --expected-executor local_systemd \
    --expected-invocation-id "$invocation_id" \
    --expected-invocation-attempt "$invocation_attempt" \
    --allow-non-pass
  structural_status=$?
  set -e

  safe_invocation="${invocation_id//:/_}"
  if (( structural_status == 0 )); then
    evidence="$evidence_dir/manifest-${source_sha}-${safe_invocation}.json"
    install -m 0600 "$manifest" "$evidence"
    set +e
    "$RUNNER" validate \
      --manifest "$manifest" \
      --expected-source-sha "$source_sha" \
      --expected-source-archive-sha256 "$archive_sha256" \
      --expected-executor local_systemd \
      --expected-invocation-id "$invocation_id" \
      --expected-invocation-attempt "$invocation_attempt"
    validate_status=$?
    set -e
    if (( run_status == 0 && validate_status == 0 )); then
      install -m 0600 "$manifest" "$evidence_dir/.latest.json.tmp"
      mv -f -- "$evidence_dir/.latest.json.tmp" "$evidence_dir/latest.json"
    fi
  else
    quarantine="$quarantine_dir/invalid-${source_sha}-${safe_invocation}.json"
    install -m 0600 "$manifest" "$quarantine"
  fi
fi

if (( run_status != 0 || structural_status != 0 || validate_status != 0 )); then
  exit 1
fi
