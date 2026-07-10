"""SOPS+age round-trip test.

Verifies:
  1. Decrypting secrets-sample.sops.yaml with the test age key yields content
     identical to secrets-sample.yml.
  2. Editing one field, re-encrypting, then decrypting again preserves the
     change and only that change (verified via difflib).

Requires real `sops` (>= 3.x) and `age` binaries.  Skips with a clear reason
if either is absent.
"""
from __future__ import annotations

import difflib
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
SOPS_FIXTURE = FIXTURES / "secrets-sample.sops.yaml"
PLAIN_FIXTURE = FIXTURES / "secrets-sample.yml"
AGE_KEY = FIXTURES / "age-test.key"


# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------

def _require_binaries() -> None:
    missing = [b for b in ("sops", "age") if not shutil.which(b)]
    if missing:
        pytest.fail(f"missing required SOPS round-trip binary: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sops_decrypt(src: Path, age_key: Path) -> dict:
    """Decrypt *src* with *age_key* and return parsed YAML dict."""
    env = {**os.environ, "SOPS_AGE_KEY_FILE": str(age_key)}
    result = subprocess.run(
        ["sops", "--decrypt", str(src)],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"sops --decrypt failed (rc={result.returncode}):\n{result.stderr}"
        )
    return yaml.safe_load(result.stdout)


def _sops_encrypt(src: Path, dst: Path, age_key: Path, age_recipient: str) -> None:
    """Encrypt plain-YAML *src* to SOPS file *dst* using the test age key."""
    env = {**os.environ, "SOPS_AGE_KEY_FILE": str(age_key)}
    result = subprocess.run(
        [
            "sops",
            "--encrypt",
            "--age", age_recipient,
            "--output", str(dst),
            str(src),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"sops --encrypt failed (rc={result.returncode}):\n{result.stderr}"
        )


def _age_recipient(age_key_file: Path) -> str:
    """Extract the public key (recipient) from an age key file."""
    for line in age_key_file.read_text().splitlines():
        if line.startswith("# public key:"):
            return line.split(":", 1)[1].strip()
    raise ValueError(f"could not parse public key from {age_key_file}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sops_decrypt_matches_plaintext_fixture(tmp_path):
    """Decrypting the fixture sops file yields the same content as the plain fixture."""
    _require_binaries()

    decrypted = _sops_decrypt(SOPS_FIXTURE, AGE_KEY)
    expected = yaml.safe_load(PLAIN_FIXTURE.read_text())

    assert decrypted == expected, (
        "Decrypted content differs from plain fixture.\n"
        f"decrypted keys: {sorted(decrypted)}\n"
        f"expected keys:  {sorted(expected)}"
    )


def test_sops_roundtrip_field_edit(tmp_path):
    """Edit one field, re-encrypt, decrypt again — only that field differs."""
    _require_binaries()

    # Step 1: Decrypt to a plain dict.
    original = _sops_decrypt(SOPS_FIXTURE, AGE_KEY)

    # Step 2: Mutate one well-known scalar field.
    EDITED_FIELD = ("watchdog_secrets", "ntfy_topic")
    EDITED_VALUE = "roundtrip-test-edited-topic-xyz"

    modified = yaml.safe_load(yaml.safe_dump(original))  # deep-copy via yaml round-trip
    modified[EDITED_FIELD[0]][EDITED_FIELD[1]] = EDITED_VALUE

    # Step 3: Write modified plain YAML to a temp file.
    plain_modified = tmp_path / "modified.yaml"
    plain_modified.write_text(yaml.safe_dump(modified))

    # Step 4: Re-encrypt.
    recipient = _age_recipient(AGE_KEY)
    encrypted_modified = tmp_path / "modified.sops.yaml"
    _sops_encrypt(plain_modified, encrypted_modified, AGE_KEY, recipient)

    # Step 5: Decrypt the re-encrypted file.
    roundtripped = _sops_decrypt(encrypted_modified, AGE_KEY)

    # Step 6: Assert the edited field is preserved.
    assert roundtripped[EDITED_FIELD[0]][EDITED_FIELD[1]] == EDITED_VALUE, (
        f"Re-encrypted+decrypted value for {'.'.join(EDITED_FIELD)} "
        f"is {roundtripped[EDITED_FIELD[0]][EDITED_FIELD[1]]!r}, "
        f"expected {EDITED_VALUE!r}"
    )

    # Step 7: Assert no other fields changed (difflib verification).
    original_lines = yaml.safe_dump(original, default_flow_style=False).splitlines()
    roundtrip_lines = yaml.safe_dump(roundtripped, default_flow_style=False).splitlines()

    diff = list(
        difflib.unified_diff(
            original_lines, roundtrip_lines,
            fromfile="original", tofile="roundtripped",
            lineterm="",
        )
    )

    # Only lines touching the edited field should appear in the diff.
    changed_lines = [
        ln for ln in diff
        if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))
    ]
    for ln in changed_lines:
        assert EDITED_FIELD[1] in ln or EDITED_VALUE in ln or original[EDITED_FIELD[0]][EDITED_FIELD[1]] in ln, (
            f"Unexpected diff line (unrelated field changed?):\n  {ln}\n\n"
            f"Full diff:\n" + "\n".join(diff)
        )
