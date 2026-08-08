#!/usr/bin/env bats

@test "new-client rejects shell metacharacters before reading secrets" {
  run env SOPS_FILE=/definitely/missing ./scripts/new-client.sh 'phone;touch /tmp/should-not-exist'
  [ "$status" -ne 0 ]
  [[ "$output" == *"client name must contain"* ]]
  [ ! -e /tmp/should-not-exist ]
}

@test "fleet rotation reads a plan path as an argv value" {
  plan="$BATS_TEST_TMPDIR/plan;not-executed.yaml"
  printf '%s\n' 'id: safe' 'min_active: 1' 'rotations: []' > "$plan"
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

@test "operator cron installs standalone protocol monitor without warm spare" {
  config="$BATS_TEST_TMPDIR/liveness.yaml"
  printf '%s\n' 'schema_version: 1' > "$config"

  run env \
    LIVENESS_CONFIG="$config" \
    SOPS_FILE="$BATS_TEST_TMPDIR/prod.secrets.sops.yaml" \
    SOPS_AGE_KEY_FILE="$BATS_TEST_TMPDIR/age.key" \
    OPERATOR_PATH=/custom/bin:/usr/bin:/bin \
    ./scripts/install-operator-crons.sh --dry-run

  [ "$status" -eq 0 ]
  [[ "$output" == *"make monitor-protocol-liveness"* ]]
  [[ "$output" != *"make watch-spare"* ]]
  [[ "$output" == *"$config"* ]]
  [[ "$output" == *"$BATS_TEST_TMPDIR/prod.secrets.sops.yaml"* ]]
  [[ "$output" == *"$BATS_TEST_TMPDIR/age.key"* ]]
  [[ "$output" == *'PATH="/custom/bin:/usr/bin:/bin"'* ]]
}
