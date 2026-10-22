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
}

teardown() {
  rm -f "${STUB_LOG}"
}

_run_dry() {
  run bash "${SCRIPT}" --plan "${PLAN}" --dry-run
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

@test "dry-run neither creates state nor reads a missing health configuration" {
  checkout="$BATS_TEST_TMPDIR/checkout"
  mkdir -p "$checkout/scripts"
  cp "$SCRIPT" "$REPO_ROOT/scripts/fleet_rotation.py" \
    "$REPO_ROOT/scripts/fleet_rotation_liveness.py" \
    "$REPO_ROOT/scripts/fleet_inspection.py" \
    "$REPO_ROOT/scripts/bootstrap_readiness.py" "$checkout/scripts/"
  cp "$PLAN" "$checkout/plan.yaml"
  run bash "$checkout/scripts/fleet-rotate.sh" --plan "$checkout/plan.yaml" --dry-run
  assert_success
  [ ! -e "$checkout/.omc" ]
  [ ! -e "$checkout/liveness.yaml" ]
}

@test "dry-run rejects duplicate keys instead of accepting a changed safety floor" {
  plan="$BATS_TEST_TMPDIR/duplicate.yaml"
  cp "$PLAN" "$plan"
  printf '\nmin_active: 0\n' >> "$plan"
  run bash "$SCRIPT" --plan "$plan" --dry-run
  assert_failure
  assert_output --partial "duplicate-or-invalid-mapping"
}

@test "dry-run refuses legacy unbound plans" {
  plan="$BATS_TEST_TMPDIR/legacy.yaml"
  printf '%s\n' 'id: old-plan' 'min_active: 1' 'rotations: []' > "$plan"
  run bash "$SCRIPT" --plan "$plan" --dry-run
  assert_failure
  assert_output --partial "invalid-plan"
}
