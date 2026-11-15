#!/usr/bin/env bash
# Print a curl config with the notification destination and token.
#
# Callers pipe it to `curl --config -`, so the topic and the token are never in
# a process argument list. There is no default destination: the operator sets
# NTFY_URL to a service of their choice.
#
# Usage:
#   scripts/ntfy-curl-config.sh | curl -fsS --config - -H "Title: ..." --data "$body"
# Environment: NTFY_URL, NTFY_TOPIC (both required), NTFY_TOKEN (optional).
set -euo pipefail

if [[ -z "${NTFY_URL:-}" || -z "${NTFY_TOPIC:-}" ]]; then
  echo "ntfy-curl-config: no alert was sent; set NTFY_URL to your notification service and NTFY_TOPIC to its topic" >&2
  exit 1
fi

for value in "$NTFY_URL" "$NTFY_TOPIC" "${NTFY_TOKEN:-}"; do
  if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    echo "ntfy-curl-config: a notification value contains a line break" >&2
    exit 1
  fi
done

quoted() {
  local value="$1"
  value="${value//\\/\\\\}"
  printf '%s' "${value//\"/\\\"}"
}

printf 'url = "%s"\n' "$(quoted "${NTFY_URL%/}/${NTFY_TOPIC}")"
if [[ -n "${NTFY_TOKEN:-}" ]]; then
  printf 'header = "Authorization: Bearer %s"\n' "$(quoted "$NTFY_TOKEN")"
fi
