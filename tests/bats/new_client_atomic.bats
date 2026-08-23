#!/usr/bin/env bats

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/new-client.sh"

setup() {
  FAKE_BIN="${BATS_TEST_TMPDIR}/bin"
  SOPS_FILE="${BATS_TEST_TMPDIR}/secrets.sops.yaml"
  SOPS_STATE="${BATS_TEST_TMPDIR}/sops-state"
  mkdir -p "$FAKE_BIN"
  printf 'encrypted-original\n' > "$SOPS_FILE"
  printf '0\n' > "$SOPS_STATE"

  cat > "${FAKE_BIN}/sops" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--decrypt" ]]; then
  if [[ "$*" != *--extract* ]]; then
    printf '{"snell_secrets":{"variants":%s}}\n' "${SNELL_VARIANTS:-[]}"
  else
    printf '[]\n'
  fi
  exit 0
fi
case "${1:-}" in
  set)
    shift
    if [[ "${1:-}" == "--value-stdin" ]]; then
      shift
      cat >/dev/null
    fi
    target="$1"
    ;;
  *) exit 64 ;;
esac
count="$(cat "$SOPS_STATE")"
count=$((count + 1))
printf '%s\n' "$count" > "$SOPS_STATE"
printf 'mutation-%s\n' "$count" >> "$target"
if [[ "$count" == "${SOPS_FAIL_ON:-0}" ]]; then
  exit 42
fi
EOF
  cat > "${FAKE_BIN}/uuidgen" <<'EOF'
#!/usr/bin/env bash
printf '00000000-0000-4000-8000-000000000001\n'
EOF
  cat > "${FAKE_BIN}/openssl" <<'EOF'
#!/usr/bin/env bash
if [[ "${2:-}" == "-hex" ]]; then
  printf '01020304\n'
else
  printf 'fixed-hysteria-password\n'
fi
EOF
  cat > "${FAKE_BIN}/awg" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  genkey) printf 'private-key\n' ;;
  pubkey) cat >/dev/null; printf 'public-key\n' ;;
  genpsk) printf 'preshared-key\n' ;;
  *) exit 64 ;;
esac
EOF
  chmod 0700 "${FAKE_BIN}/sops" "${FAKE_BIN}/uuidgen" "${FAKE_BIN}/openssl" "${FAKE_BIN}/awg"
}

_run_new_client() {
  run env \
    PATH="${FAKE_BIN}:${PATH}" \
    HOME="$BATS_TEST_TMPDIR" \
    SOPS_FILE="$SOPS_FILE" \
    SOPS_STATE="$SOPS_STATE" \
    SOPS_FAIL_ON="${1:-0}" \
    SNELL_VARIANTS="${SNELL_VARIANTS:-}" \
    bash "$SCRIPT" phone
}

@test "failure after a staged profile update leaves original secrets unchanged" {
  local fail_on
  for fail_on in 1 2 3; do
    printf 'encrypted-original\n' > "$SOPS_FILE"
    printf '0\n' > "$SOPS_STATE"

    _run_new_client "$fail_on"

    [ "$status" -eq 42 ]
    [ "$(cat "$SOPS_FILE")" = "encrypted-original" ]
    [ -z "$(find "$BATS_TEST_TMPDIR" -maxdepth 1 -name '*.new-client.*.yaml' -print -quit)" ]

    printf '0\n' > "$SOPS_STATE"
    _run_new_client
    [ "$status" -eq 0 ]
    [ "$(grep -c '^mutation-' "$SOPS_FILE")" -eq 4 ]
  done
}

@test "successful profile updates replace secrets once and remove staging file" {
  _run_new_client

  [ "$status" -eq 0 ]
  [ "$(grep -c '^mutation-' "$SOPS_FILE")" -eq 4 ]
  [ -z "$(find "$BATS_TEST_TMPDIR" -maxdepth 1 -name '*.new-client.*.yaml' -print -quit)" ]
}

@test "configured Snell variants receive distinct atomic client updates" {
  SNELL_VARIANTS='[{"id":"v4-stream","users":[]},{"id":"v6-default","users":[]},{"id":"v6-unshaped","users":[]}]'

  _run_new_client

  [ "$status" -eq 0 ]
  [ "$(grep -c '^mutation-' "$SOPS_FILE")" -eq 7 ]
  [ -z "$(find "$BATS_TEST_TMPDIR" -maxdepth 1 -name '*.new-client.*.yaml' -print -quit)" ]
}

@test "competing transaction is rejected before secrets are changed" {
  local lock="${SOPS_FILE}.new-client.lock"
  local ready="${BATS_TEST_TMPDIR}/lock-ready"
  local holder_pid="${BATS_TEST_TMPDIR}/lock-holder-pid"
  local holder
  if command -v flock >/dev/null 2>&1; then
    flock "$lock" bash -c 'printf "%s\n" "$$" > "$1"; touch "$2"; sleep 30' bash "$holder_pid" "$ready" &
  else
    lockf "$lock" bash -c 'printf "%s\n" "$$" > "$1"; touch "$2"; sleep 30' bash "$holder_pid" "$ready" &
  fi
  holder=$!
  while [[ ! -e "$ready" ]]; do
    sleep 0.05
  done

  _run_new_client

  kill "$(cat "$holder_pid")" 2>/dev/null || true
  wait "$holder" 2>/dev/null || true
  [ "$status" -ne 0 ]
  [[ "$output" == *"another new-client transaction is active"* ]]
  [ "$(cat "$SOPS_FILE")" = "encrypted-original" ]
}

@test "stale lock file does not block a retry" {
  printf 'stale-owner\n' > "${SOPS_FILE}.new-client.lock"

  _run_new_client

  [ "$status" -eq 0 ]
  [ "$(grep -c '^mutation-' "$SOPS_FILE")" -eq 4 ]
}

@test "symlink secrets path updates its target without replacing the link" {
  local target="${BATS_TEST_TMPDIR}/target.sops.yaml"
  local link="${BATS_TEST_TMPDIR}/linked.sops.yaml"
  mv "$SOPS_FILE" "$target"
  ln -s "$target" "$link"
  SOPS_FILE="$link"

  _run_new_client

  [ "$status" -eq 0 ]
  [ -L "$link" ]
  [ "$(grep -c '^mutation-' "$target")" -eq 4 ]
}
