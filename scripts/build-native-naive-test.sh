#!/usr/bin/env bash
# Build the exact role-owned composite for native parser/socket/proxy acceptance.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
naive_test_build_dir="${NAIVE_NATIVE_BUILD_DIR:-${repo_root}/.cache/p2-native-caddy}"
[[ "$naive_test_build_dir" == /* ]] || {
  echo 'native Naive build directory must be absolute' >&2
  exit 1
}
[[ "$(go env GOVERSION)" == go1.27.1 ]] || {
  echo 'native Naive acceptance requires the repository-pinned Go toolchain' >&2
  exit 1
}
mkdir -p "$naive_test_build_dir/gopath/bin" "$naive_test_build_dir/go-cache"
export GOPATH="$naive_test_build_dir/gopath"
export GOBIN="$GOPATH/bin"
export GOCACHE="$naive_test_build_dir/go-cache"
export GOMAXPROCS=2
export CGO_ENABLED=0
export GOFLAGS='-mod=readonly -p=2'
go install github.com/caddyserver/xcaddy/cmd/xcaddy@v0.4.5
"$GOBIN/xcaddy" build v2.11.2 \
  --with github.com/caddyserver/forwardproxy@caddy2=github.com/klzgrad/forwardproxy@d62c80d3dd2c706b6b87579844d2397bddd18317 \
  --output "$naive_test_build_dir/caddy"
