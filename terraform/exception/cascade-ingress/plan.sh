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

# A fresh clone has no .terraform directory; validate/plan would fail with
# "no package for ... cached". Initialize once instead of failing opaquely.
# This stays AFTER the attestation gate: no terraform invocation may happen
# before the check passes.
if [[ ! -d "${ROOT}/.terraform" ]]; then
  echo "cascade exception root not initialized; running terraform init" >&2
  terraform "-chdir=${ROOT}" init -input=false
fi

exec terraform "-chdir=${ROOT}" plan \
  -var="exception_confirmation=${CONFIRMATION}" \
  -var="activation_mode=INERT_UNATTESTED" \
  -var="attestation_file=${ATTESTATION}" \
  "$@"
