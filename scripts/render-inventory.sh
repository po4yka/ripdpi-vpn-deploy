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
# Recurring AWG evidence: optional AWG_EVIDENCE_MODES, one per host. Values are
# fail_closed, echo, or server and are emitted as host vars beside the exact
# Terraform listener contract.
#   HOSTS="scaleway:prod,vultr:prod" AWG_EVIDENCE_MODES="echo,server" ./scripts/render-inventory.sh
#
# Required env: ANSIBLE_SSH_PRIVATE_KEY_FILE.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${REPO_ROOT}/ansible/inventory/generated.ini"

if [[ -z "${ANSIBLE_SSH_PRIVATE_KEY_FILE:-}" ]]; then
  echo "ANSIBLE_SSH_PRIVATE_KEY_FILE is not set" >&2
  exit 1
fi

for tool in terraform jq ssh; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing: $tool" >&2; exit 1; }
done

if [[ -n "${HOSTS:-}" ]]; then
  HOST_LIST="$HOSTS"
else
  HOST_LIST="${PROVIDER:-upcloud}:${ENV:-prod}"
fi

IFS=',' read -r -a host_pairs <<< "$HOST_LIST"
IFS=',' read -r -a cohort_list <<< "${COHORTS:-}"
IFS=',' read -r -a awg_evidence_mode_list <<< "${AWG_EVIDENCE_MODES:-}"

if [[ -n "${COHORTS:-}" && ${#cohort_list[@]} -ne ${#host_pairs[@]} ]]; then
  echo "COHORTS count (${#cohort_list[@]}) must equal HOSTS count (${#host_pairs[@]})" >&2
  exit 1
fi

for cohort in "${cohort_list[@]}"; do
  [[ -z "$cohort" ]] && continue
  if [[ ! "$cohort" =~ ^[a-z0-9][a-z0-9-]*$ ]] || \
      [[ ! -f "${REPO_ROOT}/ansible/group_vars/vpn-${cohort}.yml" ]]; then
    echo "unknown or invalid cohort: ${cohort}" >&2
    exit 1
  fi
done

if [[ -n "${AWG_EVIDENCE_MODES:-}" && ${#awg_evidence_mode_list[@]} -ne ${#host_pairs[@]} ]]; then
  echo "AWG_EVIDENCE_MODES count (${#awg_evidence_mode_list[@]}) must equal HOSTS count (${#host_pairs[@]})" >&2
  exit 1
fi

declare -a vpn_lines=()
declare -A cohort_groups=()
declare -A host_sources=()

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

confirm_vultr_guest_ipv4() {
  local primary_ip="$1"
  local admin_user="$2"
  local secondary_ip="$3"
  local ssh_port="$4"
  local attempts="${VULTR_GUEST_IPV4_ATTEMPTS:-30}"
  local delay_seconds="${VULTR_GUEST_IPV4_DELAY_SECONDS:-5}"
  local attempt

  [[ "$attempts" =~ ^[1-9][0-9]*$ ]] || {
    echo "VULTR_GUEST_IPV4_ATTEMPTS must be a positive integer" >&2
    return 2
  }
  [[ "$delay_seconds" =~ ^[0-9]+$ ]] || {
    echo "VULTR_GUEST_IPV4_DELAY_SECONDS must be a non-negative integer" >&2
    return 2
  }

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if ssh -o BatchMode=yes \
           -o StrictHostKeyChecking=accept-new \
           -o ConnectTimeout=5 \
           -p "$ssh_port" \
           -i "$ANSIBLE_SSH_PRIVATE_KEY_FILE" \
           "${admin_user}@${primary_ip}" \
           "ip -4 -o address show | grep -Fq -- ' ${secondary_ip}/'" \
           2>/dev/null; then
      return 0
    fi
    if ((attempt < attempts)); then
      sleep "$delay_seconds"
    fi
  done

  echo "Vultr secondary IPv4 is not configured in the guest after ${attempts} attempts: ${secondary_ip}" >&2
  return 1
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
  ssh_port="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw ssh_port)"
  hostname="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_hostname)"
  if [[ -n "${host_sources[$hostname]:-}" ]]; then
    echo "duplicate inventory alias '${hostname}' from ${host_sources[$hostname]} and ${pair}" >&2
    exit 1
  fi
  host_sources["$hostname"]="$pair"
  public_listeners="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -json public_listeners | jq -c .)"
  public_listeners_b64="$(printf '%s' "$public_listeners" | base64 | tr -d '\n')"
  allowed_ssh_cidrs="$(terraform_json_var "$prov" "$env" "$tfvars_rel" "var.allowed_ssh_cidrs")"
  # Optional secondary public IP for the honeypot role. Surfaces as a
  # host var so the role binds the canary listener to a dedicated
  # address rather than 0.0.0.0. Null when additional_public_ip is
  # false in the terraform vars.
  honey_ip="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw honeypot_ipv4 2>/dev/null || true)"

  if ! [[ "$ssh_port" =~ ^[1-9][0-9]*$ ]] || (( ssh_port > 65535 )); then
    echo "invalid ssh_port output for ${prov}:${env}: ${ssh_port}" >&2
    exit 1
  fi
  # Keep the public service endpoint independent from ansible_host. Operators
  # may override ansible_host with a Tailscale address for administration;
  # data-plane probes must continue to target the Terraform-owned public IP.
  vpn_line="${hostname} ansible_host=${ip} vpn_service_address=${ip} ansible_user=${user} ansible_port=${ssh_port} provider=${prov} env=${env}"
  # The INI inventory plugin tokenizes host vars with shlex before applying
  # Python literal parsing. Quote the complete JSON value so the inner string
  # quotes survive and Ansible receives a list instead of a malformed string.
  vpn_line+=" allowed_ssh_cidrs='${allowed_ssh_cidrs}'"
  vpn_line+=" terraform_public_listeners_b64=${public_listeners_b64}"
  if [[ -n "${AWG_EVIDENCE_MODES:-}" ]]; then
    awg_evidence_mode="${awg_evidence_mode_list[$i]}"
    case "$awg_evidence_mode" in
      fail_closed|echo|server) ;;
      *)
        echo "AWG_EVIDENCE_MODES entries must be fail_closed, echo, or server" >&2
        exit 1
        ;;
    esac
    vpn_line+=" real_vps_awg_nat_mode=${awg_evidence_mode}"
  fi
  # Append the required server_ipv6 output when the provider allocates one.
  if [[ -n "$ipv6" && "$ipv6" != "null" ]]; then
    vpn_line+=" server_ipv6=${ipv6}"
  fi
  if [[ -n "$honey_ip" && "$honey_ip" != "null" ]] \
     && [[ "$honey_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    if [[ "$prov" == "vultr" ]]; then
      confirm_vultr_guest_ipv4 "$ip" "$user" "$honey_ip" "$ssh_port"
    fi
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
