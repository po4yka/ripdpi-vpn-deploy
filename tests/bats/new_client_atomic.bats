#!/usr/bin/env bats
# Actual all-profile CLI transactions; only selected encryption failure is injected.
REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/new-client.sh"

setup() {
  umask 077
  chmod 0700 "$BATS_TEST_TMPDIR"
  FAKE_BIN="${BATS_TEST_TMPDIR}/bin"
  SOPS_FILE="${BATS_TEST_TMPDIR}/secrets.sops.yaml"
  SOPS_STATE="${BATS_TEST_TMPDIR}/sops-state"
  ORIGINAL="${BATS_TEST_TMPDIR}/original.sops.yaml"
  REAL_SOPS="$(command -v sops)"
  if [[ "$REAL_SOPS" == */mise/shims/* ]]; then
    while IFS= read -r candidate; do
      [[ "$candidate" == */mise/shims/* ]] || { REAL_SOPS="$candidate"; break; }
    done < <(type -ap sops)
    [[ "$REAL_SOPS" != */mise/shims/* ]]
  fi
  SOPS_AGE_KEY_FILE="${BATS_TEST_TMPDIR}/age-test.key"
  cp "${REPO_ROOT}/tests/fixtures/age-test.key" "$SOPS_AGE_KEY_FILE"
  chmod 0600 "$SOPS_AGE_KEY_FILE"
  export REAL_SOPS SOPS_AGE_KEY_FILE
  mkdir -m 0700 "$FAKE_BIN"
  cat > "${FAKE_BIN}/sops" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == set ]]; then
  count="$(cat "$SOPS_STATE")"
  count=$((count + 1))
  printf '%s\n' "$count" > "$SOPS_STATE"
  [[ "$count" != "${SOPS_FAIL_ON:-0}" ]] || exit 42
fi
exec "$REAL_SOPS" "$@"
EOF
  chmod 0700 "${FAKE_BIN}/sops"
  _seed
}

_seed() {
  local recipient
  recipient="$(age-keygen -y "$SOPS_AGE_KEY_FILE")"
  python3 -c '
import base64, json, os
print(json.dumps({
  "unrelated": {"retain": "synthetic-private-marker"},
  "xray": {"clients": []},
  "hysteria": {"clients": [], "masquerade_type": "proxy", "masquerade_url": "https://owned.example"},
  "amneziawg_secrets": {"instances": [{"name": "awg0", "listen_port": 51820,
    "address_v4": "10.66.66.1/24", "address_v6": "fd42:42:42::1/64",
    "server_private_key": base64.b64encode(bytes([8])*32).decode(),
    "jc": 4, "jmin": 40, "jmax": 70, "s1": 50, "s2": 100,
    "h1": 11, "h2": 12, "h3": 13, "h4": 14, "peers": []}]},
  "snell_secrets": {"variants": json.loads(os.environ.get("SNELL_VARIANTS") or "[]")},
  "client_registry": {}}))
' | "$REAL_SOPS" --encrypt --age "$recipient" --input-type json --output-type yaml /dev/stdin > "$SOPS_FILE"
  chmod 0600 "$SOPS_FILE"
  cp "$SOPS_FILE" "$ORIGINAL"
  printf '0\n' > "$SOPS_STATE"
}

_run_new_client() {
  run env PATH="${FAKE_BIN}:${PATH}" HOME="$BATS_TEST_TMPDIR" \
    SOPS_FILE="$SOPS_FILE" SOPS_STATE="$SOPS_STATE" \
    REAL_SOPS="$REAL_SOPS" SOPS_AGE_KEY_FILE="$SOPS_AGE_KEY_FILE" \
    SOPS_FAIL_ON="${1:-0}" PROVIDER=upcloud ENV=prod AWG_INSTANCE=awg0 COHORT= bash "$SCRIPT" phone

}

_assert_issued() {
  "$REAL_SOPS" --decrypt --output-type json "$SOPS_FILE" | python3 -c '
import json,sys
doc=json.load(sys.stdin)
assert doc["unrelated"]=={"retain":"synthetic-private-marker"}
assert doc["xray"]["clients"][0]["name"]=="phone"
assert doc["hysteria"]["clients"][0]["name"]=="phone"
assert doc["amneziawg_secrets"]["instances"][0]["peers"][0]["name"]=="phone"
assert doc["client_registry"]["phone"]["awg_binding"]["instance"]=="awg0"
keys=[item["users"][0]["userkey"] for item in doc["snell_secrets"]["variants"]]
assert len(keys)==len(set(keys))
'
  [ -z "$(find "$BATS_TEST_TMPDIR" -maxdepth 1 -name '.*.client.*.yaml' -print -quit)" ]
}

@test "failure after a staged profile update leaves original secrets unchanged" {
  local fail_on
  for fail_on in 1 2 3; do
    _seed
    _run_new_client "$fail_on"
    [ "$status" -ne 0 ]
    [[ "$output" == *"awg-device-operation-refused"* ]]
    cmp "$SOPS_FILE" "$ORIGINAL"
    [ -z "$(find "$BATS_TEST_TMPDIR" -maxdepth 1 -name '.*.client.*.yaml' -print -quit)" ]
    printf '0\n' > "$SOPS_STATE"
    _run_new_client
    [ "$status" -eq 0 ]
    _assert_issued
  done
}

@test "successful profile updates publish verified ciphertext and remove staging" {
  _run_new_client
  [ "$status" -eq 0 ]
  _assert_issued
  ! cmp -s "$SOPS_FILE" "$ORIGINAL"
}

@test "configured Snell variants receive distinct atomic client updates" {
  export SNELL_VARIANTS='[{"id":"v4-stream","users":[]},{"id":"v6-default","users":[]},{"id":"v6-unshaped","users":[]}]'
  _seed
  _run_new_client
  [ "$status" -eq 0 ]
  _assert_issued
}

@test "competing transaction is rejected before encrypted reads or changes" {
  local ready="${BATS_TEST_TMPDIR}/lock-ready"
  local holder
  python3 -c 'import fcntl,os,sys,time; fd=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR,0o600); fcntl.flock(fd,fcntl.LOCK_EX); open(sys.argv[2],"w").close(); time.sleep(30)' \
    "${SOPS_FILE}.new-client.lock" "$ready" &
  holder=$!
  for _ in {1..100}; do
    [[ ! -e "$ready" ]] || break
    sleep 0.05
  done
  [ -e "$ready" ]
  _run_new_client
  kill "$holder"
  wait "$holder" 2>/dev/null || true
  [ "$status" -ne 0 ]
  [[ "$output" == *"awg-device-operation-refused"* ]]
  cmp "$SOPS_FILE" "$ORIGINAL"
  [ "$(cat "$SOPS_STATE")" -eq 0 ]
}

@test "owned private stale lock file does not block a retry" {
  printf 'stale-owner\n' > "${SOPS_FILE}.new-client.lock"
  chmod 0600 "${SOPS_FILE}.new-client.lock"
  _run_new_client
  [ "$status" -eq 0 ]
  _assert_issued
}

@test "symlink secrets path refuses and preserves its target and link" {
  local target="${BATS_TEST_TMPDIR}/target.sops.yaml"
  local link="${BATS_TEST_TMPDIR}/linked.sops.yaml"
  mv "$SOPS_FILE" "$target"
  ln -s "$target" "$link"
  SOPS_FILE="$link"
  _run_new_client
  [ "$status" -ne 0 ]
  [ -L "$link" ]
  cmp "$target" "$ORIGINAL"
  [ "$(cat "$SOPS_STATE")" -eq 0 ]
}
