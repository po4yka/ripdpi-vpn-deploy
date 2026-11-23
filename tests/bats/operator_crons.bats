#!/usr/bin/env bats

setup() {
  cd "$BATS_TEST_DIRNAME/../.." || return 1
  mkdir -p "$BATS_TEST_TMPDIR/bin"
  export PATH="$BATS_TEST_TMPDIR/bin:$PATH"
  export TABLE="$BATS_TEST_TMPDIR/table"
  cat > "$BATS_TEST_TMPDIR/bin/crontab" <<'STUB'
#!/usr/bin/env bash
case "$1" in
  -l)
    if [[ ${READ_ERROR:-0} == 1 ]]; then
      echo 'partial crontab'
      echo 'crontab: permission denied' >&2
      exit 1
    fi
    if [[ ! -e "$TABLE" ]]; then
      echo "crontab: no crontab for $(id -un)" >&2
      exit 1
    fi
    cat "$TABLE" ;;
  -) cat > "$TABLE" ;;
  *) exit 2 ;;
esac
STUB
  chmod +x "$BATS_TEST_TMPDIR/bin/crontab"
}

@test "absent crontab permits first install and repeated removal" {
  run scripts/install-operator-crons.sh --remove
  [ "$status" -eq 0 ]
  [ ! -e "$TABLE" ]
  run scripts/install-operator-crons.sh
  [ "$status" -eq 0 ]
  grep -q 'make tspu-canary' "$TABLE"
  printf '0 0 * * * date\n' >> "$TABLE"
  run scripts/install-operator-crons.sh --remove
  [ "$status" -eq 0 ]
  [ "$(cat "$TABLE")" = '0 0 * * * date' ]
}

@test "failed crontab read leaves existing entries intact on install and removal" {
  echo '0 0 * * * date' > "$TABLE"
  for action in install remove; do
    args=()
    if [ "$action" = remove ]; then args=(--remove); fi
    run env READ_ERROR=1 scripts/install-operator-crons.sh "${args[@]}"
    [ "$status" -ne 0 ]
    [[ "$output" == *'permission denied'* ]]
    [ "$(cat "$TABLE")" = '0 0 * * * date' ]
  done
}

@test "truncated managed block leaves unrelated entries intact" {
  printf '# vpn-deploy: BEGIN — managed block, do not edit\n0 0 * * * date\n' > "$TABLE"
  cp "$TABLE" "$TABLE.before"
  run scripts/install-operator-crons.sh
  [ "$status" -ne 0 ]
  cmp "$TABLE" "$TABLE.before"
}

@test "every syslog job reports producer and logger failures under the cron shell" {
  config="$BATS_TEST_TMPDIR/config"
  touch "$config"
  export MONITOR_STATE_IDENTITY_SOPS_FILE="$config" STATE_PASSPHRASE_SOPS_FILE="$config"
  export STATE_IDENTITY_SOPS_FILE="$config" SELF_STEAL_SOPS_FILE="$config" SELF_STEAL_DNS_ENV_FILE="$config"
  export REALITY_TARGET_VANTAGE=filtered-test LIVENESS_CONFIG="$config"
  for tool in make sops; do
    printf '#!/bin/sh\nprintf "job diagnostic\\n" >&2\nexit "$JOB_STATUS"\n' > "$BATS_TEST_TMPDIR/bin/$tool"
  done
  printf '#!/bin/sh\ncat > "$TABLE.logged"\nexit "$LOG_STATUS"\n' > "$BATS_TEST_TMPDIR/bin/logger"
  chmod +x "$BATS_TEST_TMPDIR/bin/"*
  for spare in '' standby; do
    WARM_SPARE_ENV="$spare" scripts/install-operator-crons.sh --dry-run > "$TABLE.preview"
    count=0
    while IFS= read -r command; do
      run env JOB_STATUS=23 LOG_STATUS=0 sh -c "$command"
      [ "$status" -eq 23 ]
      [ "$(cat "$TABLE.logged")" = 'job diagnostic' ]
      run env JOB_STATUS=0 LOG_STATUS=19 sh -c "$command"
      [ "$status" -eq 19 ]
      count=$((count + 1))
    done < <(awk '/^[0-9*]/ {sub(/^([^[:space:]]+[[:space:]]+){5}/,""); print}' "$TABLE.preview")
    [ "$count" -eq 9 ]
  done
}
