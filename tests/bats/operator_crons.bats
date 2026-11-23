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
