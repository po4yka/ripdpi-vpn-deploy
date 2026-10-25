#!/usr/bin/env bash
# Cert hygiene check for the public-CA-issued certificates that the
# stack actually serves: nginx_xhttp, hysteria, naive_secrets, self-steal.
# Select only the enabled authorities. For each:
#   * not a placeholder
#   * openssl can parse it
#   * issuer != subject (not self-signed)
#   * SAN covers the configured server_name / SNI
#   * valid dates, trusted issuer chain, and TLS server purpose
#   * expiry > 14 days from now
#   * certificate public key matches its private key (RSA or EC)
#
# Reads $VPN_SECRETS_FILE or the path passed as $1.
# VPN_CERT_VARS_FILES is an ordered JSON list of complete effective vars files.
# Without it, use canonical all/vpn defaults and the supplied secrets.
# OpenSSL uses the operator trust store (SSL_CERT_FILE / SSL_CERT_DIR).
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

umask 077
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/vpn-check-certs.XXXXXX")"
# shellcheck disable=SC2329  # Invoked indirectly by the EXIT trap.
cleanup() {
  local status=$? file
  trap - EXIT
  for file in "$tmp_dir"/*; do
    [[ -f "$file" ]] || continue
    if command -v shred >/dev/null 2>&1; then
      shred -u "$file" || rm -f "$file" || status=1
    else
      rm -f "$file" || status=1
    fi
  done
  rmdir "$tmp_dir" || status=1
  exit "$status"
}
trap cleanup EXIT

# Keep input precedence equal to the selected deployment. Loading each mapping
# replaces a top-level variable, as include_vars(hash_behaviour=replace) does.
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
if ! python3 - "$src" "$tmp_dir" "$repo_root" <<'PYSELECT'
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import yaml

try:
    source, temporary, root = map(Path, sys.argv[1:])
    sys.path.insert(0, str(root / 'scripts'))
    from transport_semantics import managed_http_acme
    temporary = temporary.resolve()
    def load(paths):
        effective = {}
        for path in paths:
            with open(path) as stream:
                document = yaml.safe_load(stream)
            if document is None:
                document = {}
            if not isinstance(document, dict):
                raise ValueError
            effective.update(document)
        return effective
    def canonical(groups):
        if any(not re.fullmatch(r'all|vpn|vpn-[a-z0-9][a-z0-9-]*', group) for group in groups):
            raise ValueError
        return [root / 'ansible/group_vars' / (group + '.yml') for group in groups]
    extra = os.environ.get('VPN_CERT_EXTRA_VARS_FILE')
    raw = os.environ.get('VPN_CERT_VARS_FILES')
    if raw is not None:
        paths = json.loads(raw)
        if (not isinstance(paths, list) or not paths or len(paths) > 64
                or any(not isinstance(path, str) or not path for path in paths)
                or source.resolve() not in [Path(path).resolve() for path in paths]):
            raise ValueError
        contexts = [load(paths)]
    elif os.environ.get('VPN_CERT_INVENTORY'):
        sys.path.insert(0, str(root / 'scripts'))
        spec = importlib.util.spec_from_file_location('certificate_deployment', root / 'scripts/deploy-controller.py')
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        try:
            hosts, memberships, metadata, *_ = controller.inventory_selection(
                os.environ['VPN_CERT_INVENTORY'], os.environ.get('VPN_CERT_LIMIT', ''), temporary)
        except controller.DeployError:
            raise ValueError from None
        contexts = []
        for host in hosts:
            effective = load(canonical(('all', 'vpn', *memberships[host['name']])))
            effective.update(metadata[host['name']])
            effective.update(load([source]))
            if extra:
                effective.update(load([extra]))
            contexts.append(effective)
        if not contexts:
            raise ValueError
    else:
        cohorts = set(filter(None, os.environ.get('VPN_CERT_COHORTS', '').split(',')))
        if (len(cohorts) > 1 or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', name)
                                  for name in cohorts) or os.environ.get('VPN_CERT_LIMIT')):
            raise ValueError
        paths = canonical(('all', 'vpn', *('vpn-' + name for name in sorted(cohorts))))
        contexts = [load([*paths, source, *([extra] if extra else [])])]
    def select(effective):
        vpn = effective.get('vpn', {})
        if not isinstance(vpn, dict):
            raise ValueError
        def boolean(mapping, name, default=False):
            value = mapping.get(name, default)
            if type(value) is not bool:
                raise ValueError
            return value
        selected = {}
        if not boolean(effective, 'vpn_subscription_only'):
            for block, toggle, default in (
                ('nginx_xhttp', 'enable_nginx_xhttp', True),
                ('hysteria', 'enable_hysteria', True),
                ('naive_secrets', 'enable_naive', False),
                ('reality_self_steal', 'enable_reality_self_steal', False),
            ):
                if not boolean(vpn, toggle, default):
                    continue
                material = effective.get(block, {})
                if not isinstance(material, dict):
                    raise ValueError
                if 'acme' in material:
                    managed_http_acme(material['acme'], material.get('server_name'))
                    if block not in {'nginx_xhttp', 'hysteria'} or any(name in material for name in ('cert_pem', 'key_pem')):
                        raise ValueError
                    print(f'[{block}] managed HTTP-01 policy admitted; trusted certificate requires live acceptance')
                    continue
                selected[block] = dict(material)
            if 'hysteria' in selected:
                material = selected['hysteria']
                ech = material.get('ech') or {}
                frontend = effective.get('nginx_xhttp') or {}
                if not isinstance(ech, dict) or not isinstance(frontend, dict):
                    raise ValueError
                material['server_name'] = (material.get('server_name') or ech.get('inner_name')
                                           or frontend.get('server_name'))
            if 'nginx_xhttp' in selected:
                frontend = selected['nginx_xhttp']
                fallback = frontend.get('fallback_server_name', frontend.get('server_name'))
                if boolean(frontend, 'fallback_enabled') and fallback != frontend.get('server_name'):
                    selected['nginx_xhttp_fallback'] = {
                        'server_name': fallback, 'cert_pem': frontend.get('fallback_cert_pem'),
                        'key_pem': frontend.get('fallback_key_pem'),
                    }
        return selected
    selected = {}
    for index, context in enumerate(contexts):
        for name, material in select(context).items():
            selected[(f'profile_{index + 1}_' if len(contexts) > 1 else '') + name] = material
    (temporary / 'selected.yaml').write_text(yaml.safe_dump(selected))
    (temporary / 'blocks').write_text(''.join(name + '\n' for name in selected))
except (OSError, ValueError, TypeError, ImportError, yaml.YAMLError):
    print('certificate profile selection failed; provide one explicit effective profile', file=sys.stderr)
    raise SystemExit(1) from None
PYSELECT
then
  exit 1
fi
src="$tmp_dir/selected.yaml"

findings=0
report() { echo "  - $1"; findings=$((findings+1)); }

extract() {
  python3 - "$src" "$1" "$2" <<'PYEXTRACT'
import sys, yaml
with open(sys.argv[1]) as stream:
    data = yaml.safe_load(stream) or {}
value = (data.get(sys.argv[2]) or {}).get(sys.argv[3]) or ''
sys.stdout.write(value if isinstance(value, str) else '')
PYEXTRACT
}

check_block() {
  local block="$1" host_field="$2"
  local host cert key
  host="$( extract "$block" "$host_field" )"
  cert="$( extract "$block" cert_pem )"
  key="$(  extract "$block" key_pem  )"

  echo "[$block]"

  if [[ -z "$cert" || "$cert" == *REPLACE_WITH* ]]; then
    report "cert_pem is placeholder or empty"
    return
  fi
  if [[ -z "$key" || "$key" == *REPLACE_WITH* ]]; then
    report "key_pem is placeholder or empty"
    return
  fi

  local cert_file="$tmp_dir/${block}.cert.pem"
  local key_file="$tmp_dir/${block}.key.pem"
  printf '%s\n' "$cert" > "$cert_file"
  printf '%s\n' "$key" > "$key_file"

  local subj issuer
  if ! subj="$(openssl x509 -in "$cert_file" -noout -subject 2>/dev/null)"; then
    report "openssl could not parse cert_pem"
    return
  fi
  issuer="$(openssl x509 -in "$cert_file" -noout -issuer 2>/dev/null)"
  if [[ "${subj#subject=}" == "${issuer#issuer=}" ]]; then
    report "appears self-signed (subject == issuer)"
  fi

  if [[ -z "$host" ]]; then
    report "configured server name is missing"
  fi

  # Public issuance is separate from hostname matching. Certificates after the
  # leaf are untrusted intermediates; a supplied root cannot create trust.
  if ! openssl verify -purpose sslserver -untrusted "$cert_file" "$cert_file" >/dev/null 2>&1; then
    report "certificate trust, validity, or TLS server purpose verification failed"
  fi

  # Require DNS SAN authority and complete wildcard labels before the native
  # matcher. OpenSSL otherwise permits CN fallback and partial wildcards.
  if [[ -n "$host" ]]; then
    if ! python3 - "$cert_file" >/dev/null 2>&1 <<'PY'
from pathlib import Path
import sys
from cryptography import x509

try:
    cert = x509.load_pem_x509_certificate(Path(sys.argv[1]).read_bytes())
    names = cert.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.DNSName)
except (OSError, ValueError, x509.ExtensionNotFound):
    raise SystemExit(1)
if not names or any(
    "*" in name and (not name.startswith("*.") or name.count("*") != 1)
    for name in names
):
    raise SystemExit(1)
PY
    then
      report "SAN does not cover configured server name"
    # OpenSSL 3.0 x509 -checkhost can exit zero on mismatch. Trust only this
    # supplied leaf for the native identity check; issuance is checked above.
    elif ! openssl verify -no-CAfile -no-CApath -no-CAstore -trusted "$cert_file" \
      -partial_chain -verify_hostname "$host" "$cert_file" >/dev/null 2>&1; then
      report "SAN does not cover configured server name"
    fi
  fi

  # Expiry
  local end_iso days
  end_iso="$(openssl x509 -in "$cert_file" -noout -enddate 2>/dev/null | sed 's/notAfter=//')"
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
  cert_pub="$(openssl x509 -in "$cert_file" -pubkey -noout 2>/dev/null | openssl pkey -pubin -outform DER 2>/dev/null | openssl sha256 2>/dev/null || true)"
  key_pub="$(openssl pkey -in "$key_file" -passin pass: -pubout -outform DER 2>/dev/null | openssl sha256 2>/dev/null || true)"
  if [[ -z "$cert_pub" || -z "$key_pub" || "$cert_pub" != "$key_pub" ]]; then
    report "certificate public key does not match private key"
  fi
}

while IFS= read -r block; do
  check_block "$block" server_name
done < "$tmp_dir/blocks"

echo
if (( findings == 0 )); then
  if [[ -s "$tmp_dir/blocks" ]]; then
    echo "OK — supplied certs healthy; managed certificates require live acceptance"
  else
    echo "OK — no supplied certificates selected; managed certificates require live acceptance"
  fi
  exit 0
else
  echo "$findings finding(s) — fix before deploy"
  exit 1
fi
