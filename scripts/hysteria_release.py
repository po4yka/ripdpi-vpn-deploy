#!/usr/bin/env python3
"""Refresh exact release metadata; publication eligibility never proves a soak."""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

PINS = json.loads(
    (
        Path(__file__).resolve().parent.parent / "contract/hysteria-runtimes.json"
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
        if any(
            not isinstance(a, dict) or a.get("severity") not in {"low", "medium"}
            for a in advisories
        ):
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
    try:
        now = datetime.now(timezone.utc)
        for name, repo, prefix in [
            ("hysteria", "HyNetworks/hysteria", "app/"),
            ("sing_box", "SagerNet/sing-box", "v"),
        ]:
            pin = PINS[name]
            tag = prefix + pin["version"]
            release = fetch(
                "https://api.github.com/repos/" + repo + "/releases/tags/" + tag
            )
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
            if not publication_eligible(release, tag, digests, advisories, now):
                raise ValueError("release-publication-ineligible")
            print(
                name
                + ": exact stable assets and 48-hour publication eligibility verified; staging soak remains separate"
            )
    except Exception:
        print(
            "Release/advisory metadata unavailable or ineligible; promotion remains blocked",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
