#!/usr/bin/env bats

@test "new-client rejects shell metacharacters before reading secrets" {
  run env SOPS_FILE=/definitely/missing ./scripts/new-client.sh 'phone;touch /tmp/should-not-exist'
  [ "$status" -ne 0 ]
  [[ "$output" == *"client name must contain"* ]]
  [ ! -e /tmp/should-not-exist ]
}

@test "fleet rotation reads a plan path as an argv value" {
  plan="$BATS_TEST_TMPDIR/plan;not-executed.yaml"
  printf '%s\n' 'id: safe' 'min_active: 1' 'rotations:' '  - current: upcloud:prod' '    new_env: next' > "$plan"
  run ./scripts/fleet-rotate.sh --plan "$plan" --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"plan id=safe"* ]]
}

@test "Make passes client values as one argv argument" {
  marker="$BATS_TEST_TMPDIR/make-client-injection"
  run make emit-singbox "CLIENT=phone;touch $marker"
  [ "$status" -ne 0 ]
  [ ! -e "$marker" ]
}
