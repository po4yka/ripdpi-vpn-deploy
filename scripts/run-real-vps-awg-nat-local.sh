#!/usr/bin/env bash
# Fixed-command local executor for the recurring real-VPS AWG/NAT evidence lane.
set -euo pipefail

[[ $# -eq 0 ]] || { echo "this fixed-command runner accepts no arguments" >&2; exit 2; }

: "${RUNTIME_DIRECTORY:?systemd must provide RUNTIME_DIRECTORY}"
: "${STATE_DIRECTORY:?systemd must provide STATE_DIRECTORY}"

RUNNER="/usr/local/libexec/ripdpi-real-vps-awg-nat"
CONFIG="/etc/ripdpi/real-vps-awg-nat-local.json"
CLIENT_IDENTITY="/etc/ripdpi/real-vps-awg-client-identity.json"
ENTRYPOINT="scripts/run-real-vps-awg-nat-local.sh"
LOCK_DIR="/run/lock/ripdpi-real-vps-awg-nat"

umask 077
evidence_dir="$STATE_DIRECTORY/evidence"
quarantine_dir="$STATE_DIRECTORY/quarantine"
preflight_epoch="$(date -u +%s 2>/dev/null || printf '1')"
[[ "$preflight_epoch" =~ ^[1-9][0-9]*$ ]] || preflight_epoch=1

# This record contains fixed categories and placeholders only: it is written
# before the installed Python runner and its source checkout are trusted.
emit_preflight_failure() {
  local reason="$1"
  local invocation_id="local-preflight-${preflight_epoch}-$$"
  local temporary="$evidence_dir/.preflight-${preflight_epoch}-${reason}-$$.tmp"
  local evidence="$evidence_dir/preflight-${preflight_epoch}-${reason}-$$.json"
  mkdir -p "$evidence_dir" "$quarantine_dir" 2>/dev/null || return 0
  chmod 0700 "$evidence_dir" "$quarantine_dir" 2>/dev/null || return 0
  printf '%s\n' \
    "{\"captureDigests\":[],\"classification\":\"INFRA_UNAVAILABLE\",\"cleanup\":{\"capturesRemoved\":true,\"clientStopped\":true,\"scratchRemoved\":true,\"serverTransactionFinalized\":true},\"clientIdentity\":{\"artifactSha256\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"ripdpiSourceSha\":\"0000000000000000000000000000000000000000\"},\"finishedAtEpoch\":${preflight_epoch},\"generatedAtEpoch\":${preflight_epoch},\"phases\":[],\"privateLogSha256\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"producerDigests\":{\"rotationHookSha256\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"runnerSha256\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"serverControlHookSha256\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"serverDeployHookSha256\":\"0000000000000000000000000000000000000000000000000000000000000000\"},\"provenance\":{\"entrypointPath\":\"scripts/run-real-vps-awg-nat-local.sh\",\"executor\":\"local_systemd\",\"invocationAttempt\":1,\"invocationId\":\"${invocation_id}\",\"sourceArchiveSha256\":\"0000000000000000000000000000000000000000000000000000000000000000\"},\"reasonCode\":\"${reason}\",\"rotation\":{\"committed\":false,\"newKeyMatched\":false,\"oldKeyRejected\":false,\"prepared\":false,\"rolledBack\":false},\"runnerIdSha256\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"serverDeployment\":{\"archiveMatched\":false,\"receiptSha256\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"sourceCurrent\":false},\"sourceSha\":\"0000000000000000000000000000000000000000\",\"startedAtEpoch\":${preflight_epoch},\"version\":\"real_vps_awg_nat_evidence_v3\"}" \
    > "$temporary" 2>/dev/null || return 0
  chmod 0600 "$temporary" 2>/dev/null || { rm -f -- "$temporary"; return 0; }
  mv -f -- "$temporary" "$evidence" 2>/dev/null || rm -f -- "$temporary"
}

preflight_fail() {
  emit_preflight_failure "$1"
  exit 75
}

for tool in awk cmp find flock git install python3 readlink sha256sum stat; do
  command -v "$tool" >/dev/null 2>&1 || preflight_fail PREFLIGHT_TOOL_MISSING
done
if ! REPO_ROOT="$(readlink -f "${RIPDPI_AWG_EVIDENCE_REPO_ROOT:-/opt/ripdpi-real-vps-awg-nat/current}")"; then
  preflight_fail PREFLIGHT_SOURCE_UNSAFE
fi
[[ -d "$LOCK_DIR" ]] || preflight_fail PREFLIGHT_LOCK_BUSY
[[ "$(stat -c '%u:%a' "$LOCK_DIR")" == "0:700" ]] || preflight_fail PREFLIGHT_LOCK_BUSY
exec 9>"$LOCK_DIR/lane.lock" || preflight_fail PREFLIGHT_LOCK_BUSY
flock -n 9 || preflight_fail PREFLIGHT_LOCK_BUSY

install -d -m 0700 "$evidence_dir" "$quarantine_dir" || preflight_fail PREFLIGHT_CONFIG_INVALID
[[ -x "$RUNNER" ]] || preflight_fail PREFLIGHT_RUNNER_INVALID
[[ -f "$CONFIG" && ! -L "$CONFIG" ]] || preflight_fail PREFLIGHT_CONFIG_INVALID
[[ -d "$REPO_ROOT/.git" ]] || preflight_fail PREFLIGHT_SOURCE_UNSAFE
[[ "$(stat -c '%u' "$REPO_ROOT" "$REPO_ROOT/.git")" == $'0\n0' ]] || preflight_fail PREFLIGHT_SOURCE_UNSAFE
[[ -z "$(find "$REPO_ROOT" "$REPO_ROOT/.git" -maxdepth 0 -perm /022 -print -quit)" ]] || preflight_fail PREFLIGHT_SOURCE_UNSAFE
cmp -s "$RUNNER" "$REPO_ROOT/scripts/real-vps-awg-nat.py" || preflight_fail PREFLIGHT_SOURCE_MISMATCH
cmp -s "$0" "$REPO_ROOT/$ENTRYPOINT" || preflight_fail PREFLIGHT_SOURCE_MISMATCH
cmp -s /etc/systemd/system/ripdpi-real-vps-awg-nat.service "$REPO_ROOT/scripts/systemd/ripdpi-real-vps-awg-nat.service" || preflight_fail PREFLIGHT_SOURCE_MISMATCH
cmp -s /etc/systemd/system/ripdpi-real-vps-awg-nat.timer "$REPO_ROOT/scripts/systemd/ripdpi-real-vps-awg-nat.timer" || preflight_fail PREFLIGHT_SOURCE_MISMATCH
cmp -s /usr/lib/tmpfiles.d/ripdpi-real-vps-awg-nat.conf "$REPO_ROOT/scripts/tmpfiles.d/ripdpi-real-vps-awg-nat.conf" || preflight_fail PREFLIGHT_SOURCE_MISMATCH
if ! source_sha="$(git -C "$REPO_ROOT" rev-parse --verify 'HEAD^{commit}')"; then
  preflight_fail PREFLIGHT_SOURCE_UNSAFE
fi
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || preflight_fail PREFLIGHT_SOURCE_UNSAFE
git -C "$REPO_ROOT" diff-index --quiet HEAD -- || preflight_fail PREFLIGHT_SOURCE_UNSAFE
if ! client_binary="$(readlink -f "$(command -v amneziawg-go)")"; then
  preflight_fail PREFLIGHT_RUNNER_INVALID
fi
if ! client_identity_json="$(
  "$RUNNER" validate-client-runtime \
    --identity "$CLIENT_IDENTITY" \
    --binary "$client_binary"
)"; then
  preflight_fail PREFLIGHT_RUNNER_INVALID
fi
if ! client_identity_values="$(
  printf '%s\n' "$client_identity_json" | python3 -c \
    'import json,sys; value=json.load(sys.stdin); print(value["ripdpiSourceSha"], value["artifactSha256"])'
)"; then
  preflight_fail PREFLIGHT_RUNNER_INVALID
fi
read -r client_source_sha client_artifact_sha256 <<< "$client_identity_values"
[[ "$client_source_sha" =~ ^[0-9a-f]{40}$ ]] || preflight_fail PREFLIGHT_RUNNER_INVALID
[[ "$client_artifact_sha256" =~ ^[0-9a-f]{64}$ ]] || preflight_fail PREFLIGHT_RUNNER_INVALID
# The runner's command lookup and exec now resolve the same immutable directory
# that was validated above; the lane lock serializes authorized toolchain swaps.
PATH="$(dirname "$client_binary"):$PATH"
export PATH

# A preflight refusal leaves an existing last known PASS intact.
rm -f -- "$evidence_dir/latest.json" "$evidence_dir/.latest.json.tmp"

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
    --expected-client-source-sha "$client_source_sha" \
    --expected-client-artifact-sha256 "$client_artifact_sha256" \
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
      --expected-invocation-attempt "$invocation_attempt" \
      --expected-client-source-sha "$client_source_sha" \
      --expected-client-artifact-sha256 "$client_artifact_sha256"
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
