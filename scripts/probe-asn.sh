#!/usr/bin/env bash
# Resolve an IP or hostname through Team Cymru's whois interface and print
# a single tab-separated line: IP<TAB>ASN<TAB>ORG<TAB>COUNTRY.
# Empty fields stay empty; the row always has four columns. Exit 1 if
# Cymru is unreachable or returns an error envelope.
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
if ! [[ "$target" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  ip="$(resolve_ipv4 "$target")"
  if [[ -z "$ip" ]]; then
    echo "could not resolve: $target" >&2
    exit 1
  fi
fi

line="$(whois -h whois.cymru.com " -v $ip" 2>/dev/null | tail -1 || true)"
if [[ -z "$line" ]] || echo "$line" | grep -qiE '^bulk|^error|<html'; then
  echo "Team Cymru lookup failed for $ip" >&2
  exit 1
fi

# Guard: the result line must have exactly 7 pipe-delimited fields and the
# first field (ASN) must be numeric. Any other shape (NO_DATA, truncated
# line, format change) is treated as a lookup failure rather than silently
# returning a wrong value.
_nf="$(echo "$line" | awk -F'|' '{print NF}')"
_asn_raw="$(echo "$line" | awk -F'|' '{gsub(/^ +| +$/,"",$1); print $1}')"
if [[ "$_nf" -ne 7 ]] || ! [[ "$_asn_raw" =~ ^[0-9]+$ ]]; then
  echo "Team Cymru lookup failed for $ip (unexpected response format)" >&2
  exit 1
fi

asn="$(   echo "$line" | awk -F'|' '{gsub(/^ +| +$/,"",$1); print $1}')"
prefix="$(echo "$line" | awk -F'|' '{gsub(/^ +| +$/,"",$3); print $3}')"
country="$(echo "$line" | awk -F'|' '{gsub(/^ +| +$/,"",$4); print $4}')"
org="$(   echo "$line" | awk -F'|' '{gsub(/^ +| +$/,"",$7); print $7}')"
printf '%s\t%s\t%s\t%s\t%s\n' "$ip" "$asn" "$prefix" "$country" "$org"
