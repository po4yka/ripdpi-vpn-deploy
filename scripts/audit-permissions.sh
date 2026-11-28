#!/usr/bin/env bash
# Local-filesystem permission audit. Runs on the operator workstation
# to catch the common ways secrets leak through file mode:
#   * age private key not 0600
#   * SOPS file world-readable
#   * SSH private key not 0600
#   * stray plaintext *.secrets.yaml on disk (left by a crashed sops editor)
#
# Exit 1 on any finding.
#
# Run via `make audit-permissions`.
set -euo pipefail

CONFIG_DIR="${HOME}/.config/vpn-provision"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
findings=0

stat_mode() {
  # cross-platform mode: macOS stat -f vs GNU stat -c
  if stat -c %a "$1" >/dev/null 2>&1; then
    stat -c %a "$1"
  else
    stat -f %Lp "$1"
  fi
}

check_mode() {
  local path="$1" want="$2"
  if [[ ! -e "$path" ]]; then return; fi
  local got
  got="$(stat_mode "$path")"
  if [[ "$got" != "$want" ]]; then
    echo "  FAIL $path  mode=$got  want=$want"
    findings=$((findings+1))
  else
    echo "  ok   $path  mode=$got"
  fi
}

echo "[1] ~/.config/vpn-provision"
check_mode "$CONFIG_DIR" 700
for k in "$CONFIG_DIR"/age.key "$CONFIG_DIR"/*.secrets.sops.yaml; do
  [[ -f "$k" ]] || continue
  check_mode "$k" 600
done

echo
echo "[2] SSH keys"
for k in "${HOME}/.ssh/vpn_deploy" "${HOME}/.ssh/vpn_deploy.pub"; do
  if [[ -f "$k" ]]; then
    if [[ "$k" == *.pub ]]; then
      check_mode "$k" 644
    else
      check_mode "$k" 600
    fi
  fi
done

echo
echo "[3] Stray plaintext"
shopt -s nullglob
strays=()
# Check explicit and default locations together. A later invocation can use a
# different runtime directory from an interrupted decrypt.
runtime_suffix="vpn-provision-$(id -u)"
seen_runtime_dirs=()
for runtime_dir in "${VPN_RUNTIME_DIR:-}" "${XDG_RUNTIME_DIR:-}" "${RUNTIME_DIR:-}" \
                   "${TMPDIR:-/tmp}/$runtime_suffix" "/tmp/$runtime_suffix"; do
  [[ -n "$runtime_dir" ]] || continue
  duplicate=false
  for seen in ${seen_runtime_dirs[@]+"${seen_runtime_dirs[@]}"}; do
    if [[ "$runtime_dir" == "$seen" ]]; then
      duplicate=true
      break
    fi
  done
  [[ "$duplicate" == false ]] || continue
  seen_runtime_dirs+=("$runtime_dir")
  for p in "$runtime_dir"/vpn-*.secrets.yaml "$runtime_dir"/.vpn-*.secrets.*; do
    [[ -f "$p" || -L "$p" ]] && strays+=("$p")
  done
done
for p in /tmp/vpn-*.secrets.yaml \
         "${TMPDIR:-/tmp}"/vpn-blue-green.*/*.yaml /tmp/vpn-blue-green.*/*.yaml \
         "$CONFIG_DIR"/*.secrets.yaml \
         "$REPO_ROOT"/secrets/*.secrets.yaml; do
  # The example schema is fine; anything else under secrets/ that's not
  # the example is suspect.
  case "$p" in
    */prod.secrets.example.yaml|*/staging.secrets.example.yaml) continue ;;
    */README*) continue ;;
  esac
  [[ -f "$p" ]] && strays+=("$p")
done
shopt -u nullglob
if (( ${#strays[@]} == 0 )); then
  echo "  ok   no stray plaintext secrets files"
else
  for s in "${strays[@]}"; do
    echo "  FAIL stray plaintext: $s"
    findings=$((findings+1))
  done
fi

echo
if (( findings == 0 )); then
  echo "OK — permissions audit clean"
  exit 0
fi
echo "$findings finding(s) — chmod the listed files before continuing"
exit 1
