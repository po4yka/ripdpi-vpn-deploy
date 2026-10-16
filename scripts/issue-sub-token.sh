#!/usr/bin/env bash
# Issue/refresh through the locked encrypted exact-payload transaction.
set -euo pipefail
umask 077
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# == 0 || "$1" == --help || "$1" == -h ]]; then
  exec python3 "${REPO_ROOT}/scripts/issue_sub_token.py" "$@"
fi
client="$1"
shift
options=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --refresh-token|--format|--expires)
      [[ $# -ge 2 ]] || { echo 'missing subscription option value' >&2; exit 2; }
      options+=("$1=$2")
      shift 2
      ;;
    *) options+=("$1"); shift ;;
  esac
done
exec python3 "${REPO_ROOT}/scripts/issue_sub_token.py" "${options[@]}" -- "$client"
