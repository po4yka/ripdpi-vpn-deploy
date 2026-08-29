#!/usr/bin/env python3
"""Run cloud-init schema in the pinned container without host mounts."""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tarfile

MAX_CONFIG_BYTES = 4 * 1024 * 1024
MAX_CA_BYTES = 2 * 1024 * 1024
MAX_TIMEOUT = 600
PINNED_IMAGE = re.compile(r"^[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}$")

CONTAINER_SCRIPT = r"""
umask 077
work=/run/cloud-init-schema
tar -xf - -C "$work"
test -s "$work/ca.pem"
test -s "$work/cloud-config.yaml"
ca_dir=/run/cloud-init-schema-public
ca="$ca_dir/ca.pem"
install -d -m 0755 "$ca_dir"
install -m 0644 "$work/ca.pem" "$ca"

set --
for source in /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
  test -f "$source" || continue
  set -- "$@" "$source"
  sed -i \
    -e 's#http://ports.ubuntu.com/ubuntu-ports/#https://ports.ubuntu.com/ubuntu-ports/#g' \
    -e 's#http://archive.ubuntu.com/ubuntu/#https://archive.ubuntu.com/ubuntu/#g' \
    -e 's#http://security.ubuntu.com/ubuntu/#https://security.ubuntu.com/ubuntu/#g' \
    "$source"
done
test "$#" -gt 0

if grep -qE '(^|[[:space:]])(URIs:[[:space:]]*|deb(-src)?[[:space:]]+[^#]*)(http://)' "$@"; then
  echo 'cloud-init schema fallback refuses a remaining plaintext APT source' >&2
  exit 65
else
  status=$?
  if test "$status" -ne 1; then
    echo 'cloud-init schema fallback could not validate APT sources' >&2
    exit 66
  fi
fi

apt-get \
  -o Acquire::https::CAInfo=/run/cloud-init-schema-public/ca.pem \
  -o Acquire::https::Verify-Peer=true \
  -o Acquire::https::Verify-Host=true \
  -o Acquire::Retries=2 \
  -o Acquire::http::Timeout=20 \
  -o Acquire::https::Timeout=20 \
  -o APT::Update::Error-Mode=any \
  update -qq
DEBIAN_FRONTEND=noninteractive apt-get \
  -o Acquire::https::CAInfo=/run/cloud-init-schema-public/ca.pem \
  -o Acquire::https::Verify-Peer=true \
  -o Acquire::https::Verify-Host=true \
  -o Acquire::Retries=2 \
  -o Acquire::http::Timeout=20 \
  -o Acquire::https::Timeout=20 \
  -o APT::Update::Error-Mode=any \
  install -y -qq --no-install-recommends cloud-init >/dev/null
cloud-init schema --config-file "$work/cloud-config.yaml"
""".strip()


def _read_regular(path: Path, *, limit: int, require_owner: bool) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("required input is not a readable regular file") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("required input is not a regular file")
        if require_owner and before.st_uid != os.geteuid():
            raise ValueError("rendered cloud-init input has the wrong owner")
        if before.st_size <= 0 or before.st_size > limit:
            raise ValueError("required input has an invalid size")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(fd)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if len(data) != before.st_size or identity_before != identity_after:
            raise ValueError("required input changed while it was read")
        return data
    finally:
        os.close(fd)


def _archive(config: bytes, ca_bundle: bytes) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, content in (("ca.pem", ca_bundle), ("cloud-config.yaml", config)):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mode = 0o600
            member.uid = 0
            member.gid = 0
            member.mtime = 0
            archive.addfile(member, io.BytesIO(content))
    return output.getvalue()


def _stop_container(name: str, process: subprocess.Popen[bytes]) -> bool:
    """Stop the named container and its client within fixed cleanup bounds."""
    removed = False
    try:
        removed = subprocess.run(
            ["docker", "rm", "--force", "--volumes", name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        removed = False  # The bounded inspect below must confirm uncertain cleanup.
    process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return False
    if removed:
        return True
    try:
        inspected = subprocess.run(
            ["docker", "container", "inspect", name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return inspected.returncode != 0 and b"No such" in inspected.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args(argv)

    if not PINNED_IMAGE.fullmatch(args.image):
        print("cloud-init schema fallback requires a digest-pinned image", file=sys.stderr)
        return 2
    if not 1 <= args.timeout <= MAX_TIMEOUT:
        print("cloud-init schema fallback has an invalid timeout", file=sys.stderr)
        return 2

    try:
        config = _read_regular(args.config, limit=MAX_CONFIG_BYTES, require_owner=True)
        try:
            import certifi
        except ModuleNotFoundError:
            print(
                "cloud-init schema fallback requires pinned certifi from requirements.txt",
                file=sys.stderr,
            )
            return 2
        ca_bundle = _read_regular(Path(certifi.where()), limit=MAX_CA_BYTES, require_owner=False)
    except ValueError as exc:
        print(f"cloud-init schema fallback refused its input: {exc}", file=sys.stderr)
        return 2

    name = f"vpn-cloud-init-schema-{os.getpid()}-{secrets.token_hex(8)}"
    try:
        process = subprocess.Popen(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "--name",
                name,
                "--network=bridge",
                "--tmpfs=/run/cloud-init-schema:rw,noexec,nosuid,nodev,size=8m,mode=0700",
                args.image,
                "sh",
                "-eu",
                "-c",
                CONTAINER_SCRIPT,
            ],
            stdin=subprocess.PIPE,
        )
    except OSError:
        print("cloud-init schema fallback could not start Docker", file=sys.stderr)
        return 2
    try:
        process.communicate(_archive(config, ca_bundle), timeout=args.timeout)
    except subprocess.TimeoutExpired:
        if not _stop_container(name, process):
            print(
                "cloud-init schema fallback timed out; container cleanup is uncertain",
                file=sys.stderr,
            )
            return 125
        print("cloud-init schema fallback timed out and was stopped", file=sys.stderr)
        return 124
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
