"""The declared MSRV must be exercised by CI."""

from pathlib import Path


def test_ci_checks_declared_vpnd_msrv():
    root = Path(__file__).resolve().parents[2]
    cargo = (root / "vpnd/Cargo.toml").read_text()
    ci = (root / ".github/workflows/ci.yml").read_text()
    assert 'rust-version = "1.88"' in cargo
    assert "cargo +1.88.0 check --locked" in ci
