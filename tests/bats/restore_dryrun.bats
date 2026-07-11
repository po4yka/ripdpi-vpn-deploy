#!/usr/bin/env bats
# Safety and sequencing tests for scripts/restore.sh. Execution tests use only
# a per-test make stub and never contact a provider or read real secrets.

load 'test_helper/bats-support/load'
load 'test_helper/bats-assert/load'

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/restore.sh"

setup() {
  STUB_LOG="${BATS_TEST_TMPDIR}/make.log"
  : > "$STUB_LOG"
  export STUB_LOG
  export HOME="${BATS_TEST_TMPDIR}/home"
  mkdir -p "$HOME"
}

make_stub() {
  mkdir -p "${BATS_TEST_TMPDIR}/bin"
  MAKE_STUB="${BATS_TEST_TMPDIR}/bin/make"
  cat > "$MAKE_STUB" <<'SH'
#!/bin/sh
target="${1:?target required}"
printf '%s\n' "$target" >> "$STUB_LOG"
if [ "${RECOVERY_STUB_FAIL_TARGET:-}" = "$target" ]; then
  exit 23
fi
SH
  chmod +x "$MAKE_STUB"
}

@test "Path A dry-run is nonmutating and identifies its environment" {
  run sh "$SCRIPT" --dry-run --env prod --provider upcloud --path-a
  assert_success
  assert_output --partial "Path A"
  assert_output --partial "production-shaped"
  assert_output --partial "PROVIDER=upcloud"
  [ ! -s "$STUB_LOG" ]
}

@test "Path B dry-run remains a nonmutating manual restic procedure" {
  run sh "$SCRIPT" --dry-run --env prod --provider upcloud --path-b
  assert_success
  assert_output --partial "Path B"
  assert_output --partial "restic"
  [ ! -s "$STUB_LOG" ]

  local decrypt_line playbook_line
  decrypt_line="$(printf '%s\n' "$output" | grep -n -m1 'make decrypt' | cut -d: -f1)"
  playbook_line="$(printf '%s\n' "$output" | grep -n -m1 'ANSIBLE_TAGS="baseline,firewall,backup" make deploy' | cut -d: -f1)"
  [ -n "$decrypt_line" ]
  [ -n "$playbook_line" ]
  [ "$decrypt_line" -lt "$playbook_line" ]

  run make -n -C "$REPO_ROOT" deploy ENV=prod RUNTIME_DIR=/tmp/restore-test \
    ANSIBLE_TAGS=baseline,firewall,backup
  assert_success
  assert_output --partial 'VPN_SECRETS_FILE=/tmp/restore-test/vpn-prod.secrets.yaml'
  assert_output --partial 'ansible-playbook ansible/playbooks/site.yml --tags "baseline,firewall,backup"'
}

@test "missing environment or path and mutually exclusive paths fail" {
  run sh "$SCRIPT" --dry-run --path-a
  assert_failure 2
  run sh "$SCRIPT" --dry-run --env prod
  assert_failure 2
  run sh "$SCRIPT" --dry-run --env prod --path-a --path-b
  assert_failure 2
}

@test "invalid provider and environment slugs fail before commands" {
  run sh "$SCRIPT" --dry-run --env prod --provider unknown --path-a
  assert_failure 2
  run sh "$SCRIPT" --dry-run --env 'bad/env' --provider upcloud --path-a
  assert_failure 2
  [ ! -s "$STUB_LOG" ]
}

@test "omitting dry-run and guarded execution fails closed" {
  run sh "$SCRIPT" --env prod --provider upcloud --path-a
  assert_failure 2
  assert_output --partial "choose --dry-run or the guarded --execute-ephemeral"
}

@test "ephemeral execution rejects production-shaped environments" {
  make_stub
  run env RECOVERY_MAKE="$MAKE_STUB" sh "$SCRIPT" --env prod --provider upcloud \
    --path-a --execute-ephemeral --confirm-env prod
  assert_failure 2
  assert_output --partial "requires a ci-* environment"
  [ ! -s "$STUB_LOG" ]
}

@test "ephemeral execution requires an exact environment confirmation" {
  make_stub
  run env RECOVERY_MAKE="$MAKE_STUB" sh "$SCRIPT" --env ci-recovery --provider upcloud \
    --path-a --execute-ephemeral
  assert_failure 2
  run env RECOVERY_MAKE="$MAKE_STUB" sh "$SCRIPT" --env ci-recovery --provider upcloud \
    --path-a --execute-ephemeral --confirm-env ci-other
  assert_failure 2
  [ ! -s "$STUB_LOG" ]
}

@test "ephemeral execution rejects Path B" {
  make_stub
  run env RECOVERY_MAKE="$MAKE_STUB" sh "$SCRIPT" --env ci-recovery --provider upcloud \
    --path-b --execute-ephemeral --confirm-env ci-recovery
  assert_failure 2
  assert_output --partial "supports Path A only"
  [ ! -s "$STUB_LOG" ]
}

@test "dry-run and ephemeral execution are mutually exclusive" {
  make_stub
  run env RECOVERY_MAKE="$MAKE_STUB" sh "$SCRIPT" --env ci-recovery --provider upcloud \
    --path-a --dry-run --execute-ephemeral --confirm-env ci-recovery
  assert_failure 2
  [ ! -s "$STUB_LOG" ]
}

@test "ephemeral Path A executes the exact make target order" {
  make_stub
  run env RECOVERY_MAKE="$MAKE_STUB" sh "$SCRIPT" --env ci-recovery --provider upcloud \
    --path-a --execute-ephemeral --confirm-env ci-recovery
  assert_success
  assert_equal "$(cat "$STUB_LOG")" $'decrypt\npre-deploy-check\ninit\nplan\napply\ninventory\nwait\ndry-run\ndeploy\nverify\nclean'
  assert_output --partial "ephemeral Path A execution spike verified"
}

@test "pre-apply failure stops without a preservation warning" {
  make_stub
  run env RECOVERY_MAKE="$MAKE_STUB" RECOVERY_STUB_FAIL_TARGET=plan \
    sh "$SCRIPT" --env ci-recovery --provider upcloud --path-a \
    --execute-ephemeral --confirm-env ci-recovery
  assert_failure 23
  assert_equal "$(cat "$STUB_LOG")" $'decrypt\npre-deploy-check\ninit\nplan'
  refute_output --partial "ephemeral node may remain"
}

@test "post-apply failure stops and preserves the ephemeral node for manual cleanup" {
  make_stub
  run env RECOVERY_MAKE="$MAKE_STUB" RECOVERY_STUB_FAIL_TARGET=deploy \
    sh "$SCRIPT" --env ci-recovery --provider upcloud --path-a \
    --execute-ephemeral --confirm-env ci-recovery
  assert_failure 23
  assert_equal "$(cat "$STUB_LOG")" $'decrypt\npre-deploy-check\ninit\nplan\napply\ninventory\nwait\ndry-run\ndeploy'
  assert_output --partial "ephemeral node may remain"
  assert_output --partial "PROVIDER=upcloud ENV=ci-recovery make destroy"
  refute_line "destroy"
}
