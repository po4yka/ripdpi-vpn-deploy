"""The dependency policy must run with the repository's cargo-deny config."""

from pathlib import Path


def test_ci_runs_cargo_deny_with_vpnd_config():
    root = Path(__file__).resolve().parents[2]
    config = (root / "vpnd/deny.toml").read_text()
    ci = (root / ".github/workflows/ci.yml").read_text()

    assert 'unmaintained = "workspace"' in config
    assert "vulnerability =" not in config
    assert "copyleft =" not in config
    assert "EmbarkStudios/cargo-deny-action@" in ci
    assert "manifest-path: vpnd/Cargo.toml" in ci
    assert 'command-arguments: "--config vpnd/deny.toml"' in ci
    assert 'rust-version: "1.88.0"' in ci


def test_lockfile_excludes_the_advisory_affected_anyhow_release():
    root = Path(__file__).resolve().parents[2]
    lockfile = (root / "vpnd/Cargo.lock").read_text()

    assert 'name = "anyhow"\nversion = "1.0.103"' in lockfile
    assert 'name = "anyhow"\nversion = "1.0.102"' not in lockfile
