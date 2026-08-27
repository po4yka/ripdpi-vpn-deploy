#!/usr/bin/env bats

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"

setup() {
  mkdir -p "${BATS_TEST_TMPDIR}/bin"
  cat > "${BATS_TEST_TMPDIR}/bin/sops" <<'EOF'
#!/usr/bin/env bash
printf 'fixture: true\n'
exit "${SOPS_TEST_EXIT:-0}"
EOF
  chmod 0700 "${BATS_TEST_TMPDIR}/bin/sops"
  printf 'synthetic encrypted fixture\n' > "${BATS_TEST_TMPDIR}/input.yaml"
}

decrypt_fixture() {
  run env -u XDG_RUNTIME_DIR PATH="${BATS_TEST_TMPDIR}/bin:${PATH}" \
    SOPS_FILE="${BATS_TEST_TMPDIR}/input.yaml" SECRETS_FILE="$1" \
    VPN_RUNTIME_DIR="${BATS_TEST_TMPDIR}/unused-runtime" ENV=test \
    SOPS_TEST_EXIT="${SOPS_TEST_EXIT:-0}" bash "${REPO_ROOT}/scripts/decrypt-secrets.sh"
}

@test "decrypt creates the explicit output parent outside the default runtime" {
  local out="${BATS_TEST_TMPDIR}/new directory/nested/vpn-test.secrets.yaml"
  decrypt_fixture "$out"
  [ "$status" -eq 0 ]
  [ "$(cat "$out")" = 'fixture: true' ]
  [ ! -e "${BATS_TEST_TMPDIR}/unused-runtime" ]
  [[ "$output" != *"$out"* ]]
  run python3 -c 'import os, stat, sys; assert stat.S_IMODE(os.stat(sys.argv[1]).st_mode) == 0o600' "$out"
  [ "$status" -eq 0 ]
}

@test "decrypt failure keeps the previous file and removes partial plaintext" {
  local dir="${BATS_TEST_TMPDIR}/runtime" out
  mkdir "$dir"
  out="${dir}/vpn-test.secrets.yaml"
  printf 'previous\n' > "$out"
  SOPS_TEST_EXIT=9 decrypt_fixture "$out"
  [ "$status" -ne 0 ]
  [ "$(cat "$out")" = previous ]
  run python3 -c 'import pathlib, sys; assert not list(pathlib.Path(sys.argv[1]).glob(".vpn-*.secrets.*"))' "$dir"
  [ "$status" -eq 0 ]
}

@test "decrypt rejects a symlink output directory before invoking sops" {
  mkdir "${BATS_TEST_TMPDIR}/actual"
  ln -s "${BATS_TEST_TMPDIR}/actual" "${BATS_TEST_TMPDIR}/linked"
  decrypt_fixture "${BATS_TEST_TMPDIR}/linked/vpn-test.secrets.yaml"
  [ "$status" -ne 0 ]
  [ ! -e "${BATS_TEST_TMPDIR}/actual/vpn-test.secrets.yaml" ]
}

@test "decrypt refuses a shared writable output directory without changing its mode" {
  mkdir "${BATS_TEST_TMPDIR}/shared"
  chmod 0777 "${BATS_TEST_TMPDIR}/shared"
  decrypt_fixture "${BATS_TEST_TMPDIR}/shared/vpn-test.secrets.yaml"
  [ "$status" -ne 0 ]
  [ ! -e "${BATS_TEST_TMPDIR}/shared/vpn-test.secrets.yaml" ]
  run python3 -c 'import os, stat, sys; assert stat.S_IMODE(os.stat(sys.argv[1]).st_mode) == 0o777' "${BATS_TEST_TMPDIR}/shared"
  [ "$status" -eq 0 ]
}

@test "decrypt refuses symlink and directory output paths" {
  mkdir "${BATS_TEST_TMPDIR}/destination"
  ln -s "${BATS_TEST_TMPDIR}/destination" "${BATS_TEST_TMPDIR}/linked-output"
  decrypt_fixture "${BATS_TEST_TMPDIR}/linked-output"
  [ "$status" -ne 0 ]
  decrypt_fixture "${BATS_TEST_TMPDIR}/destination"
  [ "$status" -ne 0 ]
  run python3 -c 'import pathlib, sys; assert not list(pathlib.Path(sys.argv[1]).iterdir())' "${BATS_TEST_TMPDIR}/destination"
  [ "$status" -eq 0 ]
}
