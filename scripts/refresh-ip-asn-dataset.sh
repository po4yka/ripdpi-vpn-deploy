#!/usr/bin/env bash
# Download a new copy of the offline IP-to-ASN dataset for the subscription-host
# network hint, check that the ingest can load it, and print the pin to commit.
#
# The dataset is iptoasn.com ip2asn-combined.tsv.gz under the Public Domain
# Dedication and License 1.0 (ansible/roles/subscription-host/THIRD_PARTY_NOTICES.md).
# The URL always serves the latest build, so the version is its Last-Modified
# instant and the file is kept as .cache/ip-asn/ip2asn-combined-<version>.tsv.gz.
# Deploy copies only that pinned file; no host fetches the dataset.
#
# Usage: scripts/refresh-ip-asn-dataset.sh
# Env:   IP_ASN_DATASET_URL  (default https://iptoasn.com/data/ip2asn-combined.tsv.gz)
#        IP_ASN_CACHE_DIR    (default <repo>/.cache/ip-asn)
# Output: the dataset_version and dataset_sha256 lines for
#         subscription_field_report.network_hint in the role defaults or group_vars.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${IP_ASN_DATASET_URL:-https://iptoasn.com/data/ip2asn-combined.tsv.gz}"
CACHE_DIR="${IP_ASN_CACHE_DIR:-$REPO_ROOT/.cache/ip-asn}"
SERVICE="$REPO_ROOT/ansible/roles/subscription-host/files/vpn-field-report.py"

case "$URL" in
  https://*) ;;
  *) echo "refresh-ip-asn-dataset: IP_ASN_DATASET_URL must be https" >&2; exit 1 ;;
esac

WORK="$(mktemp -d "${TMPDIR:-/tmp}/ip-asn-refresh.XXXXXX")"
STAGE=""
trap 'rm -rf "$WORK"; [ -z "$STAGE" ] || rm -f "$STAGE"' EXIT

curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --max-time 300 \
  --max-filesize 104857600 --user-agent refresh-ip-asn-dataset \
  --dump-header "$WORK/headers" --output "$WORK/dataset.tsv.gz" "$URL"

if command -v sha256sum >/dev/null 2>&1; then
  SHA256="$(sha256sum "$WORK/dataset.tsv.gz" | cut -d' ' -f1)"
else
  SHA256="$(shasum -a 256 "$WORK/dataset.tsv.gz" | cut -d' ' -f1)"
fi

# The ingest's own loader must accept the file, so a damaged download never gets a pin.
python3 -I - "$SERVICE" "$WORK/dataset.tsv.gz" "$SHA256" "$WORK/headers" > "$WORK/version" <<'PY'
import importlib.util
import sys
from email.utils import parsedate_to_datetime

service, dataset, sha256, headers = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("vpn_field_report", service)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.AsnTable(dataset, sha256)
modified = [line.split(":", 1)[1].strip() for line in open(headers, encoding="latin-1")
            if line.lower().startswith("last-modified:")]
if not modified:
    sys.exit("refresh-ip-asn-dataset: the response has no Last-Modified header to version the dataset")
print(parsedate_to_datetime(modified[-1]).strftime("%Y%m%dT%H%M%SZ"))
PY
VERSION="$(cat "$WORK/version")"

TARGET="$CACHE_DIR/ip2asn-combined-$VERSION.tsv.gz"
mkdir -p "$CACHE_DIR"
# A committed pin names this file, so an existing copy is never replaced. ln refuses an existing
# name atomically; the stage sits in the cache directory so the link stays on one filesystem.
STAGE="$(mktemp "$CACHE_DIR/.ip2asn-combined.XXXXXX")"
cp "$WORK/dataset.tsv.gz" "$STAGE"
if ! ln "$STAGE" "$TARGET" 2>/dev/null; then
  echo "refresh-ip-asn-dataset: $TARGET already exists; it is never replaced" >&2
  exit 1
fi
echo "Stored $TARGET"
echo "Pin it in subscription_field_report.network_hint:"
printf '    dataset_version: "%s"\n    dataset_sha256: "%s"\n' "$VERSION" "$SHA256"
