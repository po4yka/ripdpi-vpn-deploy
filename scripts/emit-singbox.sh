#!/usr/bin/env bash
# Emit a standard sing-box client JSON for one client name. Embeds every
# enabled transport supported by official sing-box across one or more VPS
# hosts as outbounds, wired into a `selector` + `urltest` group. P1 XHTTP is
# emitted only for the explicit RIPDPI profile format because official
# sing-box does not implement the XHTTP V2Ray transport.
#
# Single host (backwards-compatible):
#   PROVIDER=upcloud ENV=prod  scripts/emit-singbox.sh laptop
#
# Multi-host:
#   HOSTS="upcloud:prod,hetzner:prod"  scripts/emit-singbox.sh laptop
#   HOSTS="upcloud:prod,upcloud:spare" scripts/emit-singbox.sh laptop
#   HOSTS="upcloud:p0,upcloud:full" COHORTS="p0-minimal,device-full" scripts/emit-singbox.sh laptop
#
# Per-host SOPS files: by default each pair uses
# ~/.config/vpn-provision/<ENV>.secrets.sops.yaml. Override with SOPS_FILE
# (single shared file) or SOPS_FILES (comma-separated, one per host).
# VPN_SECRETS_FILE instead supplies one protected plaintext YAML document shared
# by all hosts. It is authoritative and cannot be combined with SOPS_FILES.
#
# Client uTLS fingerprint (REALITY + XHTTP outbounds; Hysteria2's QUIC TLS has
# no uTLS knob): per-profile via group_vars `xray_utls_fingerprint` (declared in
# the xray role defaults; default "chrome"). A global UTLS_FINGERPRINT env var
# overrides it for a single run. Allowed values are whatever the target sing-box
# supports (chrome, firefox, edge, safari, ios, android, random, …). See
# docs/CLIENT-NOTES.md for when a non-default choice matters (RU-AS cascade only).
set -euo pipefail

CLIENT_NAME="${1:-}"
if [[ -z "$CLIENT_NAME" ]]; then
  echo "usage: $0 <client_name> [--profile-format sing-box|ripdpi] [--per-app-bypass pkg1,pkg2…] [--per-app-via-tun pkg1,pkg2…]" >&2
  exit 1
fi
shift

# Per-app routing (Android sing-box only — the rules carry package_name).
# bypass = those apps egress direct (no tunnel); via-tun = those apps
# go via the selector group as usual but with an explicit rule so they
# can't fall through to "direct" even if a later rule says otherwise.
PER_APP_BYPASS=""
PER_APP_VIA_TUN=""
PROFILE_FORMAT="sing-box"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-format)
      PROFILE_FORMAT="${2:-}"
      case "$PROFILE_FORMAT" in
        sing-box|ripdpi) ;;
        *) echo "profile format must be sing-box or ripdpi" >&2; exit 1 ;;
      esac
      shift 2
      ;;
    --per-app-bypass)  PER_APP_BYPASS="$2"; shift 2 ;;
    --per-app-via-tun) PER_APP_VIA_TUN="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

tools=(terraform jq python3)
if [[ ! ${VPN_SECRETS_FILE+x} ]]; then
  tools+=(sops)
elif [[ -n "${SOPS_FILES:-}" ]]; then
  echo "plaintext secrets cannot be combined with SOPS_FILES" >&2
  exit 1
fi
for tool in "${tools[@]}"; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing: $tool" >&2; exit 1; }
done

# ---------------------------------------------------------------------------
# Resolve host pairs
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

cohort_from_inventory() {
  local hostname="$1"
  local inventory="${REPO_ROOT}/ansible/inventory/generated.ini"
  [[ -f "$inventory" ]] || return 0

  python3 - "$inventory" "$hostname" <<'PY'
import pathlib
import sys

inventory = pathlib.Path(sys.argv[1])
hostname = sys.argv[2]
section = None
matches = []

for raw_line in inventory.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("[") and line.endswith("]"):
        section = line[1:-1]
        continue
    if not section or ":" in section:
        continue
    if line.split()[0] == hostname and section.startswith("vpn-"):
        matches.append(section.removeprefix("vpn-"))

if matches:
    print(matches[0])
PY
}

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


defaults_path = root / "ansible" / "roles" / "snell" / "defaults" / "main.yml"
with defaults_path.open(encoding="utf-8") as handle:
    merged = yaml.safe_load(handle) or {}
deep_merge(merged, load_group("all"))
deep_merge(merged, load_group("vpn"))
if cohort:
    deep_merge(merged, load_group(f"vpn-{cohort}", required=True))

print(json.dumps(merged))
PY
}

toggle_enabled() {
  local config_json="$1"
  local key="$2"
  local default="$3"
  jq -r --arg key "$key" --argjson default "$default" \
    'if has($key) then .[$key] else $default end | tostring | ascii_downcase' \
    <<< "$config_json"
}

# All temporary materializations are private and cleaned on exit.
umask 0077
WORK="$(mktemp -d -t vpn-singbox.XXXXXX)"
trap 'find "$WORK" -type f -exec shred -u {} \; 2>/dev/null; rm -rf "$WORK"' EXIT

# Read once through the permission-checked descriptor, then share the JSON
# snapshot across hosts. Never fall back to SOPS for a rejected explicit path.
if [[ ${VPN_SECRETS_FILE+x} ]]; then
  python3 - > "${WORK}/shared-secrets.json" <<'PY'
import json
import os
import stat
import sys

import yaml

try:
    descriptor = os.open(
        os.environ["VPN_SECRETS_FILE"],
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
    )
    with os.fdopen(descriptor, encoding="utf-8") as handle:
        metadata = os.fstat(handle.fileno())
        if (not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_mode & 0o077):
            raise ValueError("unsafe plaintext")
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ValueError("expected a secrets mapping")
    payload = json.dumps(document)
except (OSError, ValueError, TypeError, yaml.YAMLError):
    sys.exit("cannot read plaintext secrets: require a current-owner private regular YAML file")
sys.stdout.write(payload)
PY
fi

OUTBOUNDS='[]'
SNELL_TAGS='[]'

for i in "${!host_pairs[@]}"; do
  pair="${host_pairs[$i]}"
  prov="${pair%:*}"
  env="${pair#*:}"

  if [[ ${VPN_SECRETS_FILE+x} ]]; then
    secrets_tmp="${WORK}/shared-secrets.json"
    sops_file="the protected plaintext input"
  else
    # Direct script users may still select one encrypted source per host.
    if [[ -n "${SOPS_FILES:-}" ]]; then
      sops_file="${sops_per_host[$i]:-}"
      if [[ -z "$sops_file" ]]; then
        echo "missing SOPS_FILES entry for ${prov}:${env}" >&2
        exit 1
      fi
    elif [[ -n "${SOPS_FILE:-}" ]]; then
      sops_file="$SOPS_FILE"
    else
      sops_file="${HOME}/.config/vpn-provision/${env}.secrets.sops.yaml"
    fi

    if [[ ! -f "$sops_file" ]]; then
      echo "missing $sops_file (for ${prov}:${env})" >&2
      exit 1
    fi
    secrets_tmp="${WORK}/secrets-${i}.json"
    sops --decrypt --output-type json "$sops_file" > "$secrets_tmp"
    chmod 0600 "$secrets_tmp"
  fi

  server_ip="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"
  server_hostname="$(PROVIDER="$prov" ENV="$env" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_hostname 2>/dev/null || true)"
  tag_prefix="${prov}-${env}"
  cohort="${cohort_list[$i]:-}"
  if [[ -z "$cohort" && -n "$server_hostname" ]]; then
    cohort="$(cohort_from_inventory "$server_hostname")"
  fi
  host_json="$(host_config_json "$cohort")"
  vpn_json="$(jq -c '.vpn // {}' <<< "$host_json")"
  enable_reality="$(toggle_enabled "$vpn_json" enable_xray_reality true)"
  enable_xhttp="$(toggle_enabled "$vpn_json" enable_nginx_xhttp true)"
  enable_hysteria="$(toggle_enabled "$vpn_json" enable_hysteria false)"
  enable_snell="$(toggle_enabled "$vpn_json" enable_snell false)"
  flow_mode="$(jq -r '.xray_flow_mode // empty' <<< "$vpn_json")"
  [[ -n "$flow_mode" ]] || flow_mode="$(jq -r '.p0_reality_flow_mode // "vision"' <<< "$host_json")"
  p0_shapes_json="$(jq -c '.p0_reality_shapes // {}' <<< "$host_json")"
  default_finalmask="false"
  xray_server_port="$(jq -r '.xray_port // 443' <<< "$host_json")"
  xray_fallback_port="$(jq -r '.xray_fallback_port // 0' <<< "$host_json")"
  xhttp_server_port="$(jq -r '.nginx_xhttp_public_port // 443' <<< "$host_json")"
  hysteria_server_port="$(jq -r '.hysteria_port // 443' <<< "$host_json")"
  hysteria_port_range="$(jq -r '.hysteria_port_range // ""' <<< "$host_json")"
  hysteria_hop_interval="$(jq -r '.hysteria_hop_interval // "30s"' <<< "$host_json")"
  # Client uTLS fingerprint for this profile. Per-profile via group_vars
  # (xray_utls_fingerprint), default "chrome"; a global UTLS_FINGERPRINT env
  # overrides. Used by the REALITY and XHTTP outbounds only.
  utls_fp="${UTLS_FINGERPRINT:-$(jq -r '.xray_utls_fingerprint // "chrome"' <<< "$host_json")}"
  [[ -z "$utls_fp" || "$utls_fp" == "null" ]] && utls_fp="chrome"

  emit_xhttp=false
  if [[ "$enable_xhttp" == "true" && "$PROFILE_FORMAT" == "ripdpi" ]]; then
    emit_xhttp=true
  fi

  if [[ "$enable_reality" == "true" || "$emit_xhttp" == "true" ]]; then
    client_json="$(jq --arg name "$CLIENT_NAME" '.xray.clients[]? | select(.name==$name)' "$secrets_tmp")"
    if [[ -z "$client_json" || "$client_json" == "null" ]]; then
      echo "enabled Xray profile has no client named '$CLIENT_NAME' in ${sops_file} → xray.clients" >&2
      exit 1
    fi
    uuid="$(echo "$client_json" | jq -r .uuid)"
    short_id="$(echo "$client_json" | jq -r .short_id)"
  fi

  # P0 REALITY — multi-cohort aware. When xray.cohorts is non-empty, emit one
  # outbound per cohort the client is in, each on its own port + flow_mode.
  # Empty cohorts → single outbound on xray_port with vpn.xray_flow_mode.
  if [[ "$enable_reality" == "true" ]]; then
    default_shape="$(jq -ce --arg flow "$flow_mode" '
      .[$flow] | select(
        type == "object"
        and (.client_flow | type == "string")
        and (.client_mux | type == "boolean")
        and (.finalmask | type == "boolean")
      )
    ' <<< "$p0_shapes_json")" || {
      echo "P0 REALITY flow mode '$flow_mode' has no valid p0_reality_shapes descriptor" >&2
      exit 1
    }
    default_finalmask="$(jq -r --argjson shape "$default_shape" '.xray_finalmask // $shape.finalmask' <<< "$vpn_json")"
    reality_pubkey="$(jq -r '.xray.reality_public_key // empty' "$secrets_tmp")"
    sni="$(jq -r '.xray.server_names[0] // empty' "$secrets_tmp")"
    if [[ -z "$reality_pubkey" || -z "$sni" ]]; then
      echo "enabled REALITY profile is missing xray.reality_public_key or xray.server_names in ${sops_file}" >&2
      exit 1
    fi

    cohorts_json="$(jq -c '.xray.cohorts // []' "$secrets_tmp")"
    n_cohorts="$(jq 'length' <<< "$cohorts_json")"

    emit_reality_outbound() {
      # args: tag_suffix port flow finalmask
      local suffix="$1" port="$2" flow="$3" finalmask="$4"
      local shape client_flow client_mux
      shape="$(jq -ce --arg flow "$flow" '
        .[$flow] | select(
          type == "object"
          and (.client_flow | type == "string")
          and (.client_mux | type == "boolean")
          and (.finalmask | type == "boolean")
        )
      ' <<< "$p0_shapes_json")" || {
        echo "P0 REALITY flow mode '$flow' has no valid p0_reality_shapes descriptor" >&2
        exit 1
      }
      client_flow="$(jq -r '.client_flow' <<< "$shape")"
      client_mux="$(jq -r '.client_mux' <<< "$shape")"
      # finalmask is an Xray socket option. Official sing-box has no
      # equivalent client field; fail closed rather than emitting an ignored
      # or unsupported key that would silently diverge from the server shape.
      if [[ "$finalmask" == "true" ]]; then
        echo "P0 REALITY finalmask requires an Xray client; official sing-box cannot represent it" >&2
        exit 1
      fi
      local outb_args=(
        --arg tag "p0-reality-${tag_prefix}${suffix}"
        --arg ip "$server_ip" --arg uuid "$uuid"
        --arg sni "$sni" --arg pk "$reality_pubkey" --arg sid "$short_id"
        --arg fp "$utls_fp" --arg flow "$client_flow"
        --argjson port "$port"
      )
      if [[ "$client_mux" == "true" ]]; then
        OUTBOUNDS="$(echo "$OUTBOUNDS" | jq "${outb_args[@]}" \
          '. += [{type:"vless", tag:$tag, server:$ip, server_port:$port, uuid:$uuid,
                  multiplex:{enabled:true, protocol:"smux", max_streams:8},
                  tls:{enabled:true, server_name:$sni,
                       utls:{enabled:true, fingerprint:$fp},
                       reality:{enabled:true, public_key:$pk, short_id:$sid}}}]')"
      elif [[ -n "$client_flow" ]]; then
        OUTBOUNDS="$(echo "$OUTBOUNDS" | jq "${outb_args[@]}" \
          '. += [{type:"vless", tag:$tag, server:$ip, server_port:$port, uuid:$uuid,
                  flow:$flow,
                  tls:{enabled:true, server_name:$sni,
                       utls:{enabled:true, fingerprint:$fp},
                       reality:{enabled:true, public_key:$pk, short_id:$sid}}}]')"
      else
        OUTBOUNDS="$(echo "$OUTBOUNDS" | jq "${outb_args[@]}" \
          '. += [{type:"vless", tag:$tag, server:$ip, server_port:$port, uuid:$uuid,
                  tls:{enabled:true, server_name:$sni,
                       utls:{enabled:true, fingerprint:$fp},
                       reality:{enabled:true, public_key:$pk, short_id:$sid}}}]')"
      fi
    }

    if (( n_cohorts == 0 )); then
      # Single-cohort: one outbound on xray_port with global flow_mode,
      # plus a second outbound on xray_fallback_port when configured.
      # Both share the same Reality identity — the client treats them as
      # peer endpoints in its selector group so a TLS-cap-policed
      # port-443 path can roll over to the alt-port. Skip the second
      # outbound when fallback is unset or matches the primary port.
      emit_reality_outbound "" "$xray_server_port" "$flow_mode" "$default_finalmask"
      if (( xray_fallback_port > 0 )) && (( xray_fallback_port != xray_server_port )); then
        emit_reality_outbound "-fallback" "$xray_fallback_port" "$flow_mode" "$default_finalmask"
      fi
    else
      # Multi-cohort: emit one outbound per cohort that lists this client.
      client_cohorts="$(jq -c --arg name "$CLIENT_NAME" \
        '.xray.cohorts | map(select(.clients | index($name)))' "$secrets_tmp")"
      n_match="$(jq 'length' <<< "$client_cohorts")"
      if (( n_match == 0 )); then
        echo "client '$CLIENT_NAME' is not listed in any xray.cohorts[].clients in ${sops_file}" >&2
        exit 1
      fi
      for cohort_idx in $(seq 0 $((n_match - 1))); do
        c="$(jq -c ".[$cohort_idx]" <<< "$client_cohorts")"
        c_name="$(jq -r '.name' <<< "$c")"
        c_port="$(jq -r '.port'  <<< "$c")"
        c_flow="$(jq -r --arg default "$flow_mode" '.flow_mode // $default' <<< "$c")"
        # jq's `//` treats false as absent.  A cohort's explicit false must
        # override a true global default, exactly as the server renderer does.
        c_finalmask="$(jq -r --argjson default "$default_finalmask" 'if has("finalmask") then .finalmask else $default end' <<< "$c")"
        emit_reality_outbound "-${c_name}" "$c_port" "$c_flow" "$c_finalmask"
      done
    fi
  fi

  # P1 XHTTP via nginx.
  if [[ "$emit_xhttp" == "true" ]]; then
    nginx_host="$(jq -r '.nginx_xhttp.server_name // empty' "$secrets_tmp")"
    xhttp_path="$(jq -r '.xray.xhttp_path // "/app-sync"' "$secrets_tmp")"
    if [[ -z "$nginx_host" ]]; then
      echo "enabled XHTTP profile is missing nginx_xhttp.server_name in ${sops_file}" >&2
      exit 1
    fi
    OUTBOUNDS="$(echo "$OUTBOUNDS" | jq \
      --arg tag "p1-xhttp-${tag_prefix}" \
      --arg ip "$server_ip" --arg host "$nginx_host" \
      --arg uuid "$uuid" --arg path "$xhttp_path" \
      --arg fp "$utls_fp" \
      --argjson port "$xhttp_server_port" \
      '. += [{type:"vless", tag:$tag, server:$ip, server_port:$port, uuid:$uuid,
              tls:{enabled:true, server_name:$host,
                   utls:{enabled:true, fingerprint:$fp}},
              transport:{type:"xhttp", host:$host, path:$path}}]')"
  fi

  # P2 Hysteria2
  if [[ "$enable_hysteria" == "true" ]]; then
    hy_pw="$(jq --arg n "$CLIENT_NAME" -r '.hysteria.clients[]? | select(.name==$n) | .password // empty' "$secrets_tmp")"
    hy_host="$(jq -r '.hysteria.server_name // .nginx_xhttp.server_name // empty' "$secrets_tmp")"
    hy_obfs_enabled="$(jq -r '.hysteria.salamander_enabled // false' "$secrets_tmp")"
    hy_obfs_pw="$(jq -r '.hysteria.salamander_password // empty' "$secrets_tmp")"
    if [[ -z "$hy_pw" ]]; then
      echo "enabled Hysteria2 profile has no client named '$CLIENT_NAME' in ${sops_file} → hysteria.clients" >&2
      exit 1
    fi
    hy_auth="${CLIENT_NAME}:${hy_pw}"
    if [[ -z "$hy_host" ]]; then
      echo "enabled Hysteria2 profile is missing hysteria.server_name or nginx_xhttp.server_name in ${sops_file}" >&2
      exit 1
    fi
    obfs_arg=null
    if [[ "$hy_obfs_enabled" == "true" && -n "$hy_obfs_pw" ]]; then
      obfs_arg="$(jq -n --arg p "$hy_obfs_pw" '{type:"salamander", password:$p}')"
    fi
    # Port-hopping: sing-box expects ["low:high", ...] in server_ports.
    hop_ports_arg=null
    hop_interval_arg=null
    if [[ -n "$hysteria_port_range" ]]; then
      hop_lo="${hysteria_port_range%-*}"
      hop_hi="${hysteria_port_range#*-}"
      hop_ports_arg="$(jq -nc --arg lh "${hop_lo}:${hop_hi}" '[$lh]')"
      hop_interval_arg="$(jq -nc --arg i "$hysteria_hop_interval" '$i')"
    fi
    OUTBOUNDS="$(echo "$OUTBOUNDS" | jq \
      --arg tag "p2-hysteria2-${tag_prefix}" \
      --arg ip "$server_ip" --arg host "$hy_host" --arg pw "$hy_auth" \
      --argjson obfs "$obfs_arg" \
      --argjson port "$hysteria_server_port" \
      --argjson hop_ports "$hop_ports_arg" \
      --argjson hop_interval "$hop_interval_arg" \
      '. += [{type:"hysteria2", tag:$tag, server:$ip, server_port:$port,
              server_ports:$hop_ports, hop_interval:$hop_interval,
              password:$pw, tls:{enabled:true, server_name:$host}, obfs:$obfs}
             | with_entries(select(.value != null))]')"
  fi

  if [[ "$enable_snell" == "true" ]]; then
    snell_variants="$(jq -c '.snell.variants // []' <<< "$host_json")"
    variant_count="$(jq 'length' <<< "$snell_variants")"
    (( variant_count > 0 )) || { echo "enabled Snell profile has no snell.variants" >&2; exit 1; }
    for variant_idx in $(seq 0 $((variant_count - 1))); do
      variant="$(jq -c ".[$variant_idx]" <<< "$snell_variants")"
      variant_id="$(jq -r '.id' <<< "$variant")"
      variant_port="$(jq -r '.listen_port' <<< "$variant")"
      client_version="$(jq -r '.client_version' <<< "$variant")"
      secret_variant="$(jq -c --arg id "$variant_id" '.snell_secrets.variants[]? | select(.id == $id)' "$secrets_tmp")"
      [[ -n "$secret_variant" && "$secret_variant" != "null" ]] || { echo "enabled Snell variant '$variant_id' is missing from secrets" >&2; exit 1; }
      snell_psk="$(jq -r '.psk // empty' <<< "$secret_variant")"
      snell_userkey="$(jq -r --arg name "$CLIENT_NAME" '.users[]? | select(.name == $name) | .userkey // empty' <<< "$secret_variant")"
      [[ -n "$snell_psk" && -n "$snell_userkey" ]] || { echo "enabled Snell variant '$variant_id' has no client named '$CLIENT_NAME'" >&2; exit 1; }
      for reuse in false true; do
        reuse_label=fresh
        [[ "$reuse" == true ]] && reuse_label=reuse
        tag="p3-snell-${variant_id}-${reuse_label}-${tag_prefix}"
        if [[ "$client_version" == 4 ]]; then
          OUTBOUNDS="$(echo "$OUTBOUNDS" | jq --arg tag "$tag" --arg ip "$server_ip" --arg psk "$snell_psk" --arg userkey "$snell_userkey" --argjson port "$variant_port" --argjson reuse "$reuse" '. += [{type:"snell",tag:$tag,server:$ip,server_port:$port,version:4,psk:$psk,userkey:$userkey,reuse:$reuse,network:"tcp",obfs_mode:"none"}]')"
        else
          snell_mode="$(jq -r '.mode // "default"' <<< "$variant")"
          OUTBOUNDS="$(echo "$OUTBOUNDS" | jq --arg tag "$tag" --arg ip "$server_ip" --arg psk "$snell_psk" --arg userkey "$snell_userkey" --arg mode "$snell_mode" --argjson port "$variant_port" --argjson reuse "$reuse" '. += [{type:"snell",tag:$tag,server:$ip,server_port:$port,version:6,psk:$psk,userkey:$userkey,reuse:$reuse,network:"tcp",mode:$mode}]')"
        fi
        SNELL_TAGS="$(jq -nc --argjson tags "$SNELL_TAGS" --arg tag "$tag" '$tags + [$tag]')"
      done
    done
  fi
done

# ---------------------------------------------------------------------------
# Add selector + urltest + boilerplate
# ---------------------------------------------------------------------------
if [[ "$(jq 'length' <<< "$OUTBOUNDS")" -eq 0 ]]; then
  echo "no enabled ${PROFILE_FORMAT} outbounds resolved from Ansible profile toggles" >&2
  exit 1
fi

OUTBOUNDS="$(jq -nc --argjson obs "$OUTBOUNDS" --argjson snell "$SNELL_TAGS" '
  ($obs | map(.tag) | map(select(. as $tag | ($snell | index($tag) | not)))) as $automatic |
  $obs +
  (if ($snell|length)>0 then [{type:"selector",tag:"snell-evaluation",outbounds:$snell,default:$snell[0],interrupt_exist_connections:false}] else [] end) +
  [{type:"selector",tag:"select",outbounds:($automatic + (if ($automatic|length)>0 then ["auto"] else ["direct"] end) + (if ($snell|length)>0 then ["snell-evaluation"] else [] end)),default:(if ($automatic|length)>0 then "auto" else "direct" end),interrupt_exist_connections:false}] +
  (if ($automatic|length)>0 then [{type:"urltest",tag:"auto",outbounds:$automatic,url:"https://www.gstatic.com/generate_204",interval:"5m",tolerance:50}] else [] end) +
  [{type:"direct",tag:"direct"},{type:"block",tag:"block"}]')"

# Build per-app route rules (Android only — sing-box silently ignores
# package_name on non-Android platforms, so the same bundle works
# everywhere). Bypass rules come first so they short-circuit the
# tunnel; via-tun rules are below so they override any later defaults.
per_app_rules='[]'
if [[ -n "$PER_APP_BYPASS" ]]; then
  per_app_rules="$(jq -nc --arg csv "$PER_APP_BYPASS" '
    [{
      "package_name": ($csv | split(",") | map(select(length > 0))),
      "action": "route",
      "outbound": "direct"
    }]')"
fi
if [[ -n "$PER_APP_VIA_TUN" ]]; then
  via_tun_rule="$(jq -nc --arg csv "$PER_APP_VIA_TUN" '
    {
      "package_name": ($csv | split(",") | map(select(length > 0))),
      "action": "route",
      "outbound": "select"
    }')"
  per_app_rules="$(jq -nc --argjson cur "$per_app_rules" --argjson r "$via_tun_rule" '$cur + [$r]')"
fi

jq -n \
  --arg client "$CLIENT_NAME" \
  --argjson outbounds "$OUTBOUNDS" \
  --argjson per_app "$per_app_rules" \
  '{
    "log": {"level":"warn", "timestamp":true},
    "dns": {
      "servers": [
        {"type":"https", "tag":"remote", "server":"1.1.1.1", "detour":"select"}
      ]
    },
    "inbounds": [{
      "type":"tun", "tag":"tun-in",
      "interface_name":"tun0",
      "address":["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
      "auto_route":true, "strict_route":true,
      "stack":"system"
    }],
    "outbounds": $outbounds,
    "route": {
      "rules":
        ($per_app +
        [
          {"action":"sniff"},
          {"protocol":"dns", "action":"hijack-dns"}
        ]),
      "final":"select",
      "auto_detect_interface":true
    }
  }'
