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
