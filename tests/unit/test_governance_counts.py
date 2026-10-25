"""Molecule images stay digest-pinned and scanned; testing docs match the hosted Molecule matrix."""

import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _is_digest_pinned_image(image: str) -> bool:
    name, separator, digest = image.partition("@sha256:")
    return separator == "@sha256:" and "/" in name and ":" not in name and "@" not in name and len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


def _testing_role_rows(testing: str) -> dict[str, str]:
    rows = {}
    for line in testing.splitlines():
        match = re.match(r"\| \*\*Ansible role: ([^*]+)\*\* \|", line)
        if match:
            rows[match.group(1)] = line
    return rows


def _molecule_sequence(path: Path) -> list[str]:
    molecule = yaml.safe_load(path.read_text())
    return molecule["scenario"]["test_sequence"]


def _documented_sequence(row: str, scenario: str) -> list[str]:
    match = re.search(rf"{re.escape(scenario)} sequence: ([a-z_, ]+?)(?=;|\)| \|)", row)
    assert match, f"missing {scenario} sequence in documentation: {row}"
    return [phase.strip() for phase in match.group(1).split(",")]


def test_molecule_images_are_digest_pinned():
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


def test_testing_documentation_matches_molecule_sequences_and_hosted_matrix():
    testing = (ROOT / "docs/reference/testing.md").read_text()
    role_rows = _testing_role_rows(testing)
    role_directories = {path.name for path in (ROOT / "ansible/roles").iterdir() if path.is_dir()}
    assert set(role_rows) == role_directories

    expected_sequences = {
        ("naive", "default"): "ansible/roles/naive/molecule/default/molecule.yml",
        ("geodata", "default"): "ansible/roles/geodata/molecule/default/molecule.yml",
        ("warp-outbound", "default"): "ansible/roles/warp-outbound/molecule/default/molecule.yml",
        ("amneziawg", "default"): "ansible/roles/amneziawg/molecule/default/molecule.yml",
        ("reality-self-steal", "default"): "ansible/roles/reality-self-steal/molecule/default/molecule.yml",
        ("reality-self-steal", "disabled"): "ansible/roles/reality-self-steal/molecule/disabled/molecule.yml",
        ("full-stack", "full-stack"): "ansible/molecule/full-stack/molecule.yml",
        ("full-stack", "full-stack-published"): "ansible/molecule/full-stack-published/molecule.yml",
    }
    for (subject, scenario), relative_path in expected_sequences.items():
        row = (
            next(line for line in testing.splitlines() if line.startswith("| **Full stack** |"))
            if subject == "full-stack"
            else role_rows[subject]
        )
        assert _documented_sequence(row, scenario) == _molecule_sequence(ROOT / relative_path)

    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    push_row = next(line for line in testing.splitlines() if line.startswith("| `git push` (PR) |"))
    default_segment, full_stack_segment, non_default_segment = re.split(
        r"; required hosted full-stack scenarios |; non-default scenarios ", push_row, maxsplit=2
    )
    documented_defaults = set(re.findall(r"`([^`]+)`", default_segment.split("default Molecule scenarios for ", 1)[1]))
    documented_full_stack_scenarios = set(re.findall(r"`([^`]+)`", full_stack_segment))
    documented_non_defaults = set(re.findall(r"`([^`]+)`", non_default_segment.split("; shellcheck", 1)[0]))
    expected_defaults = {role for group in ci["jobs"]["molecule"]["strategy"]["matrix"]["roles"] for role in group.split()}
    expected_non_defaults = {
        f"{scenario['role']}/{scenario['scenario']}"
        for scenario in ci["jobs"]["molecule-failure-scenarios"]["strategy"]["matrix"]["include"]
    }
    assert documented_defaults == expected_defaults
    assert documented_non_defaults == expected_non_defaults

    expected_full_stack_scenarios = set(
        ci["jobs"]["molecule-full-stack"]["strategy"]["matrix"]["scenario"]
    )
    assert expected_full_stack_scenarios == {"full-stack", "full-stack-published"}
    assert documented_full_stack_scenarios == expected_full_stack_scenarios
