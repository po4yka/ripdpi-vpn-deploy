#!/usr/bin/env bash
# Generate a complete, self-contained secrets YAML for a CI deploy.
# Used by .github/workflows/real-vps-deploy.yml — no SOPS-encrypted
# blob is committed to the repo; every CI run gets fresh crypto.
#
# What this script generates:
#   * REALITY x25519 keypair (xray)
#   * one test client UUID + shortId
#   * a self-signed cert (CA + leaf) for nginx_xhttp + hysteria, SAN-
#     covering the ${SERVER_NAME} the workflow uses
#   * Hysteria client password
#   * AmneziaWG server private key + four random H1-H4 ints + one
#     peer (the role itself is disabled in the CI deploy via
#     group_vars, but the schema still needs the fields)
#   * naive_secrets fields (role disabled)
#   * geodata pinned URLs + sha256 (role disabled — these are
#     placeholders since the role's get_url is gated on
#     vpn.enable_geodata)
#   * backup restic_password
#   * watchdog_secrets.ntfy_topic
#
# What this script does NOT generate:
#   * Xray / Hysteria release-asset sha256s — those come from the
#     SECRETS schema versions pinned in secrets/prod.secrets.example.
#     The script reads xray.version + hysteria.version from the
#     example schema and pins the same; release-asset sha256 is
#     computed on the fly with curl + sha256sum (so we exercise the
#     real download path rather than committing test sha256s).
#
# Required env:
#   OUT          path to write the YAML (e.g. /tmp/vpn-ci.secrets.yaml)
#   SERVER_NAME  hostname the cert covers (e.g. vpn-ci.example.test)
#   CLIENT_NAME  test client name (default: ci-test)
set -euo pipefail

OUT="${OUT:?OUT path is required}"
SERVER_NAME="${SERVER_NAME:?SERVER_NAME is required}"
CLIENT_NAME="${CLIENT_NAME:-ci-test}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLE="${REPO_ROOT}/secrets/prod.secrets.example.yaml"
[[ -f "$EXAMPLE" ]] || { echo "missing $EXAMPLE" >&2; exit 2; }

for tool in openssl python3 curl sha256sum uuidgen wg; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ci-bootstrap-secrets: missing tool '$tool'" >&2; exit 2; }
done

# ---------------------------------------------------------------------------
# Read versions from the schema so CI matches the v1 default.
# ---------------------------------------------------------------------------
xray_version="$(python3 -c "
import yaml; d=yaml.safe_load(open('$EXAMPLE')) or {}
print((d.get('xray') or {}).get('version') or 'v26.3.27')
")"
hys_version="$(python3 -c "
import yaml; d=yaml.safe_load(open('$EXAMPLE')) or {}
print((d.get('hysteria') or {}).get('version') or 'v2.9.0')
")"

# ---------------------------------------------------------------------------
# Compute release-asset sha256 on the fly.
# ---------------------------------------------------------------------------
xray_url="https://github.com/XTLS/Xray-core/releases/download/${xray_version}/Xray-linux-64.zip"
hys_url="https://github.com/apernet/hysteria/releases/download/app/${hys_version}/hysteria-linux-amd64"
echo "ci-bootstrap: fetching sha256 for ${xray_version} + ${hys_version}" >&2
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
curl -fsSL -o "$tmpdir/xray.zip" "$xray_url"
curl -fsSL -o "$tmpdir/hysteria"  "$hys_url"
xray_sha="$(sha256sum "$tmpdir/xray.zip"  | awk '{print $1}')"
hys_sha="$( sha256sum "$tmpdir/hysteria" | awk '{print $1}')"

# ---------------------------------------------------------------------------
# REALITY keypair. Use Xray docker image so we don't need a local xray.
# Note: ghcr.io/xtls/xray-core:<version> is a floating tag; a digest pin is
# preferred for supply-chain safety but cannot be resolved offline. Capture
# the actual image digest after pull so it is logged and auditable.
# ---------------------------------------------------------------------------
reality_raw="$(docker run --rm "ghcr.io/xtls/xray-core:${xray_version}" x25519 2>/dev/null || true)"
# Log the resolved image digest for audit purposes.
xray_image_digest="$(docker inspect --format '{{.Id}}' "ghcr.io/xtls/xray-core:${xray_version}" 2>/dev/null || true)"
if [[ -n "$xray_image_digest" ]]; then
  echo "ci-bootstrap: xray image digest: ${xray_image_digest}" >&2
else
  echo "ci-bootstrap: warning: could not resolve xray image digest (image may not be locally cached)" >&2
fi
if [[ -z "$reality_raw" ]]; then
  # Fall back to a local xray binary if available (post-deploy reruns
  # on the operator workstation).
  if command -v xray >/dev/null 2>&1; then
    reality_raw="$(xray x25519)"
  else
    echo "ci-bootstrap: cannot generate REALITY keypair (no docker, no local xray)" >&2
    exit 2
  fi
fi
reality_priv="$(echo "$reality_raw" | awk -F': ' '/Private/{print $2}' | tr -d '\r\n ')"
reality_pub="$( echo "$reality_raw" | awk -F': ' '/Public/ {print $2}' | tr -d '\r\n ')"

# ---------------------------------------------------------------------------
# Self-signed cert covering SERVER_NAME.
# ---------------------------------------------------------------------------
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -keyout "$tmpdir/key.pem" -out "$tmpdir/cert.pem" \
  -subj "/CN=${SERVER_NAME}" \
  -addext "subjectAltName=DNS:${SERVER_NAME}" \
  >/dev/null 2>&1
cert_pem="$(awk '{printf "    %s\n",$0}' "$tmpdir/cert.pem")"
key_pem="$( awk '{printf "    %s\n",$0}' "$tmpdir/key.pem")"

# ---------------------------------------------------------------------------
# Per-client creds + AWG materials.
# ---------------------------------------------------------------------------
uuid="$(uuidgen | tr 'A-Z' 'a-z')"
sid="$(openssl rand -hex 4)"
hys_pw="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
awg_priv="$(wg genkey)"
peer_priv="$(wg genkey)"
peer_pub="$(echo "$peer_priv" | wg pubkey)"
peer_psk="$(wg genpsk)"
restic_pw="$(openssl rand -base64 32 | tr -d '\n')"
ntfy_topic="ci-$(openssl rand -hex 8)"
naive_pw="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
naive_probe="$(openssl rand -hex 16)"
H1="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"
H2="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"
H3="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"
H4="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"

# ---------------------------------------------------------------------------
# Emit the YAML.
# ---------------------------------------------------------------------------
umask 077
cat > "$OUT" <<YAML
# Generated by scripts/ci-bootstrap-secrets.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# CI-only synthetic values. NEVER promote this file to a production env.

xray:
  version: "${xray_version}"
  linux_amd64_sha256: "${xray_sha}"
  linux_arm64_sha256: "${xray_sha}"
  reality_private_key: "${reality_priv}"
  reality_public_key:  "${reality_pub}"
  target: "${SERVER_NAME}:443"
  server_names: ["${SERVER_NAME}"]
  xhttp_path: "/$(openssl rand -hex 4)"
  clients:
    - name: ${CLIENT_NAME}
      uuid: "${uuid}"
      short_id: "${sid}"
  cohorts: []

nginx_xhttp:
  server_name: "${SERVER_NAME}"
  cert_pem: |
$(echo "$cert_pem")
  key_pem: |
$(echo "$key_pem")

hysteria:
  version: "${hys_version}"
  linux_amd64_sha256: "${hys_sha}"
  linux_arm64_sha256: "${hys_sha}"
  cert_pem: |
$(echo "$cert_pem")
  key_pem: |
$(echo "$key_pem")
  bandwidth_up: "100 mbps"
  bandwidth_down: "200 mbps"
  salamander_enabled: false
  salamander_password: ""
  clients:
    - name: ${CLIENT_NAME}
      password: "${hys_pw}"

naive_secrets:
  server_name: "${SERVER_NAME}"
  username: "ci-user"
  password: "${naive_pw}"
  probe_resistance_secret: "${naive_probe}"
  cert_pem: |
$(echo "$cert_pem")
  key_pem: |
$(echo "$key_pem")

geodata:
  geosite_url: "https://example.invalid/geosite.dat"
  geoip_url:   "https://example.invalid/geoip.dat"
  geosite_sha256: "$(printf '0%.0s' {1..64})"
  geoip_sha256:   "$(printf '0%.0s' {1..64})"
  install_dir: /usr/local/share/xray
  refresh_interval: "1d"

amneziawg_go_version: "v0.2.12"
amneziawg_tools_version: "v1.0.20240725"

amneziawg_secrets:
  server_private_key: "${awg_priv}"
  jc: 4
  jmin: 40
  jmax: 70
  s1: 50
  s2: 100
  h1: ${H1}
  h2: ${H2}
  h3: ${H3}
  h4: ${H4}
  peers:
    - name: ${CLIENT_NAME}
      public_key: "${peer_pub}"
      preshared_key: "${peer_psk}"
      allowed_ips: "10.66.66.2/32"
  instances: []

backup:
  restic_password: "${restic_pw}"
  remote:
    enabled: false
    rclone_remote: ""
    rclone_path: ""
    transfers: 4
    bwlimit: "off"
    rclone_config: ""

watchdog_secrets:
  ntfy_topic: "${ntfy_topic}"
YAML
chmod 0600 "$OUT"
echo "ci-bootstrap: wrote ${OUT} (xray=${xray_version} hysteria=${hys_version})"
