"""The dependency policy must run with the repository's cargo-deny config."""

from pathlib import Path


def test_ci_runs_cargo_deny_with_vpnd_config():
    root = Path(__file__).resolve().parents[2]
    config = (root / "vpnd/deny.toml").read_text()
    ci = (root / ".github/workflows/ci.yml").read_text()
    reusable = (root / ".github/workflows/_rust.yml").read_text()
    release = (root / ".github/workflows/release-vpnd.yml").read_text()
    makefile = (root / "Makefile").read_text()

    assert 'unmaintained = "workspace"' in config
    assert "vulnerability =" not in config
    assert "copyleft =" not in config
    assert "EmbarkStudios/cargo-deny-action@" in ci
    assert "manifest-path: vpnd/Cargo.toml" in ci
    assert 'arguments: "--all-features --config vpnd/deny.toml"' in ci
    assert 'rust-version: "1.88.0"' in ci
    assert "cargo-command: test --release --locked" in ci
    assert "cargo-command: clippy --release --all-targets --locked -- -D warnings" in ci
    assert 'default: "test --release --locked"' in reusable
    assert "CARGO_COMMAND: ${{ inputs.cargo-command }}" in reusable
    assert "RUST_TARGET: ${{ inputs.target }}" in reusable
    assert 'case " $CARGO_COMMAND " in' in reusable
    assert '[[ ! "$RUST_TARGET" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*$ ]]' in reusable
    assert 'read -r -a cargo_args <<< "$CARGO_COMMAND"' in reusable
    assert 'cargo "${cargo_args[@]}" --target "$RUST_TARGET"' in reusable
    assert 'cross "${cargo_args[@]}" --target "$RUST_TARGET"' in reusable
    assert "run: cargo ${{ inputs.cargo-command }}" not in reusable
    assert release.count("cargo-command: build --release --locked") == 4
    assert makefile.count("cargo test --release --locked") == 3
    assert makefile.count("cargo clippy --release --all-targets --locked -- -D warnings") == 2


def test_lockfile_excludes_the_advisory_affected_anyhow_release():
    root = Path(__file__).resolve().parents[2]
    lockfile = (root / "vpnd/Cargo.lock").read_text()

    assert 'name = "anyhow"\nversion = "1.0.103"' in lockfile
    assert 'name = "anyhow"\nversion = "1.0.102"' not in lockfile
