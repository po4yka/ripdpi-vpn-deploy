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
umask 077
LOCK_DIR="/run/lock/ripdpi-real-vps-awg-nat"
install -d -o root -g root -m 0700 "$LOCK_DIR"
exec 9>"$LOCK_DIR/lane.lock"
chmod 0600 "$LOCK_DIR/lane.lock"
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
CLIENT_ACCEPTANCE_PUBLIC_KEY="/etc/ripdpi/real-vps-awg-client-acceptance.pub"
RUNNER="/usr/local/libexec/ripdpi-real-vps-awg-nat"
[[ -f "$SOURCE_CONFIG" && ! -L "$SOURCE_CONFIG" ]] || {
  echo "/etc/ripdpi/real-vps-awg-nat.json must exist before enabling the timer" >&2
  exit 1
}
[[ "$(stat -c '%u:%a' "$SOURCE_CONFIG")" == "0:600" ]] || {
  echo "private runner config must be root-owned mode 0600" >&2
  exit 1
}
[[ -f "$CLIENT_ACCEPTANCE_PUBLIC_KEY" && ! -L "$CLIENT_ACCEPTANCE_PUBLIC_KEY" ]] || {
  echo "client acceptance verification key must be a regular file" >&2
  exit 1
}
[[ "$(stat -c '%u:%a' "$CLIENT_ACCEPTANCE_PUBLIC_KEY")" == "0:600" ]] || {
  echo "client acceptance verification key must be root-owned mode 0600" >&2
  exit 1
}
openssl pkey -pubin -in "$CLIENT_ACCEPTANCE_PUBLIC_KEY" -text -noout 2>/dev/null |
  grep -Fx 'ED25519 Public-Key:' >/dev/null || {
  echo "client acceptance verification key must be Ed25519" >&2
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

archive_legacy_latest() {
  local evidence_dir="/var/lib/ripdpi-real-vps-awg-nat/evidence"
  local latest="$evidence_dir/latest.json" identity digest archive_dir archived
  [[ -e "$latest" || -L "$latest" ]] || return 0
  [[ -f "$latest" && ! -L "$latest" ]] || {
    echo "existing latest evidence is not a regular file" >&2
    return 1
  }
  [[ "$(stat -c '%u:%a:%s' "$latest")" =~ ^0:600:([1-9][0-9]{0,5})$ ]] || {
    echo "existing latest evidence has unsafe metadata" >&2
    return 1
  }
  identity="$(python3 - "$latest" <<'PY'
import json
import pathlib
import sys

raw = pathlib.Path(sys.argv[1]).read_bytes()
value = json.loads(raw)
if (
    not isinstance(value, dict)
    or not isinstance(value.get("version"), str)
    or value.get("classification") != "PASS"
):
    raise SystemExit(1)
print(value["version"] + ":PASS")
PY
)" || return 1
  if [[ "$identity" == "real_vps_awg_nat_evidence_v4:PASS" ]]; then
    "$RUNNER" validate-retained-pass --manifest "$latest" >/dev/null
    return
  fi
  digest="$(sha256sum "$latest" | awk '{print $1}')"
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  archive_dir="$evidence_dir/legacy"
  archived="$archive_dir/latest-${digest}.json"
  install -d -o root -g root -m 0700 "$archive_dir"
  if [[ -e "$archived" || -L "$archived" ]]; then
    [[ -f "$archived" && ! -L "$archived" ]] || return 1
    cmp -s "$latest" "$archived" || return 1
    rm -f -- "$latest"
  else
    mv -T -- "$latest" "$archived"
  fi
}

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
  "$RUNNER"
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
# Only a completely installed generation may version an incompatible prior
# manifest. Retained v4 evidence must pass the canonical executable semantics
# before the periodic executor can be enabled.
systemctl disable --now ripdpi-real-vps-awg-nat.timer
if ! archive_legacy_latest; then
  echo "unable to preserve incompatible prior evidence; timer disabled" >&2
  exit 1
fi
systemctl enable --now ripdpi-real-vps-awg-nat.timer
echo "installed recurring AWG/NAT lane at source $source_sha"
