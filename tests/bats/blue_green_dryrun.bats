#!/usr/bin/env bats
# Dry-run tests for scripts/blue-green.sh.
#
# Verifies that --dry-run exits 0 and triggers only read-only stub calls:
#   - output mentions "terraform plan"
#   - output mentions "--check"
#   - STUB_LOG does not contain: terraform apply, audit-log, sops --encrypt

load 'test_helper/bats-support/load'
load 'test_helper/bats-assert/load'

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/blue-green.sh"
STUB_BIN="${REPO_ROOT}/tests/stubs/bin"

setup() {
  STUB_LOG="$(mktemp -t stub_log.XXXXXX)"
  FAKE_SOPS="$(mktemp -t prod_secrets.XXXXXX)"
  # blue-green.sh checks SOPS_FILE exists before reaching the dry-run branch
  export PATH="${STUB_BIN}:${PATH}"
  export STUB_LOG
  export BLUE_ENV="prod"
  export GREEN_ENV="green1"
  export PROVIDER="upcloud"
  export SOPS_FILE="${FAKE_SOPS}"
  export ANSIBLE_SSH_PRIVATE_KEY_FILE="${BATS_TEST_TMPDIR}/id_ed25519"
  export MAKE="true"
}

teardown() {
  rm -f "${STUB_LOG}" "${FAKE_SOPS}"
}

_run_dry() {
  run bash "${SCRIPT}" --dry-run --blue-env prod --green-env green1
}

@test "dry-run exits 0" {
  _run_dry
  assert_success
}

@test "dry-run output mentions terraform plan" {
  _run_dry
  assert_output --partial "terraform plan"
}

@test "dry-run output mentions --check (ansible check mode)" {
  _run_dry
  assert_output --partial "--check"
}

@test "dry-run STUB_LOG has no terraform apply" {
  _run_dry
  if [[ -s "${STUB_LOG}" ]]; then
    run grep -F "terraform apply" "${STUB_LOG}"
    assert_failure
  fi
}

@test "dry-run STUB_LOG has no audit-log" {
  _run_dry
  if [[ -s "${STUB_LOG}" ]]; then
    run grep -F "audit-log" "${STUB_LOG}"
    assert_failure
  fi
}

@test "dry-run STUB_LOG has no sops --encrypt" {
  _run_dry
  if [[ -s "${STUB_LOG}" ]]; then
    run grep -F -- "--encrypt" "${STUB_LOG}"
    assert_failure
  fi
}

@test "dry-run STUB_LOG has no sops call at all" {
  _run_dry
  if [[ -s "${STUB_LOG}" ]]; then
    run grep -F "sops" "${STUB_LOG}"
    assert_failure
  fi
}

@test "decrypted secrets use a private random file and are removed on exit" {
  local fake_bin="${BATS_TEST_TMPDIR}/bin"
  local capture="${BATS_TEST_TMPDIR}/secrets-path"
  mkdir -p "$fake_bin"
  cat > "${fake_bin}/make" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if ! file_mode="$(stat -c '%a' "$VPN_SECRETS_FILE" 2>/dev/null)"; then
  file_mode="$(stat -f '%Lp' "$VPN_SECRETS_FILE")"
fi
if ! dir_mode="$(stat -c '%a' "$(dirname "$VPN_SECRETS_FILE")" 2>/dev/null)"; then
  dir_mode="$(stat -f '%Lp' "$(dirname "$VPN_SECRETS_FILE")")"
fi
printf '%s\n%s\n%s\n' "$VPN_SECRETS_FILE" "$file_mode" "$dir_mode" > "$TEST_CAPTURE"
exit 23
EOF
  chmod 0700 "${fake_bin}/make"

  run env \
    PATH="${fake_bin}:${PATH}" \
    TEST_CAPTURE="$capture" \
    bash "$SCRIPT"

  assert_failure 23
  local secrets_path
  secrets_path="$(sed -n '1p' "$capture")"
  [[ "$secrets_path" == */vpn-blue-green.*/secrets.yaml ]]
  [[ "$(sed -n '2p' "$capture")" == "600" ]]
  [[ "$(sed -n '3p' "$capture")" == "700" ]]
  [[ ! -e "$secrets_path" ]]
  [[ ! -L "$secrets_path" ]]
  [[ ! -d "$(dirname "$secrets_path")" ]]
}

@test "partial decryption is removed when sops fails" {
  local fake_bin="${BATS_TEST_TMPDIR}/bin"
  local dir_capture="${BATS_TEST_TMPDIR}/secrets-dir"
  local real_mktemp
  real_mktemp="$(command -v mktemp)"
  mkdir -p "$fake_bin"
  cat > "${fake_bin}/mktemp" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
path="$("$REAL_MKTEMP" "$@")"
printf '%s\n' "$path" > "$TEST_DIR_CAPTURE"
printf '%s\n' "$path"
EOF
  cat > "${fake_bin}/sops" <<'EOF'
#!/usr/bin/env bash
printf 'partial plaintext\n'
exit 42
EOF
  chmod 0700 "${fake_bin}/mktemp" "${fake_bin}/sops"

  run env \
    PATH="${fake_bin}:${PATH}" \
    REAL_MKTEMP="$real_mktemp" \
    TEST_DIR_CAPTURE="$dir_capture" \
    bash "$SCRIPT"

  assert_failure 42
  [[ ! -e "$(cat "$dir_capture")" ]]
}
