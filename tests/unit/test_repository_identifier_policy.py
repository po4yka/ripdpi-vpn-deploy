"""Keep carrier/geography and external knowledge-store identifiers out of git."""

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
    "6b622d64726966742d6175646974", "627261696e2d6e6f7465",
    "63656e736f72736869702d627970617373206b62", "63656e736f72736869702d62797061737320636f6e63657074",
    "6b6220736f75726365", "6b6220636f6e63657074", "72652d636865636b207468652077696b69",
    "77696b69207265616c6974792d7461726765742d73656c656374696f6e",
    "736e692d65786163742d6d617463682d76732d7375666669782d636c617373696669636174696f6e2d32303236",
    "636c6f75642d6669726577616c6c2d7564702d6567726573732d6672696374696f6e",
    "746c732d706f6c6963696e672d686f6d652d69737073", "7265616c6974792d7461726765742d73656c656374696f6e2d32303236",
)
FORBIDDEN = tuple(bytes.fromhex(value).decode("ascii") for value in FORBIDDEN_HEX)
DATED_EXTERNAL_SLUG = re.compile(r"(?<![a-z0-9])(?:[a-z0-9]+-){3,}20\d{2}(?![a-z0-9-])")


def _should_scan(relative: str) -> bool:
    """Exclude this policy corpus and random encrypted data from content checks."""
    return bool(relative) and relative != SELF and relative not in ENCRYPTED_FIXTURES


def test_policy_excludes_its_corpus_and_encrypted_secret_fixtures():
    assert not _should_scan(SELF)
    assert not _should_scan("tests/fixtures/secrets-sample.sops.yaml")
    assert _should_scan("secrets/prod.secrets.sops.yaml")
    assert _should_scan("docs/ARCHITECTURE.md")


def test_tracked_files_do_not_contain_forbidden_identifiers():
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode().split("\0")
    offenders = []
    for relative in filter(_should_scan, tracked):
        content = (ROOT / relative).read_text(errors="ignore").lower()
        for identifier in FORBIDDEN:
            if identifier in content:
                offenders.append(f"{relative}: {identifier}")
        for match in DATED_EXTERNAL_SLUG.finditer(content):
            offenders.append(f"{relative}: {match.group(0)}")
    assert not offenders, "forbidden repository identifiers:\n" + "\n".join(offenders)
