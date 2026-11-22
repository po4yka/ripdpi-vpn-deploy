#!/usr/bin/env bash
# Prove the OpenTofu backend lock on a state bucket before any migration.
#
# Runs a disposable encrypted root under state/_probe/ with three identities:
#   writer        creates state, then holds the lock during a slow apply
#   other-writer  must be refused while the lock is held, then re-acquire it
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

hold=40
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-config) backend=$2; shift 2 ;;
    --writer) writer=$2; shift 2 ;;
    --other-writer) other=$2; shift 2 ;;
    --reader) reader=$2; shift 2 ;;
    --passphrase) passphrase=$2; shift 2 ;;
    --hold) hold=$2; shift 2 ;;
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
    command = "sleep ${var.hold}"
  }
}
EOF

# client <identity-doc> <client-name> <tofu args...>
client() {
  local doc=$1 name=$2
  shift 2
  mkdir -p "$work/$name"
  cp "$work/main.tf" "$work/$name/main.tf"
  TF_DATA_DIR="$work/$name/.data" TF_IN_AUTOMATION=1 CHECKPOINT_DISABLE=1 \
    sops exec-env "$doc" "$(printf '%q ' "$0" __with-passphrase "$passphrase" "$work/$name" "$@")"
}
lock_refused() { grep -q "Error acquiring the state lock" "$1"; }

failures=0
check() { # check <label> <pass|fail>
  printf '%s: %s\n' "$1" "$2"
  [[ "$2" == pass ]] || failures=$((failures + 1))
}

for pair in writer:"$writer" other:"$other" reader:"$reader"; do
  name=${pair%%:*} doc=${pair#*:}
  if client "$doc" "$name" init -input=false -no-color "-backend-config=$backend" \
       "-backend-config=key=state/_probe/terraform.tfstate" > "$work/$name-init.log" 2>&1; then
    check "$name init" pass
  else
    check "$name init" fail
    exit 1
  fi
done

client "$writer" writer apply -auto-approve -input=false -no-color -var hold=1 > "$work/create.log" 2>&1 \
  && check "writer creates encrypted state" pass || check "writer creates encrypted state" fail

client "$writer" writer apply -auto-approve -input=false -no-color -var "hold=$hold" > "$work/hold.log" 2>&1 &
holder=$!
sleep $(( hold / 3 + 1 ))
if client "$other" other plan -input=false -no-color -lock-timeout=0s -var "hold=$hold" > "$work/contend.log" 2>&1; then
  check "other writer refused while the lock is held" fail
elif lock_refused "$work/contend.log"; then
  check "other writer refused while the lock is held" pass
else
  check "other writer refused while the lock is held" fail
fi
wait "$holder" && check "writer releases the lock" pass || check "writer releases the lock" fail

client "$other" other apply -auto-approve -input=false -no-color -var hold=2 > "$work/reacquire.log" 2>&1 \
  && check "other writer re-acquires the lock" pass || check "other writer re-acquires the lock" fail

client "$reader" reader plan -lock=false -input=false -no-color -var hold=2 > "$work/read.log" 2>&1 \
  && check "reader plans without the lock" pass || check "reader plans without the lock" fail

if client "$reader" reader plan -lock-timeout=0s -input=false -no-color -var hold=2 > "$work/reader-lock.log" 2>&1; then
  check "reader cannot take the lock" fail
elif lock_refused "$work/reader-lock.log"; then
  check "reader cannot take the lock" pass
else
  check "reader cannot take the lock" fail
fi

(( failures == 0 )) || { echo "lock probe failed: $failures check(s)" >&2; exit 1; }
echo "lock probe passed"
