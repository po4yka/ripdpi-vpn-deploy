#!/usr/bin/env bash
# Prove the OpenTofu backend lock on a state bucket before any migration.
#
# Runs a disposable encrypted root under state/_probe/ with three identities:
#   writer        creates state, then holds the lock during a slow apply
#   other-writer  operator: contend, re-acquire the lock, and inspect retained versions
#   reader        must plan with -lock=false and must fail to take the lock
# Each identity and the state passphrase come from SOPS documents and reach
# tofu only through `sops exec-env`; nothing secret is printed.
#
# Usage:
#   scripts/state-lock-probe.sh --backend-config <file.s3.tfbackend> \
#     --writer <doc> --other-writer <doc> --reader <doc> --passphrase <doc> [--hold <seconds>]
# Exit 0 when every check passes, 1 when a check fails, 2 on usage errors.
set -euo pipefail
umask 077

unset TF_WORKSPACE
hold=40
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-config) backend=$2; shift 2 ;;
    --writer) writer=$2; shift 2 ;;
    --other-writer) other=$2; shift 2 ;;
    --reader) reader=$2; shift 2 ;;
    --passphrase) passphrase=$2; shift 2 ;;
    --hold) hold=$2; shift 2 ;;
    __inspect-probe)
      exec sops exec-env "$2" "$(printf '%q ' "$(dirname "$0")/restore-tf-state.py" --inspect-probe "$3" "$4" "$5")"
      ;;
    __with-passphrase)
      # Inner hop: identity variables are set; add the passphrase and run tofu.
      shift
      pass_doc=$1 dir=$2
      shift 2
      exec sops exec-env "$pass_doc" "$(printf '%q ' tofu "-chdir=$dir" "$@")"
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
for name in backend writer other reader passphrase; do
  [[ -n "${!name:-}" && -f "${!name}" ]] || { echo "missing or unreadable --${name//_/-} input" >&2; exit 2; }
done
[[ "$hold" =~ ^[1-9][0-9]*$ ]] || { echo "--hold must be a positive integer" >&2; exit 2; }

work="$(mktemp -d "${TMPDIR:-/tmp}/state-lock-probe.XXXXXX")"
trap 'rm -rf -- "$work"' EXIT
cp -- "$backend" "$work/probe.s3.tfbackend"
backend="$work/probe.s3.tfbackend"
probe_key="state/_probe/${work##*.}/terraform.tfstate"
cat > "$work/main.tf" <<'EOF'
terraform {
  backend "s3" {}
  encryption {
    key_provider "pbkdf2" "state" {
      passphrase = var.state_passphrase
    }
    method "aes_gcm" "state" {
      keys = key_provider.pbkdf2.state
    }
    state {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}

variable "state_passphrase" {
  type      = string
  sensitive = true
  ephemeral = true
}

variable "hold" {
  type    = number
  default = 0
}

# Replacing on every hold change runs the create-time provisioner, so the
# apply keeps the lock for the whole sleep.
resource "terraform_data" "probe" {
  input            = var.hold
  triggers_replace = var.hold
  provisioner "local-exec" {
    command = "touch \"$PROBE_HOLDER_READY\" && sleep ${var.hold}"
  }
}
EOF

# client <identity-doc> <client-name> <tofu args...>
client() {
  local doc=$1 name=$2
  shift 2
  mkdir -p "$work/$name"
  cp "$work/main.tf" "$work/$name/main.tf"
  PROBE_HOLDER_READY="$work/holder-ready" TF_DATA_DIR="$work/$name/.data" TF_IN_AUTOMATION=1 CHECKPOINT_DISABLE=1 \
    sops exec-env "$doc" "$(printf '%q ' "$0" __with-passphrase "$passphrase" "$work/$name" "$@")"
}
lock_refused() { grep -q "Error acquiring the state lock" "$1"; }

failures=0
check() { # check <label> <pass|fail>
  printf '%s: %s\n' "$1" "$2"
  [[ "$2" == pass ]] || failures=$((failures + 1))
}

record() {
  local label=$1 log=$2
  shift 2
  if "$@" > "$log" 2>&1; then
    check "$label" pass
  else
    check "$label" fail
  fi
}

for pair in writer:"$writer" other:"$other" reader:"$reader"; do
  name=${pair%%:*} doc=${pair#*:}
  if client "$doc" "$name" init -input=false -no-color "-backend-config=$backend" \
       "-backend-config=key=$probe_key" "-backend-config=skip_s3_checksum=false" > "$work/$name-init.log" 2>&1; then
    check "$name init" pass
  else
    check "$name init" fail
    exit 1
  fi
done

for workspace in default "probe-${work##*.}"; do
  if [[ "$workspace" != default ]]; then
    for pair in writer:"$writer" other:"$other" reader:"$reader"; do
      name=${pair%%:*} doc=${pair#*:}
      action=select
      [[ "$name" != writer ]] || action=new
      if ! client "$doc" "$name" workspace "$action" "$workspace" > "$work/$name-workspace.log" 2>&1; then
        echo "$name cannot $action the named probe workspace" >&2
        exit 1
      fi
    done
  fi
  printf 'workspace %s\n' "$workspace"
  record "writer creates state with SDK checksums" "$work/create.log" \
    client "$writer" writer apply -auto-approve -input=false -no-color -var hold=0

  rm -f -- "$work/holder-ready"
  client "$writer" writer apply -auto-approve -input=false -no-color -var "hold=$hold" > "$work/hold.log" 2>&1 &
  holder=$!
  for ((attempt = 0; attempt < 600; attempt++)); do
    if [[ -e "$work/holder-ready" ]] || ! kill -0 "$holder" 2>/dev/null; then break; fi
    sleep 0.2
  done
  [[ -e "$work/holder-ready" ]] || { wait "$holder" || true; echo "holder did not reach the locked apply" >&2; exit 1; }
  if client "$other" other plan -input=false -no-color -lock-timeout=0s -var "hold=$hold" > "$work/contend.log" 2>&1; then
    check "other writer refused while the lock is held" fail
  elif lock_refused "$work/contend.log"; then
    check "other writer refused while the lock is held" pass
  else
    check "other writer refused while the lock is held" fail
  fi
  record "writer releases the lock" "$work/wait.log" wait "$holder"

  record "other writer re-acquires the lock" "$work/reacquire.log" \
    client "$other" other apply -auto-approve -input=false -no-color -var hold=0

  record "reader plans without the lock" "$work/read.log" \
    client "$reader" reader plan -lock=false -input=false -no-color -var hold=0

  if client "$reader" reader plan -lock-timeout=0s -input=false -no-color -var hold=0 > "$work/reader-lock.log" 2>&1; then
    check "reader cannot take the lock" fail
  elif lock_refused "$work/reader-lock.log"; then
    check "reader cannot take the lock" pass
  else
    check "reader cannot take the lock" fail
  fi

  if sops exec-env "$other" "$(printf '%q ' "$0" __inspect-probe "$passphrase" "$backend" "$probe_key" "$workspace")"; then
    check "bucket retains encrypted state versions" pass
  else
    check "bucket retains encrypted state versions" fail
  fi
done

(( failures == 0 )) || { echo "lock probe failed: $failures check(s)" >&2; exit 1; }
echo "lock probe passed"
