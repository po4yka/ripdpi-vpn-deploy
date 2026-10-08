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
# Restricted Tailnet SSH transport: optional TAILNET_HANDOFFS has one private
# bootstrap handoff path or '-' per HOSTS item. Terraform still owns service
# addresses; the renderer accepts only the handoff's confirmed Tailscale address.
#   HOSTS="upcloud:staging" TAILNET_HANDOFFS="/private/path/handoff.json" ./scripts/render-inventory.sh
# Co-hosted observability requires one capability entry per VPN host.
# Exactly one existing host also carries the collector capability.
# Uptime Kuma credentials remain in SOPS, never in topology or environment.
#   OBSERVABILITY_CAPABILITIES="vpn+collector,vpn,vpn"
#   OBSERVABILITY_FAILURE_DOMAINS="node-a,node-b,node-c"
#   OBSERVABILITY_OBSERVER_ALIAS="observer-a" OBSERVABILITY_OBSERVER_DOMAIN="observer-a"
#
# Required env: ANSIBLE_SSH_PRIVATE_KEY_FILE.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${REPO_ROOT}/ansible/inventory/generated.ini"

if [[ -z "${ANSIBLE_SSH_PRIVATE_KEY_FILE:-}" ]]; then
  echo "ANSIBLE_SSH_PRIVATE_KEY_FILE is not set" >&2
  exit 1
fi

for tool in terraform jq ssh python3; do
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
IFS=',' read -r -a tailnet_handoff_list <<< "${TAILNET_HANDOFFS:-}"
IFS=',' read -r -a observability_capability_list <<< "${OBSERVABILITY_CAPABILITIES:-}"
IFS=',' read -r -a observability_failure_domain_list <<< "${OBSERVABILITY_FAILURE_DOMAINS:-}"

observability_enabled=false
observability_scope_args=()
for pair in "${host_pairs[@]}"; do
  if [[ ! "$pair" =~ ^(upcloud|hetzner|vultr|scaleway):[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
    echo "invalid provider/environment selection" >&2
    exit 1
  fi
  observability_scope_args+=(--environment "${pair#*:}")
done
observability_selector="$(python3 "${REPO_ROOT}/scripts/validate-secrets.py" --print-observability-selector "${observability_scope_args[@]}")" || {
  echo "invalid tracked observability selector" >&2
  exit 1
}
if [[ -n "${OBSERVABILITY_HOST_CLASSES:-}${OBSERVABILITY_SENTINELS_JSON:-}" ]]; then
  echo "obsolete dedicated topology; use OBSERVABILITY_CAPABILITIES and managed heartbeats" >&2
  exit 1
fi
observability_inputs_present=false
if [[ -n "${OBSERVABILITY_CAPABILITIES:-}${OBSERVABILITY_FAILURE_DOMAINS:-}${OBSERVABILITY_OBSERVER_ALIAS:-}${OBSERVABILITY_OBSERVER_DOMAIN:-}" ]]; then
  observability_inputs_present=true
fi
if [[ "$observability_selector" == true ]]; then
  observability_enabled=true
  command -v git >/dev/null 2>&1 || { echo "missing: git" >&2; exit 1; }
  if [[ -z "${OBSERVABILITY_CAPABILITIES:-}" || -z "${OBSERVABILITY_FAILURE_DOMAINS:-}" || -z "${OBSERVABILITY_OBSERVER_ALIAS:-}" || -z "${OBSERVABILITY_OBSERVER_DOMAIN:-}" ]]; then
    echo "enabled observability requires capabilities, failure domains, and observer identity" >&2
    exit 1
  fi
  if [[ ! "$OBSERVABILITY_OBSERVER_ALIAS" =~ ^[a-z][a-z0-9_-]{0,63}$ || ! "$OBSERVABILITY_OBSERVER_DOMAIN" =~ ^[a-z][a-z0-9_-]{0,63}$ ]]; then
    echo "invalid observability observer identity" >&2
    exit 1
  fi
  if [[ -z "${VPN_SECRETS_FILE:-}" ]]; then
    echo "enabled observability requires VPN_SECRETS_FILE" >&2
    exit 1
  fi
  if [[ ${#host_pairs[@]} -gt 10 || ${#observability_capability_list[@]} -ne ${#host_pairs[@]} || ${#observability_failure_domain_list[@]} -ne ${#host_pairs[@]} ]]; then
    echo "observability capability and failure-domain counts must equal HOSTS count (at most ten)" >&2
    exit 1
  fi
  collector_count=0
  for capability in "${observability_capability_list[@]}"; do
    case "$capability" in
      vpn) ;;
      vpn+collector) collector_count=$((collector_count + 1)) ;;
      *) echo "invalid observability capability" >&2; exit 1 ;;
    esac
  done
  if [[ "$collector_count" -ne 1 ]]; then
    echo "observability requires exactly one co-hosted collector" >&2
    exit 1
  fi
  source_revision="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=normal)" ]]; then
    echo "observability topology source is not clean and stable" >&2
    exit 1
  fi
elif [[ "$observability_inputs_present" == true ]]; then
  echo "tracked observability selector is disabled" >&2
  exit 1
fi

if [[ -n "${COHORTS:-}" && ${#cohort_list[@]} -ne ${#host_pairs[@]} ]]; then
  echo "COHORTS count (${#cohort_list[@]}) must equal HOSTS count (${#host_pairs[@]})" >&2
  exit 1
fi

for cohort in "${cohort_list[@]}"; do
  [[ -z "$cohort" ]] && continue
  [[ "$cohort" == "-" ]] && continue
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

if [[ -n "${TAILNET_TRANSPORTS:-}" ]]; then
  echo "TAILNET_TRANSPORTS is unsupported; use private TAILNET_HANDOFFS" >&2
  exit 1
fi

if [[ -n "${TAILNET_HANDOFFS:-}" ]] && ! python3 - "$TAILNET_HANDOFFS" "${#host_pairs[@]}" <<'PY'
from pathlib import Path
import sys

items = sys.argv[1].split(",")
if len(items) != int(sys.argv[2]):
    raise SystemExit(1)
for item in items:
    if item == "-":
        continue
    if not item or not Path(item).is_absolute():
        raise SystemExit(1) from None
PY
then
  echo "TAILNET_HANDOFFS must contain one absolute private handoff path or '-' per host" >&2
  exit 1
fi

declare -a vpn_lines=()
declare -a observability_control_lines=()
declare -a observability_nodes=()
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
           -o StrictHostKeyChecking=yes \
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

confirmed_tailnet_transport() {
  local handoff="$1"
  local expected_alias="$2"
  local expected_public="$3"
  local expected_port="$4"
  python3 - "$handoff" "$expected_alias" "$expected_public" "$expected_port" <<'PY'
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import UUID


def reject():
    raise SystemExit(1)


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            reject()
        value[key] = item
    return value


path = Path(sys.argv[1])
try:
    if not path.is_absolute():
        reject()
    for parent in reversed(path.parents):
        info = parent.lstat()
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (info.st_uid not in (0, os.geteuid())
                or (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022 and not sticky_root)):
            reject()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            reject()
        canonical_fd = os.open(path.resolve(strict=True), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            canonical_info = os.fstat(canonical_fd)
            if (info.st_dev, info.st_ino) != (canonical_info.st_dev, canonical_info.st_ino):
                reject()
        finally:
            os.close(canonical_fd)
        raw = stream.read(65537)
    if not raw or len(raw) > 65536:
        reject()
    document = json.loads(raw, object_pairs_hook=unique)
    if (not isinstance(document, dict)
            or set(document) != {"schema_version", "status", "binding", "confirmation", "contexts"}
            or type(document["schema_version"]) is not int or document["schema_version"] != 1
            or document["status"] != "configured"):
        reject()
    binding = document["binding"]
    binding_fields = {"inventory_alias", "public_address", "ssh_port", "public_sources",
                      "approved_sources", "host_key_sha256", "source_revision", "deployable_digest"}
    if (not isinstance(binding, dict) or set(binding) != binding_fields
            or binding["inventory_alias"] != sys.argv[2]
            or binding["public_address"] != sys.argv[3]
            or type(binding["ssh_port"]) is not int or binding["ssh_port"] != int(sys.argv[4])):
        reject()
    if (not re.fullmatch(r"[0-9a-f]{64}", binding["host_key_sha256"])
            or not re.fullmatch(r"[0-9a-f]{40}", binding["source_revision"])
            or not re.fullmatch(r"[0-9a-f]{64}", binding["deployable_digest"])):
        reject()
    for name in ("public_sources", "approved_sources"):
        sources = binding[name]
        if (not isinstance(sources, list) or not 1 <= len(sources) <= 8
                or len(set(sources)) != len(sources)):
            reject()
        for source in sources:
            address = ipaddress.ip_address(source)
            if str(address) != source:
                reject()
            in_tailnet = address in (ipaddress.ip_network("100.64.0.0/10")
                                     if address.version == 4 else ipaddress.ip_network("fd7a:115c:a1e0::/48"))
            if (name == "approved_sources") != in_tailnet:
                reject()
    confirmation = document["confirmation"]
    if (not isinstance(confirmation, dict)
            or set(confirmation) != {"status", "changed", "nonce", "generation", "binding_sha256", "lease", "node"}
            or confirmation["status"] != "configured" or confirmation["changed"] is not False
            or not re.fullmatch(r"[0-9a-f]{32}", confirmation["nonce"])
            or confirmation["generation"] != "tailnet-recovery-v4"):
        reject()
    canonical = (json.dumps(binding, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if confirmation["binding_sha256"] != hashlib.sha256(canonical).hexdigest():
        reject()
    lease = confirmation["lease"]
    if (not isinstance(lease, dict) or set(lease) != {"boot_id", "started_ms", "deadline_ms"}
            or str(UUID(lease["boot_id"])) != lease["boot_id"]
            or type(lease["started_ms"]) is not int or lease["started_ms"] < 0
            or type(lease["deadline_ms"]) is not int
            or lease["deadline_ms"] - lease["started_ms"] != 300000):
        reject()
    node = confirmation["node"]
    if (not isinstance(node, dict) or set(node) != {"id", "hostname", "ipv4", "ipv6"}
            or not re.fullmatch(r"[A-Za-z0-9:_-]{1,128}", node["id"])
            or node["hostname"] != "vpn-enroll-" + confirmation["nonce"]):
        reject()
    management = ipaddress.ip_address(node["ipv4"])
    management_v6 = ipaddress.ip_address(node["ipv6"])
    if (str(management) != node["ipv4"] or management not in ipaddress.ip_network("100.64.0.0/10")
            or str(management_v6) != node["ipv6"] or management_v6 not in ipaddress.ip_network("fd7a:115c:a1e0::/48")):
        reject()
    contexts = document["contexts"]
    if not isinstance(contexts, list) or len(contexts) != 2:
        reject()
    local_addresses = set()
    for context in contexts:
        if (not isinstance(context, dict)
                or set(context) != {"user", "host", "addr", "laddr", "lport"}
                or not isinstance(context["user"], str)
                or not isinstance(context["host"], str) or context["host"] != context["addr"]
                or type(context["lport"]) is not int or context["lport"] != binding["ssh_port"]):
            reject()
        remote = ipaddress.ip_address(context["addr"])
        local = ipaddress.ip_address(context["laddr"])
        if remote.version != local.version:
            reject()
        allowed = binding["public_sources"] if context["laddr"] == binding["public_address"] else binding["approved_sources"]
        if context["addr"] not in allowed:
            reject()
        local_addresses.add(context["laddr"])
    management_addresses = local_addresses - {binding["public_address"]}
    if (len(management_addresses) != 1
            or not management_addresses <= {node["ipv4"], node["ipv6"]}
            or binding["public_address"] not in local_addresses):
        reject()
    print(next(iter(management_addresses)))
except (OSError, ValueError, TypeError, KeyError, UnicodeError):
    reject()
PY
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
  build_environment_json="$(terraform_json_var "$prov" "$env" "$tfvars_rel" "var.build_env")"
  if ! jq -e 'type == "string" and length > 0 and length <= 128' <<< "$build_environment_json" >/dev/null; then
    echo "invalid canonical build environment for ${prov}:${env}" >&2
    exit 1
  fi
  build_environment_ini="$(printf '%s' "$build_environment_json" | python3 -c 'import shlex,sys; print(shlex.quote(sys.stdin.read()))')"
  # Optional secondary public IP for the honeypot role. Surfaces as a
  # host var so the role binds the canary listener to a dedicated
  # address rather than 0.0.0.0. Null when additional_public_ip is
  # false in the terraform vars.
  honey_ip="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw honeypot_ipv4 2>/dev/null || true)"

  if ! [[ "$ssh_port" =~ ^[1-9][0-9]*$ ]] || (( ssh_port > 65535 )); then
    echo "invalid ssh_port output for ${prov}:${env}: ${ssh_port}" >&2
    exit 1
  fi
  # Keep the Terraform-owned public service endpoint independent from the
  # selected SSH transport; data-plane probes always use the public address.
  handoff="${tailnet_handoff_list[$i]:--}"
  if [[ "$handoff" == "-" ]]; then
    transport_ip="$ip"
  elif ! transport_ip="$(confirmed_tailnet_transport "$handoff" "$hostname" "$ip" "$ssh_port")"; then
    echo "refusing unbound or unsafe confirmed Tailnet handoff for ${prov}:${env}" >&2
    exit 1
  fi
  capability="vpn"
  failure_domain=""
  if [[ "$observability_enabled" == true ]]; then
    capability="${observability_capability_list[$i]}"
    failure_domain="${observability_failure_domain_list[$i]}"
    [[ "$failure_domain" =~ ^[a-z][a-z0-9_-]{0,63}$ ]] || { echo "invalid observability failure domain" >&2; exit 1; }
  fi
  vpn_line="${hostname} ansible_host=${transport_ip} vpn_service_address=${ip} ansible_user=${user} ansible_port=${ssh_port} provider=${prov} env=${env}"
  vpn_line+=" vpn_build_environment=${build_environment_ini}"
  # The INI inventory plugin tokenizes host vars with shlex before applying
  # Python literal parsing. Quote the complete JSON value so the inner string
  # quotes survive and Ansible receives a list instead of a malformed string.
  vpn_line+=" allowed_ssh_cidrs='${allowed_ssh_cidrs}'"
  vpn_line+=" terraform_public_listeners_b64=${public_listeners_b64}"
  if [[ "$observability_enabled" == true ]]; then
    node_id="${prov}-${env}"
    capabilities="$(jq -nc --arg value "$capability" '$value | split("+") | sort')"
    vpn_line+=" observability_node_id=${node_id} observability_capabilities='${capabilities}' observability_failure_domain=${failure_domain}"
    normalized_listeners="$(jq -c '[.[] | with_entries(select(.value != null))]' <<< "$public_listeners")"
    observability_nodes+=("$(jq -nc \
      --arg node_id "$node_id" --arg provider "$prov" --arg environment "$env" \
      --argjson capabilities "$capabilities" --arg failure_domain "$failure_domain" \
      --argjson public_listeners "$normalized_listeners" \
      '{node_id:$node_id,provider:$provider,environment:$environment,capabilities:$capabilities,failure_domain:$failure_domain,public_listeners:$public_listeners}')")
  fi
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
  if [[ "$capability" == vpn+collector ]]; then
    observability_control_lines+=("$hostname")
  fi

  if [[ -n "${cohort_list[$i]:-}" && "${cohort_list[$i]}" != "-" ]]; then
    cohort="${cohort_list[$i]}"
    cohort_groups["$cohort"]="${cohort_groups[$cohort]:-}${hostname}"$'\n'
  fi
done

observability_topology_b64=""
if [[ "$observability_enabled" == true ]]; then
  topology_nodes="$(printf '%s\n' "${observability_nodes[@]}" | jq -sc '.')"
  current_source_revision="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  if [[ "$current_source_revision" != "$source_revision" ]] || \
     [[ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=normal)" ]]; then
    echo "observability topology source is not clean and stable" >&2
    exit 1
  fi
  topology_temp="$(mktemp "${REPO_ROOT}/ansible/inventory/.observability-topology.XXXXXX")"
  trap 'rm -f -- "${topology_temp:-}"' EXIT
  jq -nc --arg source_revision "$source_revision" --argjson nodes "$topology_nodes" \
    --arg observer "$OBSERVABILITY_OBSERVER_ALIAS" --arg domain "$OBSERVABILITY_OBSERVER_DOMAIN" \
    '{schema_version:2,credential_mode:"systemd",source_revision:$source_revision,nodes:$nodes,observer:{kind:"uptime-kuma",host_alias:$observer,failure_domain:$domain}}' \
    > "$topology_temp"
  chmod 0600 "$topology_temp"
  topology_json="$(python3 "${REPO_ROOT}/scripts/observability-contract.py" topology --document "$topology_temp")"
  python3 "${REPO_ROOT}/scripts/validate-secrets.py" \
    "$VPN_SECRETS_FILE" --strict "${observability_scope_args[@]}" --observability-topology "$topology_temp" >/dev/null
  rm -f -- "$topology_temp"
  topology_temp=""
  current_source_revision="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  if [[ "$current_source_revision" != "$source_revision" ]] || \
     [[ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=normal)" ]]; then
    echo "observability topology source is not clean and stable" >&2
    exit 1
  fi
  observability_topology_b64="$(printf '%s' "$topology_json" | base64 | tr -d '\n')"
fi

{
  echo "[vpn]"
  printf '%s\n' "${vpn_lines[@]}"
  echo
  if [[ "$observability_enabled" == true ]]; then
    echo "[vpn-observability-control]"
    printf '%s\n' "${observability_control_lines[@]}"
    echo
    echo "[observability:children]"
    echo "vpn"
    echo "vpn-observability-control"
    echo
  fi
  for cohort in "${!cohort_groups[@]}"; do
    echo "[vpn-${cohort}]"
    printf '%s' "${cohort_groups[$cohort]}"
    echo
  done
  echo "[vpn:vars]"
  echo "ansible_ssh_private_key_file=${ANSIBLE_SSH_PRIVATE_KEY_FILE}"
  echo "ansible_python_interpreter=/usr/bin/python3"
  if [[ "$observability_enabled" == true ]]; then
    echo
    echo "[observability:vars]"
    echo "ansible_ssh_private_key_file=${ANSIBLE_SSH_PRIVATE_KEY_FILE}"
    echo "ansible_python_interpreter=/usr/bin/python3"
    echo "observability_topology_b64=${observability_topology_b64}"
  fi
} > "$OUT"

echo "wrote $OUT"
echo "--"
cat "$OUT"
