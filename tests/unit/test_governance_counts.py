"""Documentation claims about repository coverage must match the live tree."""

import re
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _is_digest_pinned_image(image: str) -> bool:
    name, separator, digest = image.partition("@sha256:")
    return separator == "@sha256:" and "/" in name and ":" not in name and "@" not in name and len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


def test_governance_counts_match_live_repository():
    roles = len([path for path in (ROOT / "ansible/roles").iterdir() if path.is_dir()])
    templates = len(list((ROOT / "ansible/roles").rglob("*.j2")))
    collected = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    test_count = int(re.search(r"(\d+) tests collected", collected).group(1))
    testing = (ROOT / "docs/TESTING.md").read_text()
    assert f"{roles} roles" in (ROOT / "AGENTS.md").read_text()
    assert f"{roles} roles" in (ROOT / "CLAUDE.md").read_text()
    assert f"({templates} templates)" in testing
    assert f"({test_count} collected)" in testing
    assert "molecule / per-role tests. v2." not in (ROOT / "docs/ARCHITECTURE.md").read_text()

    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    push_row = next(line for line in testing.splitlines() if line.startswith("| `git push` (PR) |"))
    default_roles = ci["jobs"]["molecule"]["strategy"]["matrix"]["role"]
    failure_scenarios = ci["jobs"]["molecule-failure-scenarios"]["strategy"]["matrix"]["include"]
    for role in default_roles:
        assert f"`{role}`" in push_row
    for scenario in failure_scenarios:
        assert f"`{scenario['role']}/{scenario['scenario']}`" in push_row
    assert "`pytest tests/unit/`" in push_row

    audit = (ROOT / "docs/AUDIT-SILENT-FAILURE.md").read_text()
    current = audit.split("## Current disposition", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in current.splitlines() if re.match(r"\| [1-8] \|", line)]
    statuses = [
        next(status for status in ("RESOLVED", "PARTIAL", "OPEN") if f"**{status}**" in row)
        for row in rows
    ]
    assert [int(row.split("|")[1].strip()) for row in rows] == list(range(1, 9))
    assert statuses.count("RESOLVED") == 7
    assert statuses.count("PARTIAL") == 1
    assert statuses.count("OPEN") == 0

    role_tiering = (ROOT / "docs/ROLE-TIERING.md").read_text()
    for stale_claim in (
        "8 silently-broken controls",
        "all four alert-chain links broken",
        "Integrity check is missing",
        "alert pipeline is broken",
        "must have their AUDIT-SILENT-FAILURE remediations landed",
    ):
        assert stale_claim not in role_tiering

    contributing = (ROOT / "CONTRIBUTING.md").read_text()
    contributor_guidance = contributing.split("## Local pre-flight", 1)[1].split(
        "## Adding a new role / template / script", 1
    )[0]
    for pointer in ("make check", ".github/workflows/ci.yml", "docs/TESTING.md", "required checks"):
        assert pointer in contributor_guidance
    assert "check: validate ci-fast" in (ROOT / "Makefile").read_text()
    assert not re.search(r"\b\d+\+? jobs\b|matrix:\s*\d+\s+roles", contributor_guidance, re.IGNORECASE)
    assert "Renovate PRs" in contributing
    assert "Ansible plus systemd own runtime state" in contributing

    molecule_files = subprocess.run(
        ["git", "ls-files", "ansible/**/molecule.yml"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    images = [
        platform["image"]
        for molecule_file in molecule_files
        for platform in yaml.safe_load((ROOT / molecule_file).read_text())["platforms"]
    ]
    assert images
    assert all(_is_digest_pinned_image(image) for image in images)
    digest = "a" * 64
    assert _is_digest_pinned_image(f"registry.example/project/image@sha256:{digest}")
    assert not _is_digest_pinned_image(f"image@sha256:{digest}")
    assert not _is_digest_pinned_image(f"registry.example/project/image:latest@sha256:{digest}")
    assert not _is_digest_pinned_image("registry.example/project/image@sha256:not-a-digest")

    image_scan = (ROOT / ".github/workflows/image-scan.yml").read_text()
    assert "git diff --name-only" not in image_scan
    assert "BASE_SHA" not in image_scan
    assert "find ansible/roles ansible/molecule -path '*/molecule.yml' -type f" in image_scan
