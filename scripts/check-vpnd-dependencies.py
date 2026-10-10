#!/usr/bin/env python3
"""Verify immutable runtime wheels, approved licenses and non-yanked PyPI sources."""

import email
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalize(name):
    return re.sub(r"[-_.]+", "-", name.lower())


def fetch(name, version):
    url = (
        "https://pypi.org/pypi/"
        + urllib.parse.quote(name, safe="")
        + "/"
        + urllib.parse.quote(version, safe="")
        + "/json"
    )
    with urllib.request.urlopen(url, timeout=15) as response:
        data = response.read(8_000_001)
    if len(data) > 8_000_000:
        raise ValueError("registry metadata exceeds its bound")
    return json.loads(data)


def validate_wheel(wheel, expected, policy, metadata):
    with zipfile.ZipFile(wheel) as archive:
        files = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(files) != 1:
            raise ValueError("invalid runtime wheel metadata inventory")
        package = email.message_from_bytes(archive.read(files[0]))
        name = normalize(package["Name"])
        version = package["Version"]
        rule = policy["packages"].get(name)
        if name not in expected or expected[name] != version or rule is None:
            raise ValueError("unapproved runtime dependency/version")
        if (
            rule["license"] not in policy["allowed_licenses"]
            or not rule["license_files"]
        ):
            raise ValueError("missing approved SPDX license")
        base = files[0].split(".dist-info/", 1)[0] + ".dist-info/"
        for relative, digest in rule["license_files"].items():
            if hashlib.sha256(archive.read(base + relative)).hexdigest() != digest:
                raise ValueError(
                    "dependency license differs from the reviewed SPDX license"
                )
        matches = [
            entry for entry in metadata["urls"] if entry["filename"] == wheel.name
        ]
        if (
            len(matches) != 1
            or matches[0]["yanked"]
            or urllib.parse.urlsplit(matches[0]["url"]).hostname
            != "files.pythonhosted.org"
            or matches[0]["digests"]["sha256"]
            != hashlib.sha256(wheel.read_bytes()).hexdigest()
        ):
            raise ValueError(
                "dependency is yanked or lacks the verified official registry digest"
            )
        return name


def check():
    policy = json.loads((ROOT / "vpnd/dependency-policy.json").read_text())
    if policy["schema"] != 1 or policy["registry"] != "https://pypi.org":
        raise ValueError("unknown runtime registry policy")
    lock = ROOT / "vpnd/requirements.txt"
    text = lock.read_text()
    if any(
        line.strip().startswith(
            ("--index", "--extra", "--trusted", "-e", "git+", "http")
        )
        for line in text.splitlines()
    ):
        raise ValueError("runtime lock contains an unapproved dependency source")
    expected = {
        normalize(name): version
        for name, version in re.findall(
            r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", text, re.MULTILINE
        )
    }
    if not expected or set(expected) != set(policy["packages"]):
        raise ValueError("runtime lock and approved dependency inventory differ")
    before = hashlib.sha256(lock.read_bytes()).digest()
    with tempfile.TemporaryDirectory(prefix="vpnd-dependency-check-") as directory:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--require-hashes",
                "--only-binary=:all:",
                "--no-deps",
                "-r",
                str(lock),
                "-d",
                directory,
            ],
            check=True,
        )
        actual = set()
        for wheel in sorted(Path(directory).glob("*.whl")):
            name = normalize(wheel.name.split("-")[0])
            actual.add(
                validate_wheel(wheel, expected, policy, fetch(name, expected[name]))
            )
        if (
            actual != set(expected)
            or before != hashlib.sha256(lock.read_bytes()).digest()
        ):
            raise ValueError("runtime wheel closure or lock changed")
    print(
        f"Approved licenses, hashes and non-yanked registry sources: {len(expected)} packages"
    )


if __name__ == "__main__":
    check()
