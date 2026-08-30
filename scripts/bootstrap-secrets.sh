#!/usr/bin/env bash
# One-shot bootstrap of a fresh secrets blob for a new environment.
# Generates every piece of crypto the deploy needs and writes it into
# ${VPN_PROVISION_CONFIG_DIR:-~/.config/vpn-provision}/<env>.secrets.yaml, then SOPS-encrypts to
# <env>.secrets.sops.yaml. Refuses to clobber existing files unless
# --force is given.
#
# This closes the day-one error class where the operator copy-pastes
# REPLACE_WITH_* placeholders, leaves H1..H4 at "REPLACE", or drops a
# key into shell history.
#
# Usage:
#   scripts/bootstrap-secrets.sh --env prod --clients phone,laptop \
#       --target mirror.example.com:443 --server-name mirror.example.com \
#       --xhttp-host vpn.example.com
#
# Required flags: --target, --server-name (so the schema isn't a
# placeholder — the validator catches it otherwise).
set -euo pipefail

ENV=prod
CLIENTS=phone
TARGET=""
SERVER_NAME=""
XHTTP_HOST=""
FORCE=0
AWG_GO_VERSION="v0.2.12"
AWG_GO_COMMIT="2e3f7d122ca8ef61e403fddc48a9db8fccd95dbf"
AWG_TOOLS_VERSION="v1.0.20241018"
AWG_TOOLS_COMMIT="c0b400c6dfc046f5cae8f3051b14cb61686fcf55"

usage() {
  cat >&2 <<USAGE
usage: $0 --target HOST:PORT --server-name HOST [options]
  --env NAME        environment label (default: prod)
  --clients LIST    comma-separated client names (default: phone)
  --target SNI:PORT REALITY target (host:port)
  --server-name H   REALITY serverName (single hostname; SAN-covered)
  --xhttp-host H    nginx-xhttp server_name (defaults to --server-name)
  --force           overwrite existing files

Generates: age key (if missing), REALITY x25519 keypair, per-client
UUIDs and 8-hex shortIds, restic password, AmneziaWG server key, four
random H1..H4 integers. Writes plaintext + SOPS-encrypted output to
~/.config/vpn-provision/.
USAGE
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="$2"; shift 2 ;;
    --clients) CLIENTS="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --server-name) SERVER_NAME="$2"; shift 2 ;;
    --xhttp-host) XHTTP_HOST="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

[[ -n "$TARGET" && -n "$SERVER_NAME" ]] || usage
[[ -z "$XHTTP_HOST" ]] && XHTTP_HOST="$SERVER_NAME"
command -v python3 >/dev/null 2>&1 || { echo "missing tool: python3" >&2; exit 1; }

BOOTSTRAP_ENV="$ENV" \
BOOTSTRAP_CLIENTS="$CLIENTS" \
BOOTSTRAP_TARGET="$TARGET" \
BOOTSTRAP_SERVER_NAME="$SERVER_NAME" \
BOOTSTRAP_XHTTP_HOST="$XHTTP_HOST" \
python3 - <<'PY'
import ipaddress
import os
import re

environment = os.environ["BOOTSTRAP_ENV"]
clients_raw = os.environ["BOOTSTRAP_CLIENTS"]
target = os.environ["BOOTSTRAP_TARGET"]
server_name = os.environ["BOOTSTRAP_SERVER_NAME"]
xhttp_host = os.environ["BOOTSTRAP_XHTTP_HOST"]
slug_pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
label_pattern = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def fail(message: str) -> None:
    raise SystemExit(message)


def valid_dns_hostname(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return False
    except ValueError:
        pass
    if re.fullmatch(r"[0-9.]+", value):
        return False
    return 0 < len(value) <= 253 and not value.endswith(".") and all(label_pattern.fullmatch(label) for label in value.split("."))


if not slug_pattern.fullmatch(environment):
    fail("invalid environment name: use 1-64 letters, digits, underscores, or dashes")

clients = clients_raw.split(",")
if not clients_raw or any(not slug_pattern.fullmatch(client) for client in clients):
    fail("invalid client list: every name must use 1-64 letters, digits, underscores, or dashes")
if len(clients) != len(set(clients)):
    fail("duplicate client name in --clients")

if not valid_dns_hostname(server_name):
    fail("invalid server name: expected a DNS hostname")
if not valid_dns_hostname(xhttp_host):
    fail("invalid xhttp hostname: expected a DNS hostname")

if target.count(":") != 1:
    fail("invalid target: expected DNS_OR_IPV4:PORT")
host, port_text = target.rsplit(":", 1)
if not port_text.isdigit():
    fail("invalid target: port must be numeric")
try:
    valid_host = ipaddress.ip_address(host).version == 4
except ValueError:
    valid_host = valid_dns_hostname(host)
if not valid_host:
    fail("invalid target: malformed DNS hostname or IPv4 address")
port = int(port_text)
if not 1 <= port <= 65535:
    fail("invalid target: port must be between 1 and 65535")
PY

yaml_scalar() {
  python3 -c 'import json, sys; print(json.dumps(sys.stdin.read()))'
}
TARGET_YAML="$(printf '%s' "$TARGET" | yaml_scalar)"
SERVER_NAME_YAML="$(printf '%s' "$SERVER_NAME" | yaml_scalar)"
XHTTP_HOST_YAML="$(printf '%s' "$XHTTP_HOST" | yaml_scalar)"

CONFIG_DIR="${VPN_PROVISION_CONFIG_DIR:-${HOME}/.config/vpn-provision}"
mkdir -p "$CONFIG_DIR"
chmod 0700 "$CONFIG_DIR"

PLAINTEXT="${CONFIG_DIR}/${ENV}.secrets.yaml"
ENCRYPTED="${CONFIG_DIR}/${ENV}.secrets.sops.yaml"
AGE_KEY="${CONFIG_DIR}/age.key"

if [[ "$FORCE" != 1 && -f "$ENCRYPTED" ]]; then
  echo "refuse: $ENCRYPTED exists. Use --force to clobber." >&2
  exit 1
fi

for tool in sops age age-keygen openssl uuidgen wg sed; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "missing tool: $tool" >&2; exit 1; }
done

# ---------------------------------------------------------------------------
# age keypair — only generate if missing
# ---------------------------------------------------------------------------
if [[ ! -f "$AGE_KEY" ]]; then
  echo ">>> generating age keypair at $AGE_KEY"
  age-keygen -o "$AGE_KEY"
  chmod 0600 "$AGE_KEY"
fi
AGE_RECIPIENT="$(grep '^# public key:' "$AGE_KEY" | awk '{print $4}')"
[[ -n "$AGE_RECIPIENT" ]] || { echo "could not extract age recipient" >&2; exit 1; }
echo ">>> age recipient: $AGE_RECIPIENT"

# ---------------------------------------------------------------------------
# REALITY keypair — prefer local xray, fall back to docker.
# ---------------------------------------------------------------------------
echo ">>> generating REALITY x25519 keypair"
if command -v xray >/dev/null 2>&1; then
  REALITY_RAW="$(xray x25519)"
elif command -v docker >/dev/null 2>&1; then
  REALITY_RAW="$(docker run --rm ghcr.io/xtls/xray-core x25519)"
else
  echo "need either 'xray' or 'docker' to generate the REALITY keypair" >&2
  exit 1
fi
REALITY_PRIV="$(echo "$REALITY_RAW" | awk -F': ' '/Private/{print $2}' | tr -d '\r\n ')"
REALITY_PUB="$( echo "$REALITY_RAW" | awk -F': ' '/Public/ {print $2}' | tr -d '\r\n ')"
[[ -n "$REALITY_PRIV" && -n "$REALITY_PUB" ]] || {
  echo "could not parse xray x25519 output:" >&2; echo "$REALITY_RAW" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Per-client UUIDs + 8-hex shortIds
# ---------------------------------------------------------------------------
declare -a CLIENT_BLOCKS_XRAY
declare -a CLIENT_BLOCKS_HYS
IFS=',' read -r -a client_list <<< "$CLIENTS"
for name in "${client_list[@]}"; do
  name_yaml="$(printf '%s' "$name" | yaml_scalar)"
  uuid="$(uuidgen | tr 'A-Z' 'a-z')"
  sid="$(openssl rand -hex 4)"
  CLIENT_BLOCKS_XRAY+=("    - name: ${name_yaml}
      uuid: \"${uuid}\"
      short_id: \"${sid}\"")

  hys_pw="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
  CLIENT_BLOCKS_HYS+=("    - name: ${name_yaml}
      password: \"${hys_pw}\"")

done

# Do not create AmneziaWG peers here: their private keys must be handed to a
# device exactly once. Use scripts/new-client.sh after bootstrap; it emits the
# client private key through the operator-controlled secure handoff path.

# ---------------------------------------------------------------------------
# AmneziaWG server params + random H1..H4
# ---------------------------------------------------------------------------
AWG_SERVER_PRIV="$(wg genkey)"
H1="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"
H2="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"
H3="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"
H4="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"

# ---------------------------------------------------------------------------
# Restic password
# ---------------------------------------------------------------------------
RESTIC_PASSWORD="$(openssl rand -base64 32 | tr -d '\n')"

# ---------------------------------------------------------------------------
# ntfy topic (long random)
# ---------------------------------------------------------------------------
NTFY_TOPIC="vpn-$(openssl rand -hex 8)"

# ---------------------------------------------------------------------------
# Compose plaintext YAML
# ---------------------------------------------------------------------------
umask 077
{
  cat <<HEAD
# Generated by scripts/bootstrap-secrets.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Recipient: $AGE_RECIPIENT
# Plaintext file path will be sops-encrypted immediately.

xray:
  version: "v26.3.27"
  linux_amd64_sha256: "REPLACE_WITH_RELEASE_SHA256"
  linux_arm64_sha256: "REPLACE_WITH_RELEASE_SHA256"
  source_commit: "REPLACE_WITH_40_OR_64_HEX_COMMIT"
  source_binary_sha256: "REPLACE_WITH_RELEASE_SHA256"

  reality_private_key: "${REALITY_PRIV}"
  reality_public_key: "${REALITY_PUB}"

  target: ${TARGET_YAML}
  server_names:
    - ${SERVER_NAME_YAML}

  xhttp_path: "/$(openssl rand -hex 4)"

  clients:
HEAD
  for block in "${CLIENT_BLOCKS_XRAY[@]}"; do echo "$block"; done

  cat <<NGX

nginx_xhttp:
  server_name: ${XHTTP_HOST_YAML}
  cert_pem: |
    -----BEGIN CERTIFICATE-----
    REPLACE_WITH_FULLCHAIN
    -----END CERTIFICATE-----
  key_pem: |
    -----BEGIN PRIVATE KEY-----
    REPLACE_WITH_PRIVATE_KEY
    -----END PRIVATE KEY-----

reality_self_steal:
  server_name: ${SERVER_NAME_YAML}
  cert_pem: |
    -----BEGIN CERTIFICATE-----
    REPLACE_WITH_SELF_STEAL_FULLCHAIN
    -----END CERTIFICATE-----
  key_pem: |
    -----BEGIN PRIVATE KEY-----
    REPLACE_WITH_SELF_STEAL_PRIVATE_KEY
    -----END PRIVATE KEY-----

hysteria:
  version: "v2.9.0"
  linux_amd64_sha256: "REPLACE_WITH_RELEASE_SHA256"
  linux_arm64_sha256: "REPLACE_WITH_RELEASE_SHA256"
  cert_pem: |
    -----BEGIN CERTIFICATE-----
    REPLACE_WITH_FULLCHAIN
    -----END CERTIFICATE-----
  key_pem: |
    -----BEGIN PRIVATE KEY-----
    REPLACE_WITH_PRIVATE_KEY
    -----END PRIVATE KEY-----
  bandwidth_up: "100 mbps"
  bandwidth_down: "200 mbps"
  masquerade_url: "https://${XHTTP_HOST}"
  salamander_enabled: false
  salamander_password: ""
  clients:
NGX
  for block in "${CLIENT_BLOCKS_HYS[@]}"; do echo "$block"; done

  cat <<NAIVE

naive_secrets:
  server_name: ${XHTTP_HOST_YAML}
  username: "u-$(openssl rand -hex 4)"
  password: "$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
  probe_resistance_secret: "$(openssl rand -hex 16)"
  cert_pem: |
    -----BEGIN CERTIFICATE-----
    REPLACE_WITH_FULLCHAIN
    -----END CERTIFICATE-----
  key_pem: |
    -----BEGIN PRIVATE KEY-----
    REPLACE_WITH_PRIVATE_KEY
    -----END PRIVATE KEY-----

geodata:
  geosite_url: "REPLACE_WITH_PINNED_GEOSITE_RELEASE_URL"
  geoip_url:   "REPLACE_WITH_PINNED_GEOIP_RELEASE_URL"
  geosite_sha256: "REPLACE_WITH_RELEASE_SHA256"
  geoip_sha256:   "REPLACE_WITH_RELEASE_SHA256"
  install_dir: /usr/local/share/xray
  refresh_interval: "1d"

amneziawg_go_version: "${AWG_GO_VERSION}"
amneziawg_go_commit: "${AWG_GO_COMMIT}"
amneziawg_tools_version: "${AWG_TOOLS_VERSION}"
amneziawg_tools_commit: "${AWG_TOOLS_COMMIT}"

amneziawg_secrets:
  server_private_key: "${AWG_SERVER_PRIV}"
  jc: 4
  jmin: 40
  jmax: 70
  s1: 50
  s2: 100
  h1: ${H1}
  h2: ${H2}
  h3: ${H3}
  h4: ${H4}
  peers: []
NAIVE

  cat <<TAIL

backup:
  restic_password: "${RESTIC_PASSWORD}"
  remote:
    enabled: false
    rclone_remote: "offsite"
    rclone_path: "vpn-backups"
    transfers: 4
    bwlimit: "off"
    rclone_config: ""

watchdog_secrets:
  ntfy_topic: "${NTFY_TOPIC}"
  reality_probe_url: "https://${XHTTP_HOST}/"
  reality_probe_expected_status: 200
TAIL
} > "$PLAINTEXT"
chmod 0600 "$PLAINTEXT"
echo ">>> wrote plaintext: $PLAINTEXT"

# ---------------------------------------------------------------------------
# SOPS-encrypt and shred the plaintext
# ---------------------------------------------------------------------------
sops --encrypt --age "$AGE_RECIPIENT" "$PLAINTEXT" > "$ENCRYPTED"
chmod 0600 "$ENCRYPTED"
shred -u "$PLAINTEXT" 2>/dev/null || rm -f "$PLAINTEXT"
echo ">>> encrypted to: $ENCRYPTED"
echo
echo "Next: edit with  sops $ENCRYPTED"
echo "Still TODO (REPLACE_WITH_*):"
echo "  * Xray / Hysteria / geodata version sha256 (release page)"
echo "  * nginx_xhttp + hysteria + naive cert_pem + key_pem (LE / ACME)"
echo "  * geodata pinned URLs"
echo "  * verify AmneziaWG version/commit pairs before intentionally changing them"
echo
echo "Then run:  make spot-check-secrets   # catches remaining placeholders"
