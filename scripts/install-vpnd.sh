#!/usr/bin/env bash
# Download, verify and atomically install the Python vpnd release.
# PREFIX defaults to /usr/local; ALLOW_ROOT=1 explicitly permits root.
# Provenance follows the existing policy: gh verifies when available;
# VPND_SKIP_ATTESTATION explicitly opts out. Python 3.12 is required.
set -euo pipefail

if [[ "$(id -u)" -eq 0 && "${ALLOW_ROOT:-0}" != 1 ]]; then
  echo "error: refusing to run as root. Set ALLOW_ROOT=1 to override." >&2
  exit 1
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' || {
  echo "error: vpnd requires Python 3.12" >&2
  exit 1
}
case "$(uname -s):$(uname -m)" in
  Linux:x86_64) target=x86_64-unknown-linux-gnu ;;
  Linux:aarch64|Linux:arm64) target=aarch64-unknown-linux-gnu ;;
  Darwin:x86_64) target=x86_64-apple-darwin ;;
  Darwin:arm64) target=aarch64-apple-darwin ;;
  *) echo "error: unsupported OS or architecture" >&2; exit 1 ;;
esac
asset="vpnd-${target}.tar.gz"
base="https://github.com/po4yka/ripdpi-vpn-deploy/releases/latest/download"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/vpnd-install.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
curl -fsSL --connect-timeout 5 --max-time 60 -o "$scratch/$asset" "$base/$asset"
curl -fsSL --connect-timeout 5 --max-time 30 -o "$scratch/SHA256SUMS" "$base/SHA256SUMS"
python3 - "$scratch/$asset" "$scratch/SHA256SUMS" "$asset" <<'PY'
import hashlib, pathlib, re, sys
artifact, sums, name = sys.argv[1:]
rows = [line.split() for line in pathlib.Path(sums).read_text().splitlines()]
found = [row[0] for row in rows if len(row) == 2 and row[1] == name]
if len(found) != 1 or re.fullmatch(r'[0-9a-f]{64}', found[0]) is None:
    raise SystemExit('missing, duplicate or invalid checksum')
if hashlib.sha256(pathlib.Path(artifact).read_bytes()).hexdigest() != found[0]:
    raise SystemExit('artifact checksum mismatch')
PY
if [[ -z "${VPND_SKIP_ATTESTATION:-}" ]] && command -v gh >/dev/null 2>&1; then
  gh attestation verify "$scratch/$asset" --owner po4yka \
    --signer-workflow .github/workflows/release-vpnd.yml
elif [[ -z "${VPND_SKIP_ATTESTATION:-}" ]]; then
  echo "warning: gh unavailable; build provenance was not verified" >&2
fi
# Extract only the verified installer file, never arbitrary archive paths.
python3 - "$scratch/$asset" "$scratch/install.py" <<'PY'
import pathlib, sys, tarfile
with tarfile.open(sys.argv[1], 'r:gz') as archive:
    members = [m for m in archive if m.name == 'install.py']
    if len(members) != 1 or not members[0].isfile() or members[0].size > 100000:
        raise SystemExit('invalid installer member')
    stream = archive.extractfile(members[0])
    if stream is None:
        raise SystemExit('missing installer member')
    pathlib.Path(sys.argv[2]).write_bytes(stream.read())
PY
python3 "$scratch/install.py" "$scratch/$asset" "${PREFIX:-/usr/local}"
