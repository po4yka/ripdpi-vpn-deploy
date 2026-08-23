#!/usr/bin/env bash
# Evaluate the terraform/policy Rego rules against the rendered plan of one
# provider environment. Fail-closed: a missing plan or a deny rule fails the
# run. Uses scripts/terraform-env.sh so workspace selection stays canonical.
#
# Requires the same provider credentials as `make plan` for PROVIDER/ENV.
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT

usage() {
	cat >&2 <<EOF
Usage: ${0##*/} -p <provider> -e <environment>

Plans terraform/providers/<provider> for <environment> via
scripts/terraform-env.sh, converts the plan to JSON, and runs
conftest test against terraform/policy/.
EOF
}

provider=""
env_name=""
while getopts ":p:e:h" opt; do
	case "$opt" in
	p) provider="$OPTARG" ;;
	e) env_name="$OPTARG" ;;
	h) usage; exit 0 ;;
	*) usage; exit 64 ;;
	esac
done
shift $((OPTIND - 1))
[[ $# -eq 0 ]] || { usage; exit 64; }
[[ -n "$provider" && -n "$env_name" ]] || { usage; exit 64; }

for bin in conftest terraform; do
	command -v "$bin" >/dev/null 2>&1 || { printf 'missing: %s\n' "$bin" >&2; exit 69; }
done

case "$provider" in
upcloud | hetzner | vultr | scaleway) ;;
*) printf 'unsupported PROVIDER: %s\n' "$provider" >&2; exit 64 ;;
esac
if [[ ! "$env_name" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
	printf 'ENV must contain only letters, numbers, and hyphens: %s\n' "$env_name" >&2
	exit 64
fi

TFVARS="${REPO_ROOT}/terraform/providers/${provider}/environments/${env_name}.tfvars"
[[ -f "$TFVARS" ]] || { printf 'missing %s - copy from .example and fill\n' "$TFVARS" >&2; exit 66; }

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tf-policy-test.XXXXXX")"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

PLAN_BIN="${TMP_DIR}/plan.binary"
PLAN_JSON="${TMP_DIR}/plan.json"

PROVIDER="$provider" ENV="$env_name" "${REPO_ROOT}/scripts/terraform-env.sh" plan \
	-input=false -refresh=false -lock=false \
	-var-file="environments/${env_name}.tfvars" \
	-out="$PLAN_BIN"

PROVIDER="$provider" ENV="$env_name" "${REPO_ROOT}/scripts/terraform-env.sh" show \
	-json "$PLAN_BIN" >"$PLAN_JSON"

conftest test --rego-version v0 -p "${REPO_ROOT}/terraform/policy" "$PLAN_JSON"
