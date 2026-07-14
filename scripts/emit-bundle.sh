#!/usr/bin/env bash
# Emit a RIPDPI-extended sing-box JSON for one client name.
#
# Output is the full sing-box document produced by emit-singbox.sh, merged
# with a top-level "ripdpi" object carrying:
#   - amneziawg: AmneziaWG device-VPN parameters (private_key_placeholder: true
#                because the client key is never stored server-side)
#   - hysteria_extras: salamander obfs + port-hopping metadata for the P2
#                      Hysteria2 outbound (keys match the tag emit-singbox emits)
#
# The RIPDPI Android client parses this single file as its subscription
# artifact.  Standard sing-box clients should use the plain /sub endpoint
# instead — the "ripdpi" key is a non-standard extension they will ignore.
#
# Usage (mirrors emit-singbox.sh):
#   PROVIDER=upcloud ENV=prod  scripts/emit-bundle.sh laptop
#   HOSTS="upcloud:prod,hetzner:prod"  scripts/emit-bundle.sh laptop
#   HOSTS="upcloud:prod,upcloud:spare" scripts/emit-bundle.sh laptop
#   HOSTS="upcloud:p0,upcloud:full" COHORTS="p0-minimal,device-full" scripts/emit-bundle.sh laptop
#
# AWG obfuscation parameter precedence (identical to emit-awg.sh):
#   amneziawg_secrets.{jc,jmin,jmax,s1,s2,h1..h4}  (SOPS — highest)
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
  echo "usage: $0 <client_name>" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for tool in sops terraform jq python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing: $tool" >&2; exit 1; }
done

# awg or wg — prefer awg (AmneziaWG tools), fall back to wg (standard WireGuard)
AWG_PUBKEY_CMD=""
if command -v awg >/dev/null 2>&1; then
  AWG_PUBKEY_CMD="awg pubkey"
elif command -v wg >/dev/null 2>&1; then
  AWG_PUBKEY_CMD="wg pubkey"
else
  echo "missing: awg or wg (needed to derive server public key from private key)" >&2
  exit 1
fi

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
# Helper: resolve one AWG obfuscation parameter with three-level precedence
# (mirrors emit-awg.sh resolve_param exactly)
# ---------------------------------------------------------------------------
resolve_awg_param() {
  local param="$1"
  local default="$2"
  local secrets_file="$3"
  local cohort_yml="$4"

  # Level 1: amneziawg_secrets.<param> from SOPS
  local val
  val="$(jq -r --arg p "$param" '.amneziawg_secrets[$p] // empty' "$secrets_file")"
  if [[ -n "$val" ]]; then
    echo "$val"
    return
  fi

  # Level 2: amneziawg_cohort.<param> from cohort YAML
  if [[ -n "$cohort_yml" ]]; then
    val="$(python3 - "$cohort_yml" "$param" <<'PY'
import sys
import yaml
data = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
cohort = data.get("amneziawg_cohort") or {}
v = cohort.get(sys.argv[2])
if v is not None:
    print(v)
PY
)"
    if [[ -n "$val" ]]; then
      echo "$val"
      return
    fi
  fi

  # Level 3: hard default
  if [[ -n "$default" ]]; then
    echo "$default"
    return
  fi

  echo ""
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
  tag_prefix="${prov}-${env_name}"

  # ------------------------------------------------------------------
  # Topology — declared from the first host's group_vars so the client
  # can tell a split-hop / realm-relayed endpoint from a direct one
  # instead of mis-modelling a dual-role flow. Defaults: not split-hop,
  # no realm (a plain single-VPS deployment).
  # ------------------------------------------------------------------
  if [[ -z "$TOPOLOGY_JSON" ]]; then
    TOPOLOGY_JSON="$(jq -c '{
      split_hop_egress: (.split_hop_egress // false),
      hysteria_realm:   (.hysteria_realm // null)
    }' <<< "$vpn_json")"
  fi

  # ------------------------------------------------------------------
  # AWG block — build if AWG is enabled for this host and not yet built
  # ------------------------------------------------------------------
  enable_amneziawg="$(jq -r \
    'if has("enable_amneziawg") then .enable_amneziawg else false end | tostring | ascii_downcase' \
    <<< "$vpn_json")"
  if [[ "$AWG_BLOCK" == '[]' && "$enable_amneziawg" == "true" ]]; then
    # Check if AWG secrets exist for this client
    peer_json="$(jq --arg name "$CLIENT_NAME" \
      '.amneziawg_secrets.peers[]? | select(.name == $name)' "$secrets_tmp")"

    if [[ -n "$peer_json" && "$peer_json" != "null" ]]; then
      server_ip="$(PROVIDER="$prov" ENV="$env_name" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"

      # Derive server public key
      server_priv="$(jq -r '.amneziawg_secrets.server_private_key // empty' "$secrets_tmp")"
      if [[ -z "$server_priv" ]]; then
        echo "amneziawg_secrets.server_private_key missing in ${sops_file}" >&2
        exit 1
      fi
      server_pub_file="${WORK}/server-${i}.pub"
      printf '%s' "$server_priv" | $AWG_PUBKEY_CMD > "$server_pub_file"
      server_pubkey="$(cat "$server_pub_file")"

      listen_port="$(jq -r '.amneziawg_secrets.listen_port // empty' "$secrets_tmp")"
      [[ -z "$listen_port" ]] && listen_port=51820

      peer_psk="$(jq -r    '.preshared_key' <<< "$peer_json")"
      peer_addr="$(jq -r   '.allowed_ips'   <<< "$peer_json")"

      # Resolve AWG cohort file for obfuscation defaults
      AWG_COHORT="${AWG_COHORT:-}"
      cohort_yml_path=""
      if [[ -n "$AWG_COHORT" ]]; then
        cohort_file="${REPO_ROOT}/ansible/roles/amneziawg/vars/cohorts/${AWG_COHORT}.yml"
        if [[ ! -f "$cohort_file" ]]; then
          echo "cohort file not found: $cohort_file" >&2
          exit 1
        fi
        cohort_yml_path="$cohort_file"
      fi

      # Resolve obfuscation parameters (three-level precedence)
      jc="$(resolve_awg_param jc 4 "$secrets_tmp" "$cohort_yml_path")"
      jmin="$(resolve_awg_param jmin 40 "$secrets_tmp" "$cohort_yml_path")"
      jmax="$(resolve_awg_param jmax 70 "$secrets_tmp" "$cohort_yml_path")"
      s1="$(resolve_awg_param s1 50 "$secrets_tmp" "$cohort_yml_path")"
      s2="$(resolve_awg_param s2 100 "$secrets_tmp" "$cohort_yml_path")"
      h1="$(resolve_awg_param h1 "" "$secrets_tmp" "$cohort_yml_path")"
      h2="$(resolve_awg_param h2 "" "$secrets_tmp" "$cohort_yml_path")"
      h3="$(resolve_awg_param h3 "" "$secrets_tmp" "$cohort_yml_path")"
      h4="$(resolve_awg_param h4 "" "$secrets_tmp" "$cohort_yml_path")"

      if [[ -z "$h1" || -z "$h2" || -z "$h3" || -z "$h4" ]]; then
        echo "H1..H4 are required but could not be resolved from secrets or cohort." >&2
        echo "Set amneziawg_secrets.h1..h4 in SOPS or specify AWG_COHORT=<slug>." >&2
        exit 1
      fi

      # Build the AWG JSON object; conditionally include i1..i5
      # S3/S4 are intentionally absent: amneziawg-go#110 causes silent packet
      # drop on arm64-Android clients when S3/S4 are non-zero; this repo pins
      # S3=S4=0 for the whole arm64-Android family, enforced by the amneziawg role guard.
      awg_obj="$(jq -n \
        --arg tag "p2-awg-${CLIENT_NAME}" \
        --argjson addr "$(jq -nc --arg a "$peer_addr" '[$a]')" \
        --argjson mtu 1420 \
        --argjson jc "$jc" --argjson jmin "$jmin" --argjson jmax "$jmax" \
        --argjson s1 "$s1" --argjson s2 "$s2" \
        --argjson h1 "$h1" --argjson h2 "$h2" \
        --argjson h3 "$h3" --argjson h4 "$h4" \
        --arg pub "$server_pubkey" --arg psk "$peer_psk" \
        --arg endpoint "${server_ip}:${listen_port}" \
        '{
          tag: $tag,
          address: $addr,
          dns: ["1.1.1.1","1.0.0.1"],
          mtu: $mtu,
          jc: $jc, jmin: $jmin, jmax: $jmax,
          s1: $s1, s2: $s2,
          h1: $h1, h2: $h2, h3: $h3, h4: $h4,
          private_key_placeholder: true,
          peer: {
            public_key: $pub,
            preshared_key: $psk,
            endpoint: $endpoint,
            allowed_ips: ["0.0.0.0/0","::/0"],
            persistent_keepalive: 25
          }
        }')"

      # Splice in i1..i5 only when present. These are lowercase-hex strings
      # (e.g. "deadbeef"), so emit them with --arg (string), not --argjson:
      # the client parses them as strings and the bundle schema types them as
      # `^[0-9a-f]+$`. --argjson would crash on a hex value that isn't valid
      # JSON, or coerce a digit-only value to a number that fails the schema.
      for i_param in i1 i2 i3 i4 i5; do
        i_val="$(resolve_awg_param "$i_param" "" "$secrets_tmp" "$cohort_yml_path")"
        if [[ -n "$i_val" ]]; then
          awg_obj="$(jq --arg k "$i_param" --arg v "$i_val" '. + {($k): $v}' <<< "$awg_obj")"
        fi
      done

      # Stamp the cohort fingerprint: a SHA-256 over the now-fully-resolved
      # obfuscation params (jc..h4 + any i1..i5). The client recomputes it and
      # warns "profile outdated, refresh subscription" on a mismatch instead of
      # letting the AWG handshake stall silently. Algorithm is the single
      # implementation in ripdpi_cohort_fingerprint.py (same one the contract
      # test pins), so emit and verify can never disagree.
      cohort_fp="$(jq -c '{jc,jmin,jmax,s1,s2,h1,h2,h3,h4,i1,i2,i3,i4,i5}' <<< "$awg_obj" \
        | python3 "${REPO_ROOT}/scripts/ripdpi_cohort_fingerprint.py" -)"
      awg_obj="$(jq --arg fp "$cohort_fp" '. + {cohort_fingerprint: $fp}' <<< "$awg_obj")"

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
