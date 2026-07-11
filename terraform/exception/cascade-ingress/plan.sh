#!/usr/bin/env bash
# Plan the isolated inert root only after both wrapper and root verify attestation freshness.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/../../.." && pwd)"
ATTESTATION="${CASCADE_ATTESTATION:-${REPO_ROOT}/attestations/cascade-asn-attestation.json}"
CONFIRMATION="${CASCADE_EXCEPTION_CONFIRMATION:-}"
EXPECTED_CONFIRMATION="I_ACKNOWLEDGE_RU_CASCADE_JURISDICTION_EXCEPTION"

if [[ "$CONFIRMATION" != "$EXPECTED_CONFIRMATION" ]]; then
  echo "cascade exception confirmation literal missing or incorrect" >&2
  exit 1
fi

python3 "${REPO_ROOT}/scripts/check-cascade-attestation.py" --attestation "$ATTESTATION"
exec terraform "-chdir=${ROOT}" plan \
  -var="exception_confirmation=${CONFIRMATION}" \
  -var="activation_mode=INERT_UNATTESTED" \
  -var="attestation_file=${ATTESTATION}" \
  "$@"
