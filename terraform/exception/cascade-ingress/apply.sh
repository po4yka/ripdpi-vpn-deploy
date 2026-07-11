#!/usr/bin/env bash
# Preserve an explicit apply boundary while live governance and provider resources are absent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/../../.." && pwd)"
ATTESTATION="${CASCADE_ATTESTATION:-${REPO_ROOT}/attestations/cascade-asn-attestation.json}"

python3 "${REPO_ROOT}/scripts/check-cascade-attestation.py" --attestation "$ATTESTATION"
echo "cascade apply is disabled until a future governance commit adds a reviewed provider adapter" >&2
exit 1
