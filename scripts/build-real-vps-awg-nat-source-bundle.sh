#!/usr/bin/env bash
# Materialize a portable exact-HEAD git bundle for offline sentinel provisioning.
set -euo pipefail

usage() {
  echo "usage: $0 --repo /path/to/ripdpi-vpn-deploy --output /secure/path/source.bundle" >&2
  exit 2
}

repo=""
output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) repo="$2"; shift 2 ;;
    --output) output="$2"; shift 2 ;;
    *) usage ;;
  esac
done
[[ -n "$repo" && -n "$output" ]] || usage
[[ ! -L "$output" ]] || { echo "bundle output must not be a symlink" >&2; exit 1; }
output="$(python3 - "$output" <<'PY'
import os
import pathlib
import stat
import sys

output = pathlib.Path(sys.argv[1])
parent = output.parent.resolve(strict=True)
info = parent.stat()
if info.st_uid not in {0, os.geteuid()} or stat.S_IMODE(info.st_mode) & 0o022:
    raise SystemExit("bundle output parent must be owner-controlled and non-writable by group/other")
if output.exists():
    target = output.stat()
    if not stat.S_ISREG(target.st_mode) or target.st_nlink != 1:
        raise SystemExit("existing bundle output must be a singly-linked regular file")
print(parent / output.name)
PY
)"
repo="$(cd "$repo" && pwd -P)"
[[ -z "$(git -C "$repo" status --porcelain --untracked-files=all)" ]] || {
  echo "source changes, including untracked files, must be committed before bundling" >&2
  exit 1
}
sha="$(git -C "$repo" rev-parse --verify 'HEAD^{commit}')"
create_temp() {
  python3 - "$output" "$1" <<'PY'
import os
import pathlib
import sys
import tempfile

output = pathlib.Path(sys.argv[1])
parent = output.parent.resolve(strict=True)
fd, path = tempfile.mkstemp(
    prefix=f".{output.name}.{sys.argv[2]}.",
    dir=parent,
)
try:
    os.fchmod(fd, 0o600)
finally:
    os.close(fd)
print(path)
PY
}

tmp=""
archive_tmp=""
cleanup() {
  [[ -z "$tmp" ]] || rm -f -- "$tmp"
  [[ -z "$archive_tmp" ]] || rm -f -- "$archive_tmp"
}
trap cleanup EXIT
tmp="$(create_temp bundle)"
archive_tmp="$(create_temp archive)"
git -C "$repo" bundle create "$tmp" HEAD
git bundle verify "$tmp" >/dev/null
bundle_head="$(git bundle list-heads "$tmp" HEAD | awk '$2 == "HEAD" { print $1 }')"
[[ "$bundle_head" == "$sha" ]] || {
  echo "source HEAD changed while creating the bundle" >&2
  exit 1
}
git -C "$repo" archive --format=tar --output="$archive_tmp" "$sha"
chmod 0600 "$tmp"
python3 - "$tmp" "$output" <<'PY'
import os
import sys

# Both paths have the validated output parent, so os.replace is an atomic
# same-filesystem publication of the already-verified owner-only bundle.
os.replace(sys.argv[1], sys.argv[2])
PY
bundle_sha="$(shasum -a 256 "$output" | awk '{print $1}')"
archive_sha="$(shasum -a 256 "$archive_tmp" | awk '{print $1}')"
python3 - "$sha" "$bundle_sha" "$archive_sha" <<'PY'
import json
import sys

print(json.dumps({
    "sourceArchiveSha256": sys.argv[3],
    "sourceBundleSha256": sys.argv[2],
    "sourceSha": sys.argv[1],
}, sort_keys=True, separators=(",", ":")))
PY
