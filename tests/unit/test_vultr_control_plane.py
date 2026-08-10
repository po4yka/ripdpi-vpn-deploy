"""Tests for the Vultr operator control-plane preflight."""

from __future__ import annotations

import io
import runpy
import urllib.error
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check-vultr-control-plane.py"


def _module() -> dict:
    return runpy.run_path(str(SCRIPT))


def test_allowlist_rejection_is_actionable_and_redacted(monkeypatch, capsys) -> None:
    module = _module()
    token = "secret-token-must-not-appear"

    def reject(*_args: object, **_kwargs: object) -> object:
        raise urllib.error.HTTPError(
            "https://api.vultr.com/v2/account",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":"Unauthorized IP address"}'),
        )

    monkeypatch.setattr(module["urllib"].request, "urlopen", reject)
    monkeypatch.setenv("TF_VAR_vultr_api_key", token)

    assert module["main"]() == 78
    output = capsys.readouterr()
    assert "allowlist rejected the current operator egress" in output.err
    assert "exact IP/CIDR" in output.err
    assert token not in output.out + output.err


def test_other_unauthorized_response_is_classified_as_credentials(monkeypatch, capsys) -> None:
    module = _module()

    def reject(*_args: object, **_kwargs: object) -> object:
        raise urllib.error.HTTPError(
            "https://api.vultr.com/v2/account",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":"Invalid API key"}'),
        )

    monkeypatch.setattr(module["urllib"].request, "urlopen", reject)
    monkeypatch.setenv("VULTR_API_KEY", "invalid-secret")

    assert module["main"]() == 77
    assert "credentials rejected" in capsys.readouterr().err


def test_successful_authenticated_probe_passes(monkeypatch, capsys) -> None:
    module = _module()

    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(module["urllib"].request, "urlopen", lambda *_args, **_kwargs: Response())
    monkeypatch.setenv("TF_VAR_vultr_api_key", "valid-secret")

    assert module["main"]() == 0
    assert "control plane: OK" in capsys.readouterr().err


def test_missing_key_fails_before_network(monkeypatch, capsys) -> None:
    module = _module()
    monkeypatch.delenv("TF_VAR_vultr_api_key", raising=False)
    monkeypatch.delenv("VULTR_API_KEY", raising=False)

    assert module["main"]() == 2
    assert "missing TF_VAR_vultr_api_key" in capsys.readouterr().err
