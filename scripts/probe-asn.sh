#!/usr/bin/env bash
# Resolve an IP or hostname through Team Cymru's DNS interface over HTTPS and print
# a single tab-separated line: IP<TAB>ASN<TAB>PREFIX<TAB>COUNTRY<TAB>ORG.
# Empty fields stay empty; the row always has five columns. Exit 1 if the
# encrypted lookup did not run or returned an unexpected record.
#
# Usage:
#   scripts/probe-asn.sh mirror.example.com
#   scripts/probe-asn.sh 1.2.3.4
#
# Used by validate-reality-target.sh and scan-reality-targets.sh as their
# common ASN lookup primitive. Run standalone via `make probe-asn HOST=…`.
set -euo pipefail

target="${1:-}"
[[ -n "$target" ]] || { echo "usage: $0 <ip|hostname>" >&2; exit 2; }

# Portable first-IPv4 resolver. `getent` is Linux-only (macOS operator boxes
# lack it), so fall back through dig / host / python3 — whichever is present.
resolve_ipv4() {
  local h="$1" out=""
  if command -v getent >/dev/null 2>&1; then
    out="$(getent ahostsv4 "$h" 2>/dev/null | awk 'NR==1{print $1}')"
    [[ -z "$out" ]] && out="$(getent hosts "$h" 2>/dev/null | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/{print $1; exit}')"
  fi
  if [[ -z "$out" ]] && command -v dig >/dev/null 2>&1; then
    out="$(dig +short A "$h" 2>/dev/null | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/{print; exit}')"
  fi
  if [[ -z "$out" ]] && command -v host >/dev/null 2>&1; then
    out="$(host -t A "$h" 2>/dev/null | awk '/has address/{print $NF; exit}')"
  fi
  if [[ -z "$out" ]] && command -v python3 >/dev/null 2>&1; then
    out="$(python3 -c 'import socket,sys; print(socket.gethostbyname(sys.argv[1]))' "$h" 2>/dev/null || true)"
  fi
  printf '%s' "$out"
}

ip="$target"
if [[ "$target" == *:* ]]; then
  if ! python3 -c 'import ipaddress,sys; ipaddress.IPv6Address(sys.argv[1])' "$target" 2>/dev/null; then
    echo "invalid IPv6 address" >&2
    exit 1
  fi
elif ! [[ "$target" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  ip="$(resolve_ipv4 "$target")"
  if [[ -z "$ip" ]]; then
    echo "could not resolve: $target" >&2
    exit 1
  fi
fi

# Team Cymru's DNS interface, queried over HTTPS: the address never crosses the
# network in cleartext, and a failed lookup has no cleartext fallback.
lookup() { python3 "$(dirname "$0")/doh-lookup.py" TXT "$1"; }
field() { printf '%s' "$1" | awk -F'|' -v n="$2" '{gsub(/^ +| +$/,"",$n); print $n}'; }

origin_name="$(python3 - "$ip" <<'PY'
import ipaddress, sys

address = ipaddress.ip_address(sys.argv[1])
zone = ".origin6" if address.version == 6 else ".origin"
print(address.reverse_pointer.rsplit(".", 2)[0] + zone + ".asn.cymru.com")
PY
)"

# Origin records: "ASN | PREFIX | COUNTRY | REGISTRY | DATE", one for each
# announced prefix that covers the address, in no fixed order. Take the most
# specific prefix and the lowest origin, so that repeated runs agree. Any other
# shape (no data, truncated line, format change) is a lookup failure.
if ! origins="$(lookup "$origin_name")" || ! line="$(printf '%s\n' "$origins" | python3 -c '
import ipaddress, sys

rows = [[part.strip() for part in line.split("|")] for line in sys.stdin if line.strip()]
if not rows or any(len(row) != 5 or not all(item.isdigit() for item in row[0].split()) or not row[0] for row in rows):
    sys.exit(1)
row = max(rows, key=lambda row: (ipaddress.ip_network(row[1]).prefixlen, row[1]))
row[0] = str(min(int(item) for item in row[0].split()))
print(" | ".join(row))
')"; then
  echo "Team Cymru lookup failed for $ip" >&2
  exit 1
fi
asn="$(field "$line" 1)"
prefix="$(field "$line" 2)"
country="$(field "$line" 3)"

# AS record: "ASN | COUNTRY | REGISTRY | DATE | ORG".
if ! as_line="$(lookup "AS${asn}.asn.cymru.com" | head -1)" \
   || [[ "$(printf '%s' "$as_line" | awk -F'|' '{print NF}')" -ne 5 || "$(field "$as_line" 1)" != "$asn" ]]; then
  echo "Team Cymru lookup failed for AS${asn}" >&2
  exit 1
fi
org="$(field "$as_line" 5)"
printf '%s\t%s\t%s\t%s\t%s\n' "$ip" "$asn" "$prefix" "$country" "$org"
