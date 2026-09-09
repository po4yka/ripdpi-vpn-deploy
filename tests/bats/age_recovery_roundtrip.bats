#!/usr/bin/env bats
# Roundtrip tests for scripts/age-recovery-combine.sh.
#
# Verifies that any 3-of-5 Shamir shares reconstruct the correct age private
# key. Tests two different 3-share subsets and checks fixture consistency.

load 'test_helper/bats-support/load'
load 'test_helper/bats-assert/load'

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/age-recovery-combine.sh"
SHARES_DIR="${REPO_ROOT}/tests/fixtures/age-recovery-shares"
AGE_KEY_FILE="${REPO_ROOT}/tests/fixtures/age-test.key"
EXPECTED_KEY="AGE-SECRET-KEY-1V070XMWMW3TKQZFQCEUK8ZV82VFRD4EG8Z7LHECG5VP7CXP7XP2QMMQY9M"

setup() {
  command -v ssss-combine >/dev/null 2>&1 \
    || skip "ssss-combine not installed; install it (e.g. 'brew install ssss' / 'apt-get install ssss') to run the recovery roundtrip"
}

# Load share N (1-indexed), stripping trailing whitespace
_load_share() {
  local n="$1"
  tr -d '[:space:]' < "${SHARES_DIR}/share-${n}.txt"
}

# Run age-recovery-combine.sh with given shares fed via stdin
_combine() {
  local threshold="$1"
  shift
  local stdin_text=""
  for share in "$@"; do
    stdin_text="${stdin_text}${share}
"
  done
  run bash "${SCRIPT}" "${threshold}" <<< "${stdin_text}"
}

@test "shares 1 3 5 reconstruct the correct key" {
  local s1 s3 s5
  s1="$(_load_share 1)"
  s3="$(_load_share 3)"
  s5="$(_load_share 5)"
  _combine 3 "${s1}" "${s3}" "${s5}"
  assert_success
  assert_output --partial "${EXPECTED_KEY}"
}

@test "shares 2 4 5 reconstruct the correct key (any-3-of-5)" {
  local s2 s4 s5
  s2="$(_load_share 2)"
  s4="$(_load_share 4)"
  s5="$(_load_share 5)"
  _combine 3 "${s2}" "${s4}" "${s5}"
  assert_success
  assert_output --partial "${EXPECTED_KEY}"
}

@test "shares 1 2 3 reconstruct key matching age-test.key fixture" {
  # Verify fixture consistency: the key line in age-test.key matches EXPECTED_KEY
  local key_line
  key_line="$(grep '^AGE-SECRET-KEY-' "${AGE_KEY_FILE}")"
  [ "${key_line}" = "${EXPECTED_KEY}" ]

  local s1 s2 s3
  s1="$(_load_share 1)"
  s2="$(_load_share 2)"
  s3="$(_load_share 3)"
  _combine 3 "${s1}" "${s2}" "${s3}"
  assert_success
  assert_output --partial "${key_line}"
}
