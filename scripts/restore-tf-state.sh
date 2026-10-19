#!/usr/bin/env bash
# Restore the newest exact-environment age backup without truncating live state.
# This local operation does not contact Terraform or a provider.
set -euo pipefail

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case "$PROVIDER" in
  upcloud|hetzner|vultr|scaleway) ;;
  *) echo "unsupported PROVIDER: $PROVIDER" >&2; exit 2 ;;
esac
if [[ ! "$ENV" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ || "$ENV" == "default" ]]; then
  echo 'ENV must be a valid environment; default is reserved for prod' >&2
  exit 2
fi

BACKUP_DEST="${BACKUP_DEST:-${HOME}/.config/vpn-provision/state-backups}"
AGE_IDENTITY="${AGE_IDENTITY:-${HOME}/.config/vpn-provision/age.key}"
shopt -s nullglob
backups=("${BACKUP_DEST}/${PROVIDER}-${ENV}-"[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z.tfstate.age)
if (( ${#backups[@]} == 0 )); then
  echo "no state backup for ${PROVIDER}/${ENV}" >&2
  exit 1
fi
# SC2012: portable mtime ordering; all operands match the exact backup grammar.
# shellcheck disable=SC2012
latest="$(ls -1t "${backups[@]}" | sed -n '1p')"
state_dir="${REPO_ROOT}/terraform/providers/${PROVIDER}"
if [[ "$ENV" != "prod" ]]; then
  state_dir="${state_dir}/terraform.tfstate.d/${ENV}"
fi
state_file="${state_dir}/terraform.tfstate"
[[ -d "$state_dir" && ! -L "$state_file" && ( ! -e "$state_file" || -f "$state_file" ) ]] || {
  echo 'state destination must be an initialized directory without a state symlink' >&2
  exit 1
}
umask 077
pending="$(mktemp "${state_dir}/.state-restore.XXXXXXXX")"
trap 'rm -f -- "$pending"' EXIT
trap 'exit 1' HUP INT TERM
age -d -i "$AGE_IDENTITY" "$latest" > "$pending"
python3 - "$pending" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        state = json.load(stream)
    valid = (
        isinstance(state, dict)
        and type(state.get("version")) is int and state["version"] == 4
        and type(state.get("serial")) is int and state["serial"] >= 0
        and isinstance(state.get("lineage"), str) and bool(state["lineage"])
        and isinstance(state.get("resources"), list)
    )
except (OSError, ValueError, UnicodeError):
    valid = False
if not valid:
    sys.exit("restored Terraform state has an invalid structure")
PY
mv -f -- "$pending" "$state_file"
echo "restored state for ${PROVIDER}/${ENV}; review a Terraform plan before applying"
