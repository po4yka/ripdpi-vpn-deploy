#!/usr/bin/env bash
# Exact test-only runtimes for the isolated Linux semantic acceptance lane.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  echo 'native transport provisioning requires isolated Linux amd64' >&2
  exit 1
}
[[ "${TRANSPORT_NATIVE_ISOLATED:-}" == 1 ]] || {
  echo 'explicit isolated native fixture ownership is required' >&2
  exit 1
}
[[ "$(go env GOVERSION)" == go1.27.1 ]] || {
  echo 'native transport builds require repository-pinned Go 1.27.1' >&2
  exit 1
}
native_root="${repo_root}/.cache/native-transport-semantics"
mkdir -p "$native_root/bin"
read -r go_version go_commit tools_version tools_commit hysteria_version < <(
  python3 - "$repo_root" <<'PY'
import pathlib
import sys
import yaml
root = pathlib.Path(sys.argv[1])
pins = yaml.safe_load((root / 'secrets/prod.secrets.example.yaml').read_text())
print(pins['amneziawg_go_version'], pins['amneziawg_go_commit'],
      pins['amneziawg_tools_version'], pins['amneziawg_tools_commit'],
      pins['hysteria']['version'])
PY
)
[[ "$go_commit" =~ ^[0-9a-f]{40}$ && "$tools_commit" =~ ^[0-9a-f]{40}$ ]] || {
  echo 'native source fixture pins are invalid' >&2
  exit 1
}
[[ "$hysteria_version" == v2.9.0 ]] || {
  echo 'Hysteria native version and asset digest must be reviewed together' >&2
  exit 1
}
source_checkout() {
  local name="$1" version="$2" commit="$3"
  local destination="${native_root}/${name}-${commit}"
  if [[ ! -d "$destination/.git" ]]; then
    git clone --no-checkout "https://github.com/amnezia-vpn/${name}" "$destination"
    git -C "$destination" checkout --detach "$version"
  fi
  [[ "$(git -C "$destination" rev-parse HEAD)" == "$commit" ]] || {
    echo 'native source fixture commit differs from immutable pin' >&2
    exit 1
  }
  git -C "$destination" diff --quiet
  git -C "$destination" diff --cached --quiet
}
source_checkout amneziawg-go "$go_version" "$go_commit"
source_checkout amneziawg-tools "$tools_version" "$tools_commit"
export GOMAXPROCS=2 CGO_ENABLED=0 GOTOOLCHAIN=local GOWORK=off
export GOFLAGS='-mod=readonly -p=2'
make -C "${native_root}/amneziawg-go-${go_commit}" -j2
make -C "${native_root}/amneziawg-tools-${tools_commit}/src" -j2

native_download="$(mktemp -d "${native_root}/download.XXXXXXXX")"
trap 'rm -rf -- "$native_download"' EXIT
curl -fsSL --connect-timeout 10 --max-time 120 \
  'https://github.com/apernet/hysteria/releases/download/app/v2.9.0/hysteria-linux-amd64' \
  -o "$native_download/hysteria"
printf '%s  %s\n' \
  '8225c8380f1ae8122921d4986c2b70976e9c6e6f87a977e7d0498a813f4f3e37' \
  "$native_download/hysteria" | sha256sum -c -
install -m 0755 "$native_download/hysteria" "$native_root/bin/hysteria"
"$native_root/bin/hysteria" version
sha256sum "${native_root}/amneziawg-go-${go_commit}/amneziawg-go" \
  "${native_root}/amneziawg-tools-${tools_commit}/src/wg" "$native_root/bin/hysteria"
