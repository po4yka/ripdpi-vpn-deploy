#!/usr/bin/env bash
# Cert hygiene check for the public-CA-issued certificates that the
# stack actually serves: nginx_xhttp, hysteria, naive_secrets. For each:
#   * not a placeholder
#   * openssl can parse it
#   * issuer != subject (not self-signed)
#   * SAN covers the configured server_name / SNI
#   * expiry > 14 days from now
#   * cert modulus matches key modulus (RSA)
#
# Reads $VPN_SECRETS_FILE or the path passed as $1.
#
# Wired in via `make check-certs` and as a pre-flight in `make verify`.
set -euo pipefail

src="${VPN_SECRETS_FILE:-${1:-}}"
if [[ -z "$src" || ! -f "$src" ]]; then
  echo "usage: VPN_SECRETS_FILE=/tmp/vpn-prod.secrets.yaml $0" >&2
  exit 2
fi

for tool in openssl python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing tool: $tool" >&2; exit 2; }
done

findings=0
report() { echo "  - $1"; findings=$((findings+1)); }

extract() {
  local block="$1" field="$2"
  python3 -c "
import sys, yaml
data = yaml.safe_load(open('$src')) or {}
v = (data.get('$block') or {}).get('$field') or ''
sys.stdout.write(v if isinstance(v, str) else '')
"
}

check_block() {
  local block="$1" host_field="$2"
  local host cert key
  host="$( extract "$block" "$host_field" )"
  cert="$( extract "$block" cert_pem )"
  key="$(  extract "$block" key_pem  )"

  echo "[$block] host=${host:-?}"

  if [[ -z "$cert" || "$cert" == *REPLACE_WITH* ]]; then
    report "cert_pem is placeholder or empty"
    return
  fi
  if [[ -z "$key" || "$key" == *REPLACE_WITH* ]]; then
    report "key_pem is placeholder or empty"
    return
  fi

  local subj issuer
  if ! subj="$(printf '%s\n' "$cert" | openssl x509 -noout -subject 2>/dev/null)"; then
    report "openssl could not parse cert_pem"
    return
  fi
  issuer="$(printf '%s\n' "$cert" | openssl x509 -noout -issuer 2>/dev/null)"
  if [[ "${subj#subject=}" == "${issuer#issuer=}" ]]; then
    report "appears self-signed (subject == issuer)"
  fi

  # SAN coverage
  if [[ -n "$host" ]]; then
    local san_lines
    san_lines="$(printf '%s\n' "$cert" \
      | openssl x509 -noout -ext subjectAltName 2>/dev/null \
      | grep DNS: || true)"
    if ! grep -qiE "(^|, )DNS:${host//./\\.}(,|$)" <<< "$san_lines"; then
      # also tolerate single wildcard one-level above
      local parent_re="(^|, )DNS:\\*\\.${host#*.}(,|$)"
      if ! grep -qiE "$parent_re" <<< "$san_lines"; then
        report "SAN does not cover ${host}"
      fi
    fi
  fi

  # Expiry
  local end_iso days
  end_iso="$(printf '%s\n' "$cert" | openssl x509 -noout -enddate 2>/dev/null | sed 's/notAfter=//')"
  if [[ -n "$end_iso" ]]; then
    days="$(python3 -c "
from datetime import datetime, timezone
import sys
end = datetime.strptime('''$end_iso''', '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
print((end - datetime.now(timezone.utc)).days)
")"
    if   (( days < 0  )); then report "expired $((-days)) days ago ($end_iso)"
    elif (( days < 14 )); then report "expires in $days days ($end_iso) — renew now"
    fi
  fi

  # Compare public-key DER digests. Unlike RSA modulus this works for EC too.
  local cert_pub key_pub
  cert_pub="$(printf '%s\n' "$cert" | openssl x509 -pubkey -noout 2>/dev/null | openssl pkey -pubin -outform DER 2>/dev/null | openssl sha256 2>/dev/null || true)"
  key_pub="$(printf '%s\n' "$key" | openssl pkey -pubout -outform DER 2>/dev/null | openssl sha256 2>/dev/null || true)"
  if [[ -z "$cert_pub" || -z "$key_pub" || "$cert_pub" != "$key_pub" ]]; then
    report "certificate public key does not match private key"
  fi
}

check_block nginx_xhttp   server_name
check_block hysteria      server_name   # falls back to server_name -- ok if absent
check_block naive_secrets server_name

echo
if (( findings == 0 )); then
  echo "OK — certs healthy"
  exit 0
else
  echo "$findings finding(s) — fix before deploy"
  exit 1
fi
