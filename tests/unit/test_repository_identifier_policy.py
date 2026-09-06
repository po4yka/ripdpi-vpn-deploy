"""Keep sensitive operator identifiers and forbidden labels out of git."""

import gzip
import ipaddress
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).relative_to(ROOT).as_posix()
ENCRYPTED_FIXTURES = {"tests/fixtures/secrets-sample.sops.yaml"}
FORBIDDEN_HEX = (
    "726f7374656c65636f6d", "6265656c696e65", "6d656761666f6e", "6d7473",
    "72746b", "726f73746f76", "697a686576736b", "726567696d652d6c616e6473636170652f77696b69",
    "63656e736f72736869702d627970617373207661756c74", "736f757263655f77696b695f7061676573",
    "77696b692070616765", "6f6273696469616e", "2f77696b692f636f6e63657074732f",
    "63656e736f72736869702d6279706173732f",
)
FORBIDDEN = tuple(bytes.fromhex(value).decode("ascii") for value in FORBIDDEN_HEX)
RESEARCH_DOCS = (
    "docs/ANDROID-CLIENT-RESEARCH.md",
    "docs/IOS-CLIENT-RESEARCH.md",
    "docs/IOS-SPLIT-ROUTING-RESEARCH.md",
)


def _should_scan(relative: str) -> bool:
    """Exclude this policy corpus and random encrypted data from content checks."""
    return bool(relative) and relative != SELF and relative not in ENCRYPTED_FIXTURES


def _read_tracked_content(path: Path) -> str:
    """Read the tracked blob shape without following repository symlinks."""
    if path.is_symlink():
        return path.readlink().as_posix().lower()
    if path.suffix == ".gz":
        return gzip.decompress(path.read_bytes()).decode("utf-8").lower()
    return path.read_text(errors="ignore").lower()


def test_policy_excludes_its_corpus_and_encrypted_secret_fixtures():
    assert not _should_scan(SELF)
    assert not _should_scan("tests/fixtures/secrets-sample.sops.yaml")
    assert _should_scan("secrets/prod.secrets.sops.yaml")
    assert _should_scan("docs/ARCHITECTURE.md")


def test_policy_reads_a_tracked_directory_symlink_without_following_it():
    group_vars_link = ROOT / "ansible" / "playbooks" / "group_vars"

    assert group_vars_link.is_symlink()
    assert _read_tracked_content(group_vars_link) == "../group_vars"



def test_policy_scans_decompressed_gzip_content(tmp_path):
    path = tmp_path / "durations.json.gz"
    content = '{"tests/test_' + FORBIDDEN[0].upper() + '.py::test_case": 0.25}'
    path.write_bytes(gzip.compress(content.encode(), mtime=0))
    assert _should_scan(path.name)
    assert _read_tracked_content(path) == content.lower()
    assert FORBIDDEN[0] in _read_tracked_content(path)


def test_policy_rejects_corrupt_gzip_content(tmp_path):
    path = tmp_path / "durations.json.gz"
    path.write_bytes(b"invalid gzip")
    with pytest.raises(gzip.BadGzipFile):
        _read_tracked_content(path)


def test_tracked_files_do_not_contain_forbidden_identifiers():
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode().split("\0")
    offenders = []
    for relative in filter(_should_scan, tracked):
        content = _read_tracked_content(ROOT / relative)
        for identifier in FORBIDDEN:
            if identifier in content:
                offenders.append(f"{relative}: {identifier}")
    assert not offenders, "forbidden repository identifiers:\n" + "\n".join(offenders)


def test_physical_acceptance_evidence_contains_no_public_ip_literals():
    research = (ROOT / "docs" / "IOS-SPLIT-ROUTING-RESEARCH.md").read_text()
    evidence = research.split("## Physical acceptance matrix", 1)[1].split(
        "## Recommended repository work", 1
    )[0]
    public_addresses = []
    for candidate in re.findall(r"`([^`]+)`", evidence):
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.is_global:
            public_addresses.append(candidate)

    assert "<redacted-address>" in evidence
    assert not public_addresses, "public addresses in tracked evidence"


def test_client_research_is_repository_owned_and_technically_named():
    for relative in RESEARCH_DOCS:
        content = (ROOT / relative).read_text()
        assert "http://" not in content and "https://" not in content, relative

    split_routing = (ROOT / RESEARCH_DOCS[-1]).read_text()
    forbidden_labels = (
        "RU-direct",
        "category-ru",
        "geoip:ru",
        "GEOIP,RU",
        "Russian",
    )
    assert not any(label in split_routing for label in forbidden_labels)


def test_android_research_tracks_physical_awg_acceptance_and_open_gaps():
    content = (ROOT / "docs" / "ANDROID-CLIENT-RESEARCH.md").read_text()

    assert "Pixel 7 live-client matrix" in content
    assert "physical AWG acceptance remains required" not in content
    for remaining_gate in (
        "cellular handover",
        "long-duration soak",
        "IPv6 differential",
    ):
        assert remaining_gate in content
