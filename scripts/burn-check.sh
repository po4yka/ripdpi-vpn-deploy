#!/usr/bin/env bash
# External reachability probe for the current VPN VPS IP.
#
# Uses check-host.net's public node API to test TCP/443 reachability from
# multiple geographic vantage points, including RU. Exits non-zero if N or
# more nodes fail. Intended to run from cron on the operator workstation.
#
# Also runs an external UDP/443 (Hysteria2/QUIC) edge-reachability probe. This
# closes the silent-failure gap documented in the censorship-bypass KB concept
# `cloud-firewall-udp-egress-friction`: on several cloud providers, inbound
# UDP/443 is silently dropped at the provider-edge firewall even when the
# instance's own nftables shows ACCEPT and the listener is bound. On-host
# checks (`nft list`, `ss -ulnp`) cannot see this; only an external probe can.
# The probe sends an unauthenticated QUIC Version-Negotiation trigger and
# treats any reply as proof the datagram reached the server. It is always
# NON-FATAL (WARN only) — a no-response is ambiguous (edge drop vs. Hysteria2
# silently ignoring an unauthenticated probe) and is disambiguated server-side
# with `tcpdump -i any udp port 443` per the KB verification chain.
#
# Usage:
#   scripts/burn-check.sh                      # uses defaults
#   FAIL_THRESHOLD=3 scripts/burn-check.sh
#   NODES="ru1.node.check-host.net,ru4.node.check-host.net,uk1.node.check-host.net" \
#     scripts/burn-check.sh
#
# Required env:
#   PROVIDER (default: upcloud)
#   ENV      (default: prod)
#
# Optional env (UDP/443 Hysteria2 edge probe):
#   ENABLE_HYSTERIA     (default: true)  — set false to skip the UDP probe (WARN)
#   HYSTERIA_SALAMANDER (default: false) — set true when Salamander obfs is on;
#                                          external probing is then impossible
#                                          (obfs mangles the probe) so it skips
#   HYSTERIA_PORT       (default: 443)   — UDP port Hysteria2 listens on
#   UDP_PROBE_TIMEOUT   (default: 5)     — seconds to wait for a QUIC reply
set -euo pipefail

PROVIDER="${PROVIDER:-upcloud}"
ENV="${ENV:-prod}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform/providers/${PROVIDER}"
FAIL_THRESHOLD="${FAIL_THRESHOLD:-2}"
DEFAULT_NODES="ru1.node.check-host.net,ru2.node.check-host.net,ru4.node.check-host.net,de1.node.check-host.net"
NODES="${NODES:-$DEFAULT_NODES}"

# UDP/443 (Hysteria2) external edge probe — see header. Always non-fatal.
ENABLE_HYSTERIA="${ENABLE_HYSTERIA:-true}"
HYSTERIA_SALAMANDER="${HYSTERIA_SALAMANDER:-false}"
HYSTERIA_PORT="${HYSTERIA_PORT:-443}"
UDP_PROBE_TIMEOUT="${UDP_PROBE_TIMEOUT:-5}"

for tool in curl jq terraform; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing: $tool" >&2; exit 1; }
done

IP="$(terraform -chdir="$TF_DIR" output -raw server_ipv4)"

# check-host.net rest API: GET /check-tcp?host=<ip>:<port>&node=<n1>&node=<n2>…
# returns a request_id; results are polled at /check-result/<request_id>.
NODE_PARAMS="$(echo "$NODES" | tr ',' '\n' | sed 's/^/\&node=/' | tr -d '\n')"
REQ="$(curl -fsS -H 'Accept: application/json' \
  "https://check-host.net/check-tcp?host=${IP}:443${NODE_PARAMS}")"
REQUEST_ID="$(echo "$REQ" | jq -r .request_id)"

if [[ -z "$REQUEST_ID" || "$REQUEST_ID" == "null" ]]; then
  echo "check-host.net rejected the request:" >&2
  echo "$REQ" >&2
  exit 2
fi

# Poll up to 30s for results
for _ in $(seq 1 15); do
  sleep 2
  RESULT="$(curl -fsS -H 'Accept: application/json' \
    "https://check-host.net/check-result/${REQUEST_ID}")"
  # Result is a map of node→[[result_object]] or null while pending. If every
  # node has a non-null array we're done.
  PENDING="$(echo "$RESULT" | jq '[to_entries[] | select(.value == null)] | length')"
  [[ "$PENDING" == "0" ]] && break
done

# Count nodes whose first result didn't include an "address" field success.
# A successful check-tcp result looks like: {"address":"…","time":0.123}.
# Failures look like {"error":"Connection refused"} or {"error":"Connection timed out"}.
TOTAL="$(echo "$RESULT" | jq 'length')"
FAILS="$(echo "$RESULT" | jq '[to_entries[]
  | .key as $node
  | (.value // [[]])[0] // []
  | (.[0] // {})
  | select(.error != null or (.address // null) == null)
  ] | length')"

echo "burn-check: ${PROVIDER}/${ENV} ${IP}:443  →  ${TOTAL} nodes probed, ${FAILS} failed"
echo "$RESULT" | jq -r 'to_entries[] | "  \(.key): \(.value // "pending")"'

# ---------------------------------------------------------------------------
# External UDP/443 (Hysteria2/QUIC) edge-reachability probe. Always non-fatal:
# UDP_OK is "" (not measured / skipped), 0 (no response), or 1 (reachable).
# ---------------------------------------------------------------------------
UDP_OK=""
if [[ "$ENABLE_HYSTERIA" != "true" ]]; then
  echo "WARN: hysteria disabled (ENABLE_HYSTERIA=${ENABLE_HYSTERIA}) — skipping UDP/443 edge probe" >&2
elif [[ "$HYSTERIA_SALAMANDER" == "true" ]]; then
  echo "WARN: Salamander obfs enabled — an external UDP/443 probe cannot work (obfs mangles the unauthenticated QUIC probe). Verify server-side: tcpdump -i any udp port 443" >&2
elif ! command -v python3 >/dev/null 2>&1; then
  echo "WARN: python3 not found — skipping UDP/443 edge probe" >&2
else
  # Send an unauthenticated QUIC Version-Negotiation trigger (long header, a
  # 0x?a?a?a?a 'force VN' version, padded to QUIC's 1200-byte minimum). A
  # compliant QUIC server (quic-go, which Hysteria2 uses) replies with a
  # Version-Negotiation packet — no TLS, auth, or obfs key required — so any
  # datagram back proves UDP/443 was delivered end-to-end to the listener.
  set +e
  UDP_MARK="$(UDP_IP="$IP" UDP_PORT="$HYSTERIA_PORT" UDP_TIMEOUT="$UDP_PROBE_TIMEOUT" python3 - <<'PY'
import os, socket, sys

ip = os.environ["UDP_IP"]
port = int(os.environ["UDP_PORT"])
budget = float(os.environ["UDP_TIMEOUT"])

first = 0xC0                       # long header (0x80) | fixed bit (0x40)
version = b"\x1a\x2a\x3a\x4a"      # 0x1a2a3a4a — matches 0x?a?a?a?a, unknown
dcid = os.urandom(8)
pkt = bytes([first]) + version + bytes([len(dcid)]) + dcid + b"\x00"
pkt = pkt + b"\x00" * (1200 - len(pkt))   # QUIC min datagram size for VN reply

fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
attempts = 3
per = max(budget / attempts, 1.0)
s = socket.socket(fam, socket.SOCK_DGRAM)
s.settimeout(per)
try:
    for _ in range(attempts):
        try:
            s.sendto(pkt, (ip, port))
            data, _ = s.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError as e:
            sys.stderr.write("udp probe error: %s\n" % e)
            sys.exit(2)
        is_vn = len(data) >= 5 and (data[0] & 0x80) and data[1:5] == b"\x00\x00\x00\x00"
        sys.stdout.write("version-negotiation" if is_vn else "response")
        sys.exit(0)
    sys.exit(3)   # no reply within budget — ambiguous, see WARN below
finally:
    s.close()
PY
)"
  UDP_RC=$?
  set -e
  case "$UDP_RC" in
    0)
      UDP_OK=1
      echo "burn-check UDP: ${IP}:${HYSTERIA_PORT}/udp  →  reachable (QUIC ${UDP_MARK} from server)"
      ;;
    3)
      UDP_OK=0
      echo "WARN: ${IP}:${HYSTERIA_PORT}/udp  →  no QUIC reply. Per cloud-firewall-udp-egress-friction this is AMBIGUOUS: provider-edge UDP drop OR Hysteria2 silently ignoring an unauthenticated probe. Disambiguate on the server — run 'tcpdump -i any udp port 443' while re-running this probe: zero inbound packets means the provider edge is dropping UDP (open UDP/443 in the provider UI / security group); packets present means the gap is server-side, not the edge." >&2
      ;;
    *)
      echo "WARN: UDP/443 probe error (rc=${UDP_RC}) — not measured" >&2
      ;;
  esac
fi

# Optional Prometheus textfile export. When NODE_EXPORTER_TEXTFILE_DIR is
# set, write {dir}/vpn_burn.prom with one gauge per node and a summary.
# Atomic write: tmp + mv per the textfile-collector contract.
if [[ -n "${NODE_EXPORTER_TEXTFILE_DIR:-}" ]]; then
  out="${NODE_EXPORTER_TEXTFILE_DIR%/}/vpn_burn.prom"
  tmp="${out}.tmp.$$"
  {
    echo "# HELP vpn_burn_total_nodes Number of vantage points probed"
    echo "# TYPE vpn_burn_total_nodes gauge"
    echo "vpn_burn_total_nodes{provider=\"${PROVIDER}\",env=\"${ENV}\"} ${TOTAL}"
    echo "# HELP vpn_burn_failed_nodes Number of probes that did not connect"
    echo "# TYPE vpn_burn_failed_nodes gauge"
    echo "vpn_burn_failed_nodes{provider=\"${PROVIDER}\",env=\"${ENV}\"} ${FAILS}"
    echo "# HELP vpn_burn_reachable Whether the VPS public port appears reachable per node (1 OK / 0 failed)"
    echo "# TYPE vpn_burn_reachable gauge"
    echo "$RESULT" | jq -r --arg p "$PROVIDER" --arg e "$ENV" '
      to_entries[]
      | .key as $node
      | (.value // [[]])[0] // []
      | (.[0] // {})
      | (if (.address // null) != null and (.error // null) == null then 1 else 0 end) as $ok
      | "vpn_burn_reachable{provider=\"\($p)\",env=\"\($e)\",node=\"\($node)\"} \($ok)"
    '
    if [[ -n "$UDP_OK" ]]; then
      echo "# HELP vpn_burn_udp_reachable UDP/443 (Hysteria2/QUIC) reachable from the operator vantage (1 reachable / 0 no-reply). Absent when the probe was skipped."
      echo "# TYPE vpn_burn_udp_reachable gauge"
      echo "vpn_burn_udp_reachable{provider=\"${PROVIDER}\",env=\"${ENV}\"} ${UDP_OK}"
    fi
    echo "# HELP vpn_burn_last_run_unixtime Last time burn-check ran"
    echo "# TYPE vpn_burn_last_run_unixtime gauge"
    echo "vpn_burn_last_run_unixtime{provider=\"${PROVIDER}\",env=\"${ENV}\"} $(date +%s)"
  } > "$tmp"
  mv "$tmp" "$out"
  chmod 0644 "$out"
fi

if (( FAILS >= FAIL_THRESHOLD )); then
  echo "FAIL: ${FAILS} of ${TOTAL} nodes could not reach ${IP}:443 — IP may be burned" >&2
  exit 1
fi

echo "OK"
