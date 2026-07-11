#!/usr/bin/env bats
# Dry-run tests for scripts/fleet-rotate.sh.
#
# Verifies that --dry-run exits 0 and is hermetic:
#   - plan id appears in output
#   - both rotation entries (upcloud, hetzner) appear in output
#   - STUB_LOG has no terraform apply, sops --encrypt, gh release create,
#     or audit-log entries

load 'test_helper/bats-support/load'
load 'test_helper/bats-assert/load'

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/fleet-rotate.sh"
STUB_BIN="${REPO_ROOT}/tests/stubs/bin"
PLAN="${REPO_ROOT}/tests/fixtures/fleet-plan-sample.yaml"

setup() {
  STUB_LOG="$(mktemp -t stub_log.XXXXXX)"
  export PATH="${STUB_BIN}:${PATH}"
  export STUB_LOG
  TEST_REPO="${BATS_TEST_TMPDIR}/repo"
  mkdir -p "${TEST_REPO}/scripts"
  cp "${SCRIPT}" "${TEST_REPO}/scripts/fleet-rotate.sh"
  ISOLATED_SCRIPT="${TEST_REPO}/scripts/fleet-rotate.sh"
}

teardown() {
  rm -f "${STUB_LOG}"
}

_run_dry() {
  run bash "${SCRIPT}" --plan "${PLAN}" --dry-run
}

_assert_invalid_plan() {
  local contents="$1"
  local invalid_plan="${BATS_TEST_TMPDIR}/invalid-plan.yaml"
  printf '%s\n' "$contents" > "$invalid_plan"
  run bash "${ISOLATED_SCRIPT}" --plan "$invalid_plan" --dry-run
  assert_failure
  assert_output --partial "invalid fleet plan:"
  refute_output --partial "Traceback"
  [ ! -e "${TEST_REPO}/.omc" ]
}

@test "dry-run exits 0" {
  _run_dry
  assert_success
}

@test "dry-run output shows plan id" {
  _run_dry
  assert_output --partial "2026-05-test-rotation"
}

@test "dry-run output mentions upcloud entry" {
  _run_dry
  assert_output --partial "upcloud"
}

@test "dry-run output mentions hetzner entry" {
  _run_dry
  assert_output --partial "hetzner"
}

@test "dry-run STUB_LOG has no terraform apply" {
  _run_dry
  if [[ -s "${STUB_LOG}" ]]; then
    run grep -F "terraform apply" "${STUB_LOG}"
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

@test "dry-run STUB_LOG has no gh release create" {
  _run_dry
  if [[ -s "${STUB_LOG}" ]]; then
    run grep -F "release create" "${STUB_LOG}"
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

@test "valid dry-run does not create a state directory" {
  run bash "${ISOLATED_SCRIPT}" --plan "${PLAN}" --dry-run
  assert_success
  [ ! -e "${TEST_REPO}/.omc" ]
}

@test "rejects malformed YAML and invalid top-level plan shapes" {
  _assert_invalid_plan $'id: [unterminated'
  _assert_invalid_plan $'- not\n- a\n- mapping'
  _assert_invalid_plan $'id: safe\nmin_active: 1'
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations: []\nextra: value'
}

@test "rejects unsafe plan ids before creating state" {
  _assert_invalid_plan $'id: ../escape\nmin_active: 1\nrotations:\n  - current: upcloud:prod\n    new_env: next'
  [ ! -e "${TEST_REPO}/escape.json" ]
}

@test "rejects invalid min_active values" {
  local rotations=$'rotations:\n  - current: upcloud:prod\n    new_env: next'
  _assert_invalid_plan $'id: safe\nmin_active: "1"\n'"$rotations"
  _assert_invalid_plan $'id: safe\nmin_active: true\n'"$rotations"
  _assert_invalid_plan $'id: safe\nmin_active: 0\n'"$rotations"
  _assert_invalid_plan $'id: safe\nmin_active: 2\n'"$rotations"
}

@test "rejects missing empty and non-list rotations" {
  _assert_invalid_plan $'id: safe\nmin_active: 1'
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations: []'
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations: {}'
}

@test "rejects malformed rotation entries" {
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations:\n  - nope'
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations:\n  - current: upcloud:prod'
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations:\n  - current: upcloud:prod\n    new_env: next\n    extra: value'
}

@test "rejects invalid provider current and environment values" {
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations:\n  - current: unknown:prod\n    new_env: next'
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations:\n  - current: upcloud:prod:extra\n    new_env: next'
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations:\n  - current: upcloud:prod_bad\n    new_env: next'
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations:\n  - current: upcloud:prod\n    new_env: ../next'
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations:\n  - current: upcloud:prod\n    new_env: next\n    new_zone: ""'
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations:\n  - current: upcloud:prod\n    new_env: prod'
}

@test "rejects duplicate current entries" {
  _assert_invalid_plan $'id: safe\nmin_active: 1\nrotations:\n  - current: upcloud:prod\n    new_env: next-a\n  - current: upcloud:prod\n    new_env: next-b'
}

@test "refuses a symlink at the state-file path" {
  local state_dir="${TEST_REPO}/.omc/state"
  local target="${BATS_TEST_TMPDIR}/state-target.json"
  mkdir -p "$state_dir"
  printf '%s\n' 'unchanged' > "$target"
  ln -s "$target" "${state_dir}/fleet-rotate-2026-05-test-rotation.json"

  run bash "${ISOLATED_SCRIPT}" --plan "${PLAN}"

  assert_failure
  assert_output --partial "state file is a symlink"
  [ "$(cat "$target")" = "unchanged" ]
  [ ! -s "$STUB_LOG" ]
}
