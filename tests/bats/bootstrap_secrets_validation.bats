#!/usr/bin/env bats

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/bootstrap-secrets.sh"

_run_bootstrap() {
  run env HOME="$BATS_TEST_TMPDIR" bash "$SCRIPT" \
    --env "${TEST_ENV-prod}" \
    --clients "${TEST_CLIENTS-phone}" \
    --target "${TEST_TARGET-mirror.example.com:443}" \
    --server-name "${TEST_SERVER_NAME-mirror.example.com}" \
    --xhttp-host "${TEST_XHTTP_HOST-vpn.example.com}"
}

_install_bootstrap_stubs() {
  FAKE_BIN="${BATS_TEST_TMPDIR}/bin"
  UUID_STATE="${BATS_TEST_TMPDIR}/uuid-state"
  OPENSSL_STATE="${BATS_TEST_TMPDIR}/openssl-state"
  mkdir -p "$FAKE_BIN"
  printf '0\n' > "$UUID_STATE"
  printf '0\n' > "$OPENSSL_STATE"
  cat > "${FAKE_BIN}/age" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  cat > "${FAKE_BIN}/age-keygen" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == "-o" ]]
printf '%s\n' '# created: test' '# public key: age1testrecipient000000000000000000000000000000000000000000000000000' 'AGE-SECRET-KEY-TEST' > "$2"
EOF
  cat > "${FAKE_BIN}/xray" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' 'Private key: test-private-key-0000000000000000000000000000' 'Public key: test-public-key-00000000000000000000000000000'
EOF
  cat > "${FAKE_BIN}/uuidgen" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
count="$(cat "$UUID_STATE")"
count=$((count + 1))
printf '%s\n' "$count" > "$UUID_STATE"
printf '00000000-0000-4000-8000-%012d\n' "$count"
EOF
  cat > "${FAKE_BIN}/openssl" <<'EOF'
#!/usr/bin/env bash
case "${2:-}:${3:-}" in
  -hex:4)
    count="$(cat "$OPENSSL_STATE")"
    count=$((count + 1))
    printf '%s\n' "$count" > "$OPENSSL_STATE"
    printf '%08x\n' "$count"
    ;;
  -hex:8) printf '0102030405060708\n' ;;
  -hex:16) printf '0102030405060708090a0b0c0d0e0f10\n' ;;
  -base64:24) printf 'abcdefghijklmnopqrstuvwx12345678\n' ;;
  -base64:32) printf 'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH\n' ;;
  *) exit 64 ;;
esac
EOF
  cat > "${FAKE_BIN}/wg" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == "genkey" ]]
printf 'test-awg-server-private-key\n'
EOF
  cat > "${FAKE_BIN}/sops" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == "--encrypt" ]]
cat "${!#}"
EOF
  chmod 0700 "${FAKE_BIN}/age" "${FAKE_BIN}/age-keygen" "${FAKE_BIN}/xray" "${FAKE_BIN}/uuidgen" "${FAKE_BIN}/openssl" "${FAKE_BIN}/wg" "${FAKE_BIN}/sops"
}

@test "bootstrap rejects path traversal environment before filesystem changes" {
  TEST_ENV='../../escape'

  _run_bootstrap

  [ "$status" -ne 0 ]
  [[ "$output" == *"invalid environment name"* ]]
  [ ! -e "${BATS_TEST_TMPDIR}/.config" ]
  [ ! -e "${BATS_TEST_TMPDIR}/escape.secrets.yaml" ]
}

@test "bootstrap rejects invalid and duplicate client names" {
  local clients
  for clients in 'phone,bad:name' 'phone,phone' 'phone,' ''; do
    TEST_CLIENTS="$clients"
    _run_bootstrap
    [ "$status" -ne 0 ]
    [[ "$output" == *"client"* ]]
    [ ! -e "${BATS_TEST_TMPDIR}/.config" ]
  done
}

@test "bootstrap rejects malformed server and xhttp hostnames" {
  TEST_SERVER_NAME=$'vpn.example.com"\nadmin: true'
  _run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"invalid server name"* ]]

  TEST_SERVER_NAME='999.999.999.999'
  _run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"invalid server name"* ]]

  unset TEST_SERVER_NAME
  TEST_XHTTP_HOST='-vpn.example.com'
  _run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"invalid xhttp hostname"* ]]
  [ ! -e "${BATS_TEST_TMPDIR}/.config" ]
}

@test "bootstrap rejects malformed targets and invalid ports" {
  local target
  for target in 'mirror.example.com' 'mirror.example.com:0' 'mirror.example.com:65536' 'bad_host.example.com:443' '999.999.999.999:443' '[2001:db8::1]:443' $'mirror.example.com:443"\nadmin: true'; do
    TEST_TARGET="$target"
    _run_bootstrap
    [ "$status" -ne 0 ]
    [[ "$output" == *"invalid target"* ]]
    [ ! -e "${BATS_TEST_TMPDIR}/.config" ]
  done
}

@test "bootstrap serializes validated inputs into quoted YAML scalars" {
  _install_bootstrap_stubs
  TEST_ENV='test-env'
  TEST_CLIENTS='phone,laptop'
  TEST_TARGET='mirror.example.com:8443'
  TEST_SERVER_NAME='mirror.example.com'
  TEST_XHTTP_HOST='vpn.example.com'

  run env -u VPN_PROVISION_CONFIG_DIR PATH="${FAKE_BIN}:${PATH}" UUID_STATE="$UUID_STATE" OPENSSL_STATE="$OPENSSL_STATE" HOME="$BATS_TEST_TMPDIR" bash "$SCRIPT" \
    --env "$TEST_ENV" \
    --clients "$TEST_CLIENTS" \
    --target "$TEST_TARGET" \
    --server-name "$TEST_SERVER_NAME" \
    --xhttp-host "$TEST_XHTTP_HOST"

  [ "$status" -eq 0 ]
  local encrypted="${BATS_TEST_TMPDIR}/.config/vpn-provision/test-env.secrets.sops.yaml"
  [ -f "$encrypted" ]
  [ ! -e "${BATS_TEST_TMPDIR}/.config/vpn-provision/test-env.secrets.yaml" ]
  [ "$(grep -Fc 'target: "mirror.example.com:8443"' "$encrypted")" -eq 1 ]
  [ "$(grep -Fc '    - "mirror.example.com"' "$encrypted")" -eq 1 ]
  [ "$(grep -Fc '    - name: "phone"' "$encrypted")" -eq 2 ]
  [ "$(grep -Fc '    - name: "laptop"' "$encrypted")" -eq 2 ]
  [ "$(grep -Fc 'server_name: "vpn.example.com"' "$encrypted")" -eq 2 ]
  [ "$(grep -Fc '  peers: []' "$encrypted")" -eq 1 ]
  [ "$(grep -Fc '  source_commit:' "$encrypted")" -eq 1 ]
  [ "$(grep -Fc '  source_linux_amd64_sha256:' "$encrypted")" -eq 1 ]
  [ "$(grep -Fc '  source_linux_arm64_sha256:' "$encrypted")" -eq 1 ]
}

@test "bootstrap honors a repo-local provisioning directory" {
  _install_bootstrap_stubs
  local config_dir="${BATS_TEST_TMPDIR}/repo/state-backups/vpn-provision"

  run env PATH="${FAKE_BIN}:${PATH}" UUID_STATE="$UUID_STATE" OPENSSL_STATE="$OPENSSL_STATE" HOME="$BATS_TEST_TMPDIR" VPN_PROVISION_CONFIG_DIR="$config_dir" bash "$SCRIPT" \
    --env local-env \
    --clients phone \
    --target mirror.example.com:443 \
    --server-name mirror.example.com \
    --xhttp-host vpn.example.com

  [ "$status" -eq 0 ]
  [ -f "${config_dir}/age.key" ]
  [ -f "${config_dir}/local-env.secrets.sops.yaml" ]
  [ ! -e "${BATS_TEST_TMPDIR}/.config/vpn-provision/local-env.secrets.sops.yaml" ]
}
