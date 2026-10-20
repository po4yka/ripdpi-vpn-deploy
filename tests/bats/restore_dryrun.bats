#!/usr/bin/env bats
# Dry-run tests for scripts/restore.sh.
#
# Verifies that --dry-run exits 0, prints procedural steps, and does not
# invoke any destructive stub operations.

load 'test_helper/bats-support/load'
load 'test_helper/bats-assert/load'

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/restore.sh"
STUB_BIN="${REPO_ROOT}/tests/stubs/bin"

setup() {
  STUB_LOG="$(mktemp -t stub_log.XXXXXX)"
  export PATH="${STUB_BIN}:${PATH}"
  export STUB_LOG
}

teardown() {
  rm -f "${STUB_LOG}"
}

# ---------------------------------------------------------------------------
# Path A tests
# ---------------------------------------------------------------------------

@test "path-a: dry-run exits 0" {
  run sh "${SCRIPT}" --dry-run --env prod --provider upcloud --path-a
  assert_success
}

@test "path-a: output mentions env name" {
  run sh "${SCRIPT}" --dry-run --env prod --provider upcloud --path-a
  assert_output --partial "prod"
}

@test "path-a: output mentions make init or make deploy" {
  run sh "${SCRIPT}" --dry-run --env prod --provider upcloud --path-a
  # Path A mentions "make init" and "make deploy" procedural steps
  assert_output --partial "make"
}

@test "path-a: output mentions Path A" {
  run sh "${SCRIPT}" --dry-run --env prod --provider upcloud --path-a
  assert_output --partial "Path A"
}

@test "path-a: STUB_LOG is empty (no destructive stub calls)" {
  run sh "${SCRIPT}" --dry-run --env prod --provider upcloud --path-a
  if [[ -s "${STUB_LOG}" ]]; then
    local log_text
    log_text="$(cat "${STUB_LOG}")"
    fail "unexpected stub calls in dry-run: ${log_text}"
  fi
}

# ---------------------------------------------------------------------------
# Path B tests
# ---------------------------------------------------------------------------

@test "path-b: dry-run exits 0" {
  run sh "${SCRIPT}" --dry-run --env prod --provider upcloud --path-b
  assert_success
}

@test "path-b: output mentions restic" {
  run sh "${SCRIPT}" --dry-run --env prod --provider upcloud --path-b
  assert_output --partial "restic"
}

@test "path-b: output mentions Path B" {
  run sh "${SCRIPT}" --dry-run --env prod --provider upcloud --path-b
  assert_output --partial "Path B"
}

@test "path-b: lists decrypt before the first tagged deploy" {
  run sh "${SCRIPT}" --dry-run --env prod --provider upcloud --path-b
  assert_success

  local decrypt_line playbook_line
  decrypt_line="$(printf '%s\n' "$output" | grep -n -m1 'make decrypt' | cut -d: -f1)"
  playbook_line="$(printf '%s\n' "$output" | grep -n -m1 'ANSIBLE_TAGS="baseline,firewall,backup" make deploy' | cut -d: -f1)"
  [ -n "$decrypt_line" ]
  [ -n "$playbook_line" ]
  [ "$decrypt_line" -lt "$playbook_line" ]
  assert_output --partial 'ANSIBLE_TAGS="baseline,firewall,backup" make deploy'

  # The actual Make/decrypt/controller sequence is covered by
  # test_restore_runtime_secrets_reach_the_first_tagged_deploy in pytest.
}

@test "path-b: STUB_LOG is empty (no destructive stub calls)" {
  run sh "${SCRIPT}" --dry-run --env prod --provider upcloud --path-b
  if [[ -s "${STUB_LOG}" ]]; then
    local log_text
    log_text="$(cat "${STUB_LOG}")"
    fail "unexpected stub calls in dry-run: ${log_text}"
  fi
}

# ---------------------------------------------------------------------------
# Error-case tests
# ---------------------------------------------------------------------------

@test "missing --env flag exits nonzero" {
  run sh "${SCRIPT}" --dry-run --path-a
  assert_failure
}

@test "missing --path flag exits nonzero" {
  run sh "${SCRIPT}" --dry-run --env prod
  assert_failure
}


@test "both recovery paths include current SSH and deployment admission" {
  for path in --path-a --path-b; do
    run sh "${SCRIPT}" --dry-run --env prod "$path"
    assert_success
    assert_output --partial 'make install-ssh-recovery'
    assert_output --partial 'make bootstrap-tailnet'
    assert_output --partial 'TAILNET_HANDOFFS='
    assert_output --partial 'make migrate-ssh-ownership'
    assert_output --partial 'DEPLOY_SSH_CONTEXTS_FILE'
    assert_output --partial 'DEPLOY_PROMOTION_CONFIG_FILE'
    assert_output --partial 'DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE'
    assert_output --partial 'receipt sinks must be fresh and absent'
  done
}

@test "reserved default environment is refused" {
  run sh "${SCRIPT}" --dry-run --env default --path-a
  assert_failure
  assert_output --partial 'default is reserved'
}
