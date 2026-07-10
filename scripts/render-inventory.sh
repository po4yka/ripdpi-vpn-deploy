#!/usr/bin/env bash
# Render Ansible inventory from Terraform outputs. Supports single-host
# (backwards-compatible) and multi-host modes.
#
# Single host (default):
#   PROVIDER=upcloud ENV=prod ./scripts/render-inventory.sh
#
# Multi-host: pass a comma-separated PROVIDER:ENV list. Each pair must point
# to a Terraform root with valid state.
#   HOSTS="upcloud:prod,hetzner:prod" ./scripts/render-inventory.sh
#
# Cohort assignment: optional COHORTS env, comma-separated, one per host. The
# host gets added to a [vpn-<cohort>] group, which maps to group_vars/vpn-<cohort>.yml.
#   HOSTS="upcloud:prod,hetzner:prod" COHORTS="p0-minimal,device-full" ./scripts/render-inventory.sh
#
# Required env: ANSIBLE_SSH_PRIVATE_KEY_FILE.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${REPO_ROOT}/ansible/inventory/generated.ini"

if [[ -z "${ANSIBLE_SSH_PRIVATE_KEY_FILE:-}" ]]; then
  echo "ANSIBLE_SSH_PRIVATE_KEY_FILE is not set" >&2
  exit 1
fi

for tool in terraform jq; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing: $tool" >&2; exit 1; }
done

if [[ -n "${HOSTS:-}" ]]; then
  HOST_LIST="$HOSTS"
else
  HOST_LIST="${PROVIDER:-upcloud}:${ENV:-prod}"
fi

IFS=',' read -r -a host_pairs <<< "$HOST_LIST"
IFS=',' read -r -a cohort_list <<< "${COHORTS:-}"

if [[ -n "${COHORTS:-}" && ${#cohort_list[@]} -ne ${#host_pairs[@]} ]]; then
  echo "COHORTS count (${#cohort_list[@]}) must equal HOSTS count (${#host_pairs[@]})" >&2
  exit 1
fi

declare -a vpn_lines=()
declare -A cohort_groups=()

terraform_json_var() {
  local provider="$1"
  local env="$2"
  local tfvars_rel="$3"
  local expr="$4"
  local raw
  local decoded

  raw="$(PROVIDER="$provider" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" console -no-color -var-file="$tfvars_rel" <<< "jsonencode(${expr})")"
  decoded="$(jq -r . <<< "$raw")"
  jq -c . <<< "$decoded"
}

for i in "${!host_pairs[@]}"; do
  pair="${host_pairs[$i]}"
  prov="${pair%:*}"
  env="${pair#*:}"
  tf_dir="${REPO_ROOT}/terraform/providers/${prov}"
  tfvars_rel="environments/${env}.tfvars"

  if [[ ! -d "$tf_dir" ]]; then
    echo "no terraform root for provider '${prov}'" >&2
    exit 1
  fi
  if [[ ! -f "${tf_dir}/${tfvars_rel}" ]]; then
    echo "missing ${tf_dir}/${tfvars_rel}" >&2
    exit 1
  fi

  ip="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"
  ipv6="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv6 2>/dev/null || true)"
  user="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw admin_user)"
  hostname="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_hostname)"
  public_listeners="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -json public_listeners | jq -c .)"
  public_listeners_b64="$(printf '%s' "$public_listeners" | base64 | tr -d '\n')"
  allowed_ssh_cidrs="$(terraform_json_var "$prov" "$env" "$tfvars_rel" "var.allowed_ssh_cidrs")"
  # Optional secondary public IP for the honeypot role. Surfaces as a
  # host var so the role binds the canary listener to a dedicated
  # address rather than 0.0.0.0. Null when additional_public_ip is
  # false in the terraform vars.
  honey_ip="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw honeypot_ipv4 2>/dev/null || true)"

  vpn_line="${hostname} ansible_host=${ip} ansible_user=${user} provider=${prov} env=${env}"
  vpn_line+=" allowed_ssh_cidrs=${allowed_ssh_cidrs}"
  vpn_line+=" terraform_public_listeners_b64=${public_listeners_b64}"
  # Append the required server_ipv6 output when the provider allocates one.
  if [[ -n "$ipv6" && "$ipv6" != "null" ]]; then
    vpn_line+=" server_ipv6=${ipv6}"
  fi
  if [[ -n "$honey_ip" && "$honey_ip" != "null" ]] \
     && [[ "$honey_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    vpn_line+=" honeypot_listen_addr=${honey_ip}"
  fi
  vpn_lines+=("$vpn_line")

  if [[ -n "${cohort_list[$i]:-}" ]]; then
    cohort="${cohort_list[$i]}"
    cohort_groups["$cohort"]="${cohort_groups[$cohort]:-}${hostname}"$'\n'
  fi
done

{
  echo "[vpn]"
  printf '%s\n' "${vpn_lines[@]}"
  echo
  for cohort in "${!cohort_groups[@]}"; do
    echo "[vpn-${cohort}]"
    printf '%s' "${cohort_groups[$cohort]}"
    echo
  done
  echo "[vpn:vars]"
  echo "ansible_ssh_private_key_file=${ANSIBLE_SSH_PRIVATE_KEY_FILE}"
  echo "ansible_python_interpreter=/usr/bin/python3"
} > "$OUT"

echo "wrote $OUT"
echo "--"
cat "$OUT"
