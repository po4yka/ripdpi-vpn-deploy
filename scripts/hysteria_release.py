#!/usr/bin/env python3
"""Refresh exact release metadata; publication eligibility never proves a soak."""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from packaging.specifiers import SpecifierSet
from packaging.version import Version
import sys
from urllib.request import Request, urlopen

PINS = json.loads(
    (
        Path(__file__).resolve().parent.parent / "scripts/hysteria-runtimes.json"
    ).read_text()
)


def publication_eligible(release, expected_tag, expected_digests, advisories, now):
    if (
        not isinstance(release, dict)
        or release.get("tag_name") != expected_tag
        or release.get("draft") is not False
        or release.get("prerelease") is not False
        or not isinstance(advisories, list)
    ):
        return False
    try:
        published = datetime.fromisoformat(
            release["published_at"].replace("Z", "+00:00")
        )
        assets = {a["name"]: a["digest"] for a in release["assets"]}
        if published.tzinfo is None or now - published < timedelta(hours=48):
            return False
        if any(
            assets.get(name) != "sha256:" + digest
            for name, digest in expected_digests.items()
        ):
            return False
        version = Version(expected_tag.rsplit("/", 1)[-1])
        if version.is_prerelease or version.is_devrelease:
            return False
        packages = ({"github.com/apernet/hysteria/core/v2", "github.com/apernet/hysteria/app/v2",
                     "github.com/apernet/hysteria/extras/v2"} if expected_tag.startswith("app/")
                    else {"github.com/sagernet/sing-box"})
        for advisory in advisories:
            if not isinstance(advisory, dict) or advisory.get("severity") not in {"low", "medium", "high", "critical"}:
                return False
            if advisory["severity"] in {"low", "medium"}:
                continue
            vulnerabilities = advisory.get("vulnerabilities")
            if not isinstance(vulnerabilities, list) or not 1 <= len(vulnerabilities) <= 32:
                return False
            for vulnerability in vulnerabilities:
                if not isinstance(vulnerability, dict):
                    return False
                package = vulnerability.get("package")
                if not isinstance(package, dict):
                    return False
                named_module = package.get("ecosystem") == "go" and package.get("name") in packages
                repository_scope = package.get("ecosystem") == "" and package.get("name") == ""
                if not named_module and not repository_scope:
                    return False
                expression = vulnerability.get("vulnerable_version_range")
                if not isinstance(expression, str) or not 1 <= len(expression) <= 512:
                    return False
                alternatives = expression.split("||")
                if len(alternatives) > 8 or any(not part.strip() for part in alternatives):
                    return False
                if any(version in SpecifierSet(part.strip()) for part in alternatives):
                    return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def fetch(url):
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "hysteria-release-check",
        },
    )
    with urlopen(request, timeout=20) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("release-response-too-large")
    return json.loads(raw)


def main():
    validated = []
    name, stage = "runtime pair", "metadata"
    try:
        now = datetime.now(timezone.utc)
        for name, repo, prefix in [
            ("hysteria", "HyNetworks/hysteria", "app/"),
            ("sing_box", "SagerNet/sing-box", "v"),
        ]:
            stage = "release metadata"
            pin = PINS[name]
            tag = prefix + pin["version"]
            release = fetch(
                "https://api.github.com/repos/" + repo + "/releases/tags/" + tag
            )
            stage = "advisory metadata"
            advisories = fetch(
                "https://api.github.com/repos/"
                + repo
                + "/security-advisories?per_page=100"
            )
            # Full pages cannot establish an exhaustive advisory result.
            if len(advisories) >= 100:
                raise ValueError("advisory-page-incomplete")
            digests = {
                (
                    "hysteria-" + arch
                    if name == "hysteria"
                    else "sing-box-" + pin["version"] + "-" + arch + ".tar.gz"
                ): digest
                for arch, digest in pin["sha256"].items()
            }
            stage = "publication eligibility"
            if not publication_eligible(release, tag, digests, advisories, now):
                raise ValueError("release-publication-ineligible")
            validated.append(name)
    except Exception:
        print(
            f"{name} {stage} unavailable or ineligible; promotion remains blocked",
            file=sys.stderr,
        )
        return 1
    for name in validated:
        print(name + ": exact stable assets and 48-hour publication eligibility verified; staging soak remains separate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
