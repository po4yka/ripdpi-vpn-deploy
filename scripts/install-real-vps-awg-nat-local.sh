#!/usr/bin/env bash
# Install the local recurring AWG/NAT lane from one exact repository commit.
set -euo pipefail

usage() {
  echo "usage: sudo $0 --repo /path/to/ripdpi-vpn-deploy" >&2
  exit 2
}

REPO=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

[[ "$EUID" -eq 0 ]] || { echo "installer must run as root" >&2; exit 1; }
[[ -n "$REPO" ]] || usage
LOCK_DIR="/run/lock/ripdpi-real-vps-awg-nat"
install -d -o root -g root -m 0700 "$LOCK_DIR"
exec 9>"$LOCK_DIR/lane.lock"
flock -n 9 || {
  echo "real-VPS AWG/NAT lane is currently running or being installed" >&2
  exit 75
}
REPO="$(cd "$REPO" && pwd -P)"
[[ -d "$REPO/.git" ]] || { echo "not a Git checkout: $REPO" >&2; exit 1; }
git -C "$REPO" diff-index --quiet HEAD -- || { echo "tracked source changes must be committed first" >&2; exit 1; }
source_sha="$(git -C "$REPO" rev-parse --verify 'HEAD^{commit}')"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid source SHA" >&2; exit 1; }
SOURCE_CONFIG="/etc/ripdpi/real-vps-awg-nat.json"
INSTALLED_CONFIG="/etc/ripdpi/real-vps-awg-nat-local.json"
[[ -f "$SOURCE_CONFIG" && ! -L "$SOURCE_CONFIG" ]] || {
  echo "/etc/ripdpi/real-vps-awg-nat.json must exist before enabling the timer" >&2
  exit 1
}
[[ "$(stat -c '%u:%a' "$SOURCE_CONFIG")" == "0:600" ]] || {
  echo "private runner config must be root-owned mode 0600" >&2
  exit 1
}

mapfile -d '' -t hook_sources < <(python3 - "$SOURCE_CONFIG" <<'PY'
import json
import pathlib
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text())
for key in ("serverControlHook", "serverDeployHook", "rotationHook"):
    path = value.get(key)
    if not isinstance(path, str) or "\0" in path:
        raise SystemExit(f"invalid private hook mapping: {key}")
    sys.stdout.write(path + "\0")
PY
)
[[ "${#hook_sources[@]}" -eq 3 ]] || { echo "private hook mapping is incomplete" >&2; exit 1; }

validate_root_hook() {
  local candidate="$1" resolved cursor mode
  [[ "$candidate" = /* && -f "$candidate" && -x "$candidate" && ! -L "$candidate" ]] || return 1
  resolved="$(readlink -e "$candidate")" || return 1
  cursor="$resolved"
  while :; do
    [[ "$(stat -c '%u' "$cursor")" == "0" ]] || return 1
    mode="$((8#$(stat -c '%a' "$cursor")))"
    (( (mode & 8#022) == 0 )) || return 1
    [[ "$cursor" == "/" ]] && break
    cursor="$(dirname "$cursor")"
  done
  mode="$((8#$(stat -c '%a' "$resolved")))"
  (( (mode & 8#077) == 0 && (mode & 8#100) != 0 )) || return 1
  VALIDATED_ROOT_HOOK="$resolved"
}
for index in 0 1 2; do
  validate_root_hook "${hook_sources[$index]}" || { echo "private hook path chain is unsafe" >&2; exit 1; }
  hook_sources[index]="$VALIDATED_ROOT_HOOK"
done
rm -f -- \
  /var/lib/ripdpi-real-vps-awg-nat/evidence/latest.json \
  /var/lib/ripdpi-real-vps-awg-nat/evidence/.latest.json.tmp

source_base="/opt/ripdpi-real-vps-awg-nat"
source_dir="$source_base/sources/$source_sha"
if [[ ! -d "$source_dir/.git" ]]; then
  install -d -o root -g root -m 0755 "$source_base/sources"
  staging="$(mktemp -d "$source_base/sources/.install.XXXXXX")"
  trap 'rm -rf -- "$staging"' EXIT
  git clone --quiet --no-hardlinks --no-checkout "$REPO" "$staging/source"
  git -C "$staging/source" checkout --quiet --detach "$source_sha"
  git -C "$staging/source" remote remove origin
  chown -R root:root "$staging/source"
  chmod -R go-w "$staging/source"
  mv -- "$staging/source" "$source_dir"
  rm -rf -- "$staging"
  trap - EXIT
fi
[[ "$(git -C "$source_dir" rev-parse --verify 'HEAD^{commit}')" == "$source_sha" ]] || {
  echo "existing immutable source snapshot does not match $source_sha" >&2
  exit 1
}
git -C "$source_dir" diff-index --quiet HEAD -- || {
  echo "existing immutable source snapshot has tracked changes" >&2
  exit 1
}
[[ "$(stat -c '%u' "$source_dir" "$source_dir/.git")" == $'0\n0' ]] || {
  echo "immutable source snapshot is not root-owned" >&2
  exit 1
}
[[ -z "$(find "$source_dir" "$source_dir/.git" -maxdepth 0 -perm /022 -print -quit)" ]] || {
  echo "immutable source snapshot is group/other writable" >&2
  exit 1
}

ln -sfn "sources/$source_sha" "$source_base/.current.tmp"
mv -Tf -- "$source_base/.current.tmp" "$source_base/current"

install -o root -g root -m 0755 \
  "$source_dir/scripts/real-vps-awg-nat.py" \
  /usr/local/libexec/ripdpi-real-vps-awg-nat
install -o root -g root -m 0755 \
  "$source_dir/scripts/run-real-vps-awg-nat-local.sh" \
  /usr/local/libexec/ripdpi-real-vps-awg-nat-local
hook_dir="/usr/local/libexec/ripdpi-real-vps-awg-nat-hooks"
install -d -o root -g root -m 0700 "$hook_dir"
installed_hooks=(
  "$hook_dir/server-control"
  "$hook_dir/server-deploy"
  "$hook_dir/rotation"
)
for index in 0 1 2; do
  install -o root -g root -m 0700 \
    "${hook_sources[$index]}" "${installed_hooks[$index]}"
done
config_tmp="$(mktemp /etc/ripdpi/.real-vps-awg-nat-local.XXXXXX)"
trap 'rm -f -- "$config_tmp"' EXIT
python3 - "$SOURCE_CONFIG" "$config_tmp" "${installed_hooks[@]}" <<'PY'
import json
import pathlib
import sys

source, output, control, deploy, rotation = sys.argv[1:]
value = json.loads(pathlib.Path(source).read_text())
value["serverControlHook"] = control
value["serverDeployHook"] = deploy
value["rotationHook"] = rotation
pathlib.Path(output).write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
PY
install -o root -g root -m 0600 "$config_tmp" "$INSTALLED_CONFIG"
rm -f -- "$config_tmp"
trap - EXIT
install -o root -g root -m 0644 \
  "$source_dir/scripts/systemd/ripdpi-real-vps-awg-nat.service" \
  /etc/systemd/system/ripdpi-real-vps-awg-nat.service
install -o root -g root -m 0644 \
  "$source_dir/scripts/systemd/ripdpi-real-vps-awg-nat.timer" \
  /etc/systemd/system/ripdpi-real-vps-awg-nat.timer
install -o root -g root -m 0644 \
  "$source_dir/scripts/tmpfiles.d/ripdpi-real-vps-awg-nat.conf" \
  /usr/lib/tmpfiles.d/ripdpi-real-vps-awg-nat.conf

systemd-tmpfiles --create ripdpi-real-vps-awg-nat.conf
systemctl daemon-reload
systemd-analyze verify \
  /etc/systemd/system/ripdpi-real-vps-awg-nat.service \
  /etc/systemd/system/ripdpi-real-vps-awg-nat.timer
systemctl enable --now ripdpi-real-vps-awg-nat.timer
echo "installed recurring AWG/NAT lane at source $source_sha"
