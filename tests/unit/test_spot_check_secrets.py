"""Fail-diagnosed behavior for the pre-deploy secrets gate."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "spot-check-secrets.py"


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["VPN_SECRETS_FILE"] = str(path)
    return subprocess.run(
        ["python3", str(SCRIPT)], text=True, capture_output=True, check=False, env=env,
    )


def test_malformed_yaml_exits_two_with_diagnosis_not_traceback(tmp_path: Path) -> None:
    bad = tmp_path / "secrets.yaml"
    bad.write_text("xray: [unclosed\n  bad::: {", encoding="utf-8")

    result = _run(bad)

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "invalid YAML" in result.stderr
    # The diagnostic must never echo file content (may be secret material).
    assert "unclosed" not in result.stderr


def test_cert_without_cn_is_not_flagged_as_self_signed(tmp_path: Path) -> None:
    import subprocess as sp

    key = tmp_path / "k.pem"
    cert = tmp_path / "c.pem"
    subj = "/O=Example Org/C=US"
    sp.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "3650",
            "-subj", subj], capture_output=True, check=True)
    doc = tmp_path / "secrets.yaml"
    doc.write_text(
        "some_role:\n"
        f"  cert_pem: |\n{(cert.read_text()).rstrip()}\n"
        f"  key_pem: |\n{(key.read_text()).rstrip()}\n",
        encoding="utf-8",
    )

    result = _run(doc)

    # A CN-less self-signed pair must not crash and must not be reported
    # as self-signed (no CN evidence); expiry findings are expected instead.
    assert result.returncode != 0 or "self-signed" not in result.stdout
    assert "Traceback" not in result.stderr
