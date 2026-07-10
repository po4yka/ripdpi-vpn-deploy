#!/usr/bin/env bash
# External post-deploy probes. Runs from the operator's machine, not the VPS.
#
# Checks:
#   1. TCP/443 handshake to the server
#   2. UDP/443 reachability (best-effort) when Hysteria is enabled
#   3. Optional HTTPS GET /health if nginx-xhttp is enabled
set -euo pipefail

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

IP="$(PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh" output -raw server_ipv4)"

echo "== TCP/443 handshake to ${IP} =="
if openssl s_client -connect "${IP}:443" -servername "${SNI_TARGET:-www.cloudflare.com}" -tls1_3 < /dev/null 2>/dev/null \
   | grep -E "Verify return code|Cipher" ; then
  echo "OK"
else
  echo "FAIL: TLS handshake to ${IP}:443"
  exit 1
fi

if [[ "${ENABLE_HYSTERIA:-1}" == "1" ]]; then
  echo "== UDP/443 best-effort probe to ${IP} =="
  # nc -u with 1s timeout: if the kernel routes the packet at all the script
  # treats this as "host reachable on UDP/443"; semantic UDP probing requires
  # a real Hysteria client.
  if echo | nc -u -w 1 -z "${IP}" 443 2>&1 | grep -q "succeeded"; then
    echo "OK"
  else
    echo "(unverified — nc -u is best-effort; test with the real client.)"
  fi
fi

if [[ -n "${HTTP_HOST:-}" ]]; then
  echo "== HTTPS GET https://${HTTP_HOST}/health =="
  if curl -fsS --connect-timeout 5 --resolve "${HTTP_HOST}:443:${IP}" "https://${HTTP_HOST}/health" >/dev/null; then
    echo "OK"
  else
    echo "FAIL: /health did not return 200"
    exit 1
  fi
fi

echo "all probes passed"
