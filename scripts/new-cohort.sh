#!/usr/bin/env bash
# Add a Terraform root for a second VPS in the same provider (cohort
# pattern from RUNBOOK-add-fallback.md). Copies the existing
# `environments/<env>.tfvars` to a new ENV name, swaps `server_name` and
# (optionally) `zone`, prints next steps.
#
# Usage:
#   scripts/new-cohort.sh <new_env> [new_zone]
# Example:
#   scripts/new-cohort.sh spare de-fra1
set -euo pipefail

NEW_ENV="${1:-}"
NEW_ZONE="${2:-}"
PROVIDER="${PROVIDER:-upcloud}"
SOURCE_ENV="${SOURCE_ENV:-prod}"

if [[ -z "$NEW_ENV" ]]; then
  echo "usage: $0 <new_env> [new_zone]" >&2
  exit 1
fi
if [[ ! "$NEW_ENV" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
  echo "new_env must be a hostname-safe suffix: letters, numbers, hyphens" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"
SRC="${TF_DIR}/environments/${SOURCE_ENV}.tfvars"
DST="${TF_DIR}/environments/${NEW_ENV}.tfvars"

if [[ ! -f "$SRC" ]]; then
  echo "missing source tfvars: $SRC" >&2
  exit 1
fi
if [[ -f "$DST" ]]; then
  echo "destination already exists: $DST" >&2
  exit 1
fi

cp "$SRC" "$DST"

tfvar_string() {
  local key="$1"
  local file="$2"
  python3 - "$key" "$file" <<'PY'
import re
import sys

key, path = sys.argv[1:]
pattern = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*")([^"]*)(".*)$', re.MULTILINE)
text = open(path, encoding="utf-8").read()
match = pattern.search(text)
if not match:
    raise SystemExit(f"missing {key} in {path}")
print(match.group(2))
PY
}

set_tfvar_string() {
  local key="$1"
  local value="$2"
  local file="$3"
  python3 - "$key" "$value" "$file" <<'PY'
import re
import sys

key, value, path = sys.argv[1:]
escaped = value.replace("\\", "\\\\").replace('"', '\\"')
pattern = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*")([^"]*)(".*)$', re.MULTILINE)
text = open(path, encoding="utf-8").read()
new_text, count = pattern.subn(lambda m: f"{m.group(1)}{escaped}{m.group(3)}", text, count=1)
if count != 1:
    raise SystemExit(f"missing {key} in {path}")
open(path, "w", encoding="utf-8").write(new_text)
PY
}

# Make a unique server_name without disturbing the tfvars quotes or comments.
server_name="$(tfvar_string server_name "$DST")"
set_tfvar_string server_name "${server_name}-${NEW_ENV}" "$DST"

if [[ -n "$NEW_ZONE" ]]; then
  set_tfvar_string zone "$NEW_ZONE" "$DST"
fi

cat <<EOF
created: $DST

Next steps:
  1. Edit $DST — at minimum verify server_name uniqueness, and consider a
     different storage_template or plan if needed.
  2. Provision and deploy:
       PROVIDER=${PROVIDER} ENV=${NEW_ENV} make init plan apply inventory wait
  3. Decide cohort:
       same stack as prod         → make ENV=${NEW_ENV} dry-run deploy verify
       split stack (P0 only here) → render multi-host inventory:
         HOSTS="${PROVIDER}:${SOURCE_ENV},${PROVIDER}:${NEW_ENV}" \\
         COHORTS="fullstack,p0" \\
         ANSIBLE_SSH_PRIVATE_KEY_FILE=~/.ssh/vpn_deploy \\
         ./scripts/render-inventory.sh
         make PROVIDER=${PROVIDER} ENV=${NEW_ENV} dry-run deploy verify
EOF
