"""Keep sensitive operator identifiers and forbidden labels out of git."""

import ipaddress
import re
import subprocess
from pathlib import Path


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


def _should_scan(relative: str) -> bool:
    """Exclude this policy corpus and random encrypted data from content checks."""
    return bool(relative) and relative != SELF and relative not in ENCRYPTED_FIXTURES


def _read_tracked_content(path: Path) -> str:
    """Read the tracked blob shape without following repository symlinks."""
    if path.is_symlink():
        return path.readlink().as_posix().lower()
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
