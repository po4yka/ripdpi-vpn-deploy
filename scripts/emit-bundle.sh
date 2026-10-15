#!/usr/bin/env bash
# Emit a RIPDPI-extended sing-box JSON for one client name.
#
# Output is the RIPDPI profile-format document produced by emit-singbox.sh,
# merged with a top-level "ripdpi" object carrying:
#   - amneziawg: AmneziaWG device-VPN parameters (private_key_placeholder: true
#                because the client key is never stored server-side)
#   - hysteria_extras: salamander obfs + port-hopping metadata for the P2
#                      Hysteria2 outbound (keys match the tag emit-singbox emits)
#
# The RIPDPI Android client parses this single file as its subscription
# artifact. Standard sing-box clients must use the plain /sub endpoint:
# official sing-box does not implement the included XHTTP transport.
#
# Usage (mirrors emit-singbox.sh):
#   PROVIDER=upcloud ENV=prod  scripts/emit-bundle.sh laptop
#   HOSTS="upcloud:prod,hetzner:prod"  scripts/emit-bundle.sh laptop
#   HOSTS="upcloud:prod,upcloud:spare" scripts/emit-bundle.sh laptop
#   HOSTS="upcloud:p0,upcloud:full" COHORTS="p0-minimal,device-full" scripts/emit-bundle.sh laptop
#
# AWG obfuscation parameter precedence (identical to emit-awg.sh):
#   amneziawg_secrets.instances[].{jc,jmin,jmax,s1,s2,h1..h4}  (SOPS — highest)
#   amneziawg_cohort.{…}  from vars/cohorts/<AWG_COHORT>.yml (if AWG_COHORT set)
#   hard defaults: jc=4 jmin=40 jmax=70 s1=50 s2=100
#
# Environment variables:
#   CLIENT_NAME  — positional $1
#   PROVIDER     — terraform provider (default: upcloud)
#   ENV          — environment label for SOPS file lookup (default: prod)
#   HOSTS        — comma-separated provider:env pairs (multi-host mode)
#   COHORTS      — comma-separated cohort slugs, one per HOSTS entry
#   SOPS_FILE    — explicit shared SOPS file path
#   SOPS_FILES   — comma-separated SOPS paths, one per HOSTS entry
#   AWG_COHORT   — cohort slug for AWG obfuscation defaults
#   BUNDLE_EXPIRES — optional RFC3339/ISO-8601 UTC instant; when set, embedded
#                  as ripdpi.expires so the client can warn before expiry
#
# Requires: sops, terraform, awg or wg, jq, python3
set -euo pipefail

CLIENT_NAME="${1:-}"
if [[ -z "$CLIENT_NAME" ]]; then
  echo "usage: $0 <client_name> [--per-app-bypass pkg1,pkg2…] [--per-app-via-tun pkg1,pkg2…]" >&2
  exit 1
fi
shift
SINGBOX_CLI_ARGS=("$@")

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for tool in sops terraform jq python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing: $tool" >&2; exit 1; }
done

# ---------------------------------------------------------------------------
# Resolve host pairs (same logic as emit-singbox.sh)
# ---------------------------------------------------------------------------
if [[ -n "${HOSTS:-}" ]]; then
  HOST_LIST="$HOSTS"
else
  HOST_LIST="${PROVIDER:-upcloud}:${ENV:-prod}"
fi
IFS=',' read -r -a host_pairs <<< "$HOST_LIST"
IFS=',' read -r -a sops_per_host <<< "${SOPS_FILES:-}"
IFS=',' read -r -a cohort_list <<< "${COHORTS:-}"

if [[ -n "${COHORTS:-}" && ${#cohort_list[@]} -ne ${#host_pairs[@]} ]]; then
  echo "COHORTS count (${#cohort_list[@]}) must equal HOSTS count (${#host_pairs[@]})" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Work directory: shred all decrypted-secret temp files on exit
# ---------------------------------------------------------------------------
WORK="$(mktemp -d -t vpn-bundle.XXXXXX)"
trap 'find "$WORK" -type f -exec shred -u {} + 2>/dev/null; rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------
# Step 1: emit the base sing-box JSON
# ---------------------------------------------------------------------------
SINGBOX_ARGS=()
[[ -n "${HOSTS:-}"      ]] && SINGBOX_ARGS+=(HOSTS="$HOSTS")
[[ -n "${COHORTS:-}"    ]] && SINGBOX_ARGS+=(COHORTS="$COHORTS")
[[ -n "${SOPS_FILE:-}"  ]] && SINGBOX_ARGS+=(SOPS_FILE="$SOPS_FILE")
[[ -n "${SOPS_FILES:-}" ]] && SINGBOX_ARGS+=(SOPS_FILES="$SOPS_FILES")

base_json_file="${WORK}/base.json"
env "${SINGBOX_ARGS[@]}" \
  PROVIDER="${PROVIDER:-upcloud}" ENV="${ENV:-prod}" \
  "${REPO_ROOT}/scripts/emit-singbox.sh" "$CLIENT_NAME" \
  "${SINGBOX_CLI_ARGS[@]}" --profile-format ripdpi \
  > "$base_json_file"

# ---------------------------------------------------------------------------
# Helper: resolve group_vars (same python snippet as emit-singbox.sh)
# ---------------------------------------------------------------------------
host_config_json() {
  local cohort="$1"
  python3 - "$REPO_ROOT" "$cohort" <<'PY'
import json
import pathlib
import sys

import yaml

root = pathlib.Path(sys.argv[1])
cohort = sys.argv[2]
group_vars = root / "ansible" / "group_vars"


def deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_group(name, required=False):
    path = group_vars / f"{name}.yml"
    if not path.exists():
        if required:
            raise SystemExit(f"missing group vars for cohort: {path}")
        return {}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


merged = load_group("all")
deep_merge(merged, load_group("vpn"))
if cohort:
    deep_merge(merged, load_group(f"vpn-{cohort}", required=True))

print(json.dumps(merged))
PY
}

# ---------------------------------------------------------------------------
# Step 2: resolve the AWG block and Hysteria extras from each host's secrets.
# For multi-host setups AWG is typically a single server; we use the first
# host that has AWG enabled.  Hysteria extras likewise come from the first
# host that has Hysteria enabled (the one whose tag appears in the base JSON).
# ---------------------------------------------------------------------------
AWG_BLOCK='[]'
HY_EXTRAS='{}'
TOPOLOGY_JSON=''

for i in "${!host_pairs[@]}"; do
  pair="${host_pairs[$i]}"
  prov="${pair%:*}"
  env_name="${pair#*:}"

  # Pick the SOPS file for this host
  if [[ -n "${SOPS_FILES:-}" ]]; then
    sops_file="${sops_per_host[$i]:-}"
    if [[ -z "$sops_file" ]]; then
      echo "missing SOPS_FILES entry for ${prov}:${env_name}" >&2
      exit 1
    fi
  elif [[ -n "${SOPS_FILE:-}" ]]; then
    sops_file="$SOPS_FILE"
  else
    sops_file="${HOME}/.config/vpn-provision/${env_name}.secrets.sops.yaml"
  fi

  if [[ ! -f "$sops_file" ]]; then
    echo "missing $sops_file (for ${prov}:${env_name})" >&2
    exit 1
  fi

  secrets_tmp="${WORK}/secrets-${i}.json"
  sops --decrypt --output-type json "$sops_file" > "$secrets_tmp"
  chmod 0600 "$secrets_tmp"

  cohort="${cohort_list[$i]:-}"
  host_json="$(host_config_json "$cohort")"
  vpn_json="$(jq -c '.vpn // {}' <<< "$host_json")"
  jq -nc --slurpfile secrets "$secrets_tmp" --argjson context "$host_json" \
    '{secrets:$secrets[0], context:$context}' |
    python3 "${REPO_ROOT}/scripts/transport_semantics.py"

  tag_prefix="${prov}-${env_name}"

  # ------------------------------------------------------------------
  # Topology — aggregate every host so HOSTS ordering cannot hide the
  # client-facing split-hop ingress. A realm identifier may appear on any
  # participating host, but two different non-null identifiers are ambiguous
  # and therefore fail closed.
  # ------------------------------------------------------------------
  host_topology_json="$(jq -c '{
    split_hop_egress: (.enable_split_hop_ingress // false),
    hysteria_realm:   (.hysteria_realm // null)
  }' <<< "$vpn_json")"
  if [[ -z "$TOPOLOGY_JSON" ]]; then
    TOPOLOGY_JSON="$host_topology_json"
  else
    current_realm="$(jq -c '.hysteria_realm' <<< "$TOPOLOGY_JSON")"
    host_realm="$(jq -c '.hysteria_realm' <<< "$host_topology_json")"
    if [[ "$current_realm" != "null" && "$host_realm" != "null" && "$current_realm" != "$host_realm" ]]; then
      echo "conflicting vpn.hysteria_realm values across HOSTS" >&2
      exit 1
    fi
    TOPOLOGY_JSON="$(jq -cn \
      --argjson current "$TOPOLOGY_JSON" \
      --argjson host "$host_topology_json" \
      '{
        split_hop_egress: ($current.split_hop_egress or $host.split_hop_egress),
        hysteria_realm: ($current.hysteria_realm // $host.hysteria_realm)
      }')"
  fi

  # ------------------------------------------------------------------
  # AWG block — build if AWG is enabled for this host and not yet built
  # ------------------------------------------------------------------
  enable_amneziawg="$(jq -r \
    'if has("enable_amneziawg") then .enable_amneziawg else false end | tostring | ascii_downcase' \
    <<< "$vpn_json")"
  if [[ "$enable_amneziawg" == "true" ]]; then
    # A host may be selected explicitly; every selected enabled host must bind.
    selected_host="${AWG_HOST:-}"
    if [[ -z "$selected_host" || "$selected_host" == "${prov}:${env_name}" ]]; then
      if [[ "$AWG_BLOCK" != '[]' ]]; then
        echo 'ambiguous-device-binding' >&2
        exit 1
      fi
      server_ip="$(PROVIDER="$prov" ENV="$env_name" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"
      awg_obj="$(python3 "${REPO_ROOT}/scripts/awg_client.py" bundle \
        --host "${prov}:${env_name}" --cohort "$cohort" --endpoint "$server_ip" -- "$CLIENT_NAME" < "$secrets_tmp")"
      AWG_BLOCK="$(jq -nc --argjson obj "$awg_obj" '[$obj]')"
    fi
  fi

  # ------------------------------------------------------------------
  # Hysteria extras — build from the first host with Hysteria enabled
  # ------------------------------------------------------------------
  if [[ "$HY_EXTRAS" == '{}' ]]; then
    enable_hysteria="$(jq -r \
      'if has("enable_hysteria") then .enable_hysteria else false end | tostring | ascii_downcase' \
      <<< "$vpn_json")"

    if [[ "$enable_hysteria" == "true" ]]; then
      hy_tag="p2-hysteria2-${tag_prefix}"

      # Verify the tag actually appears in the base sing-box JSON
      tag_present="$(jq -r --arg t "$hy_tag" \
        '.outbounds[]? | select(.tag == $t) | .tag' "$base_json_file" || true)"

      if [[ -n "$tag_present" ]]; then
        hy_obfs_enabled="$(jq -r '.hysteria.salamander_enabled // false' "$secrets_tmp")"
        hy_obfs_pw="$(jq -r '.hysteria.salamander_password // empty' "$secrets_tmp")"
        hysteria_port_range="$(jq -r '.hysteria_port_range // ""' <<< "$host_json")"
        hysteria_hop_interval="$(jq -r '.hysteria_hop_interval // "30s"' <<< "$host_json")"

        # Build the extras object for this tag
        hy_entry="$(jq -n \
          --argjson insecure false \
          '{insecure: $insecure}')"

        if [[ "$hy_obfs_enabled" == "true" && -n "$hy_obfs_pw" ]]; then
          hy_entry="$(jq --arg pw "$hy_obfs_pw" \
            '. + {obfs: {type: "salamander", password: $pw}}' <<< "$hy_entry")"

          # salamander_upstream_tag: the Hysteria2 release this server runs.
          # The Salamander algorithm ships with hysteria2, so its upstream tag
          # IS hysteria.version — reuse it rather than carry a second secret.
          # The client compares it to the version its bundled obfuscator
          # implements and warns on a skew instead of a silent obfs failure.
          hy_version="$(jq -r '.hysteria.version // empty' "$secrets_tmp")"
          if [[ -n "$hy_version" && "$hy_version" != REPLACE_WITH_* ]]; then
            hy_entry="$(jq --arg tag "$hy_version" \
              '. + {salamander_upstream_tag: $tag}' <<< "$hy_entry")"
          fi
        fi

        if [[ -n "$hysteria_port_range" ]]; then
          hop_lo="${hysteria_port_range%-*}"
          hop_hi="${hysteria_port_range#*-}"
          port_range_str="${hop_lo}:${hop_hi}"
          hy_entry="$(jq \
            --arg ports "$port_range_str" \
            --arg interval "$hysteria_hop_interval" \
            '. + {port_hopping: {ports: $ports, interval: $interval}}' <<< "$hy_entry")"
        fi

        HY_EXTRAS="$(jq -nc \
          --arg tag "$hy_tag" \
          --argjson entry "$hy_entry" \
          '{($tag): $entry}')"
      fi
    fi
  fi
done

# ---------------------------------------------------------------------------
if [[ -n "${AWG_HOST:-}" && "$AWG_BLOCK" == '[]' ]]; then
  echo 'missing-device-binding' >&2
  exit 1
fi

# Step 3: assemble the ripdpi object and merge onto the base sing-box JSON
# ---------------------------------------------------------------------------
[[ -z "$TOPOLOGY_JSON" ]] && TOPOLOGY_JSON='{"split_hop_egress":false,"hysteria_realm":null}'

ripdpi_json="$(jq -n \
  --argjson schema_version 1 \
  --argjson amneziawg "$AWG_BLOCK" \
  --argjson hysteria_extras "$HY_EXTRAS" \
  --argjson topology "$TOPOLOGY_JSON" \
  '{schema_version: $schema_version, amneziawg: $amneziawg, hysteria_extras: $hysteria_extras, topology: $topology}')"

# expires: optional. When BUNDLE_EXPIRES is set (e.g. issue-sub-token.sh passes
# its --expires through), embed it in the ripdpi object so the client can warn
# "subscription expires in N days" proactively, rather than discovering expiry
# only when the /sub fetch starts returning 410.
if [[ -n "${BUNDLE_EXPIRES:-}" ]]; then
  ripdpi_json="$(jq --arg expires "$BUNDLE_EXPIRES" '. + {expires: $expires}' <<< "$ripdpi_json")"
fi

jq --argjson r "$ripdpi_json" '. + {ripdpi: $r}' "$base_json_file"
