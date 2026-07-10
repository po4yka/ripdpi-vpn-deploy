#!/usr/bin/env bash
# Local-filesystem permission audit. Runs on the operator workstation
# to catch the common ways secrets leak through file mode:
#   * age private key not 0600
#   * SOPS file world-readable
#   * SSH private key not 0600
#   * stray plaintext *.secrets.yaml on disk (left by a crashed sops editor)
#   * group-readable Terraform state
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
for p in /tmp/vpn-*.secrets.yaml \
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
echo "[4] Terraform state"
for tf in "$REPO_ROOT"/terraform/providers/*/terraform.tfstate \
          "$REPO_ROOT"/terraform/providers/*/terraform.tfstate.backup \
          "$REPO_ROOT"/terraform/providers/*/terraform.tfstate.d/*/terraform.tfstate \
          "$REPO_ROOT"/terraform/providers/*/terraform.tfstate.d/*/terraform.tfstate.backup; do
  [[ -f "$tf" ]] || continue
  # Terraform state may contain secrets even when our pipeline tries to
  # avoid it. 600 is the safe floor.
  got="$(stat_mode "$tf")"
  if [[ "$got" != "600" ]]; then
    echo "  FAIL $tf  mode=$got  want=600"
    findings=$((findings+1))
  else
    echo "  ok   $tf  mode=$got"
  fi
done

echo
if (( findings == 0 )); then
  echo "OK — permissions audit clean"
  exit 0
fi
echo "$findings finding(s) — chmod the listed files before continuing"
exit 1
