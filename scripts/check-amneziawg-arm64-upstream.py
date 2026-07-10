#!/usr/bin/env python3
"""Watch upstream AmneziaWG issue states and release notes for fix claims."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = REPO_ROOT / "contract" / "amneziawg-arm64-version-floor.json"
API_ROOT = "https://api.github.com"
REMEDIATION_RE = re.compile(
    r"\b(fix(?:ed|es)?|resolv(?:e|ed|es)|correct(?:ed|ion)?|align(?:ed|ment)?)\b", re.I
)
S34_RE = re.compile(r"\bS3\b.*\bS4\b|\bS4\b.*\bS3\b", re.I | re.S)
H4_RE = re.compile(r"\bH4\b", re.I)


class WatchResult:
    def __init__(self) -> None:
        self.review_required = False
        self.indeterminate = False
        self.reasons: list[str] = []
        self.candidates: list[dict] = []


def _release_claims_fix(policy: dict, release: dict) -> bool:
    text = "\n".join(
        str(release.get(key) or "") for key in ("name", "tag_name", "body")
    )
    lowered = text.lower()
    direct = [
        str(value).lower() for value in policy["release_watch"]["direct_references"]
    ]
    if any(reference in lowered for reference in direct):
        return True
    mentions_bug = bool(S34_RE.search(text) or H4_RE.search(text))
    return mentions_bug and bool(REMEDIATION_RE.search(text))


def classify(policy: dict, issues: list[dict], releases: list[dict]) -> WatchResult:
    result = WatchResult()
    issue_by_key = {
        (item.get("repository"), item.get("number")): item for item in issues
    }
    for expected in policy["expected_issue_states"]:
        key = (expected["repository"], expected["number"])
        actual = issue_by_key.get(key)
        if actual is None:
            result.indeterminate = True
            result.reasons.append(
                f"Missing upstream issue payload for {key[0]}#{key[1]}"
            )
            continue
        if actual.get("state") not in {"open", "closed"}:
            result.indeterminate = True
            result.reasons.append(
                f"Malformed state for {key[0]}#{key[1]}: {actual.get('state')!r}"
            )
            continue
        if actual.get("state") != expected["state"]:
            result.review_required = True
            result.reasons.append(
                f"{key[0]}#{key[1]} changed from tracked {expected['state']} to {actual.get('state')}: "
                f"{expected['url']}"
            )

    cursor = policy["release_watch"]["last_reviewed_release"]
    if not releases:
        result.indeterminate = True
        result.reasons.append("The upstream release payload was empty")
        return result
    cursor_index = next(
        (
            index
            for index, release in enumerate(releases)
            if release.get("tag_name") == cursor
        ),
        None,
    )
    if releases and cursor_index is None:
        result.indeterminate = True
        result.reasons.append(
            f"Release cursor {cursor!r} was not present in the fetched release page"
        )
        return result

    for release in releases[: cursor_index or 0]:
        if _release_claims_fix(policy, release):
            result.review_required = True
            candidate = {
                "tag": release.get("tag_name"),
                "url": release.get("html_url"),
            }
            result.candidates.append(candidate)
            result.reasons.append(
                f"Release {candidate['tag']} contains an AmneziaWG arm64 S3/S4 fix claim"
            )
    return result


def _github_get(path: str) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ripdpi-vpn-deploy-amneziawg-floor-watch",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{API_ROOT}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _live_payloads(policy: dict) -> tuple[list[dict], list[dict]]:
    issues: list[dict] = []
    for expected in policy["expected_issue_states"]:
        payload = _github_get(
            f"/repos/{expected['repository']}/issues/{expected['number']}"
        )
        if not isinstance(payload, dict):
            raise ValueError(
                f"unexpected issue response for {expected['repository']}#{expected['number']}"
            )
        payload["repository"] = expected["repository"]
        issues.append(payload)
    release_repo = policy["release_watch"]["repository"]
    releases = _github_get(f"/repos/{release_repo}/releases?per_page=100")
    if not isinstance(releases, list):
        raise ValueError(f"unexpected releases response for {release_repo}")
    return issues, releases


def _load_fixture(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--issues-fixture", type=Path)
    parser.add_argument("--releases-fixture", type=Path)
    args = parser.parse_args(argv)
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        if bool(args.issues_fixture) != bool(args.releases_fixture):
            raise ValueError(
                "both --issues-fixture and --releases-fixture are required together"
            )
        if args.issues_fixture:
            issues = _load_fixture(args.issues_fixture)
            releases = _load_fixture(args.releases_fixture)
        else:
            issues, releases = _live_payloads(policy)
        if not isinstance(issues, list) or not isinstance(releases, list):
            raise ValueError("fixture roots must be JSON arrays")
        result = classify(policy, issues, releases)
    except (
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as error:
        print(f"INDETERMINATE: {error}")
        return 2

    status = "REVIEW_REQUIRED" if result.review_required else "NO_SIGNAL"
    if result.indeterminate:
        status = "INDETERMINATE"
    print(status)
    for reason in result.reasons:
        print(f"- {reason}")
    if result.review_required:
        if result.candidates:
            print("Candidate releases:")
            for candidate in result.candidates:
                print(f"- {candidate['tag']}: {candidate['url']}")
        print(
            "\nRevalidation remains mandatory; do not change candidate/verified floors or either guard from this signal alone."
        )
        print("Required physical checks:")
        for requirement in policy["revalidation_requirements"]:
            print(f"- {requirement}")
    if result.indeterminate:
        return 2
    return 1 if result.review_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
