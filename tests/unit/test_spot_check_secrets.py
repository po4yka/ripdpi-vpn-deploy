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


def test_certificates_are_left_to_the_enabled_authority_check(tmp_path: Path) -> None:
    # Regression: a self-signed placeholder for a role the node disables failed every
    # verify; check-certs.sh owns certificates and selects only enabled authorities.
    import textwrap

    key = tmp_path / "k.pem"
    cert = tmp_path / "c.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(cert), "-days", "3650",
                    "-subj", "/CN=disabled.example.test"], capture_output=True, check=True)
    doc = tmp_path / "secrets.yaml"
    doc.write_text(
        "naive_secrets:\n"
        "  cert_pem: |\n"
        f"{textwrap.indent(cert.read_text().rstrip(), '    ')}\n"
        "  key_pem: |\n"
        f"{textwrap.indent(key.read_text().rstrip(), '    ')}\n",
        encoding="utf-8",
    )

    result = _run(doc)

    assert "invalid YAML" not in result.stderr and "Traceback" not in result.stderr
    # The gate still runs its other checks on this document.
    assert "backup.restic_password" in result.stdout
    assert "cert_pem" not in result.stdout
