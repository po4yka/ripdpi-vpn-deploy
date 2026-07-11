"""The declared MSRV must be exercised by CI."""

import re
import tomllib
from pathlib import Path


def test_ci_checks_msrv_and_pins_normal_rust_toolchain():
    root = Path(__file__).resolve().parents[2]
    cargo = (root / "vpnd/Cargo.toml").read_text()
    ci = (root / ".github/workflows/ci.yml").read_text()
    normal_workflows = {
        path: (root / ".github/workflows" / path).read_text()
        for path in ("_rust.yml", "mutants.yml")
    }
    mise = tomllib.loads((root / "mise.toml").read_text())
    normal_pin = mise["tools"]["rust"]

    assert 'rust-version = "1.88"' in cargo
    assert "cargo +1.88.0 check --locked" in ci
    assert isinstance(normal_pin, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+", normal_pin)

    for workflow in normal_workflows.values():
        assert f'toolchain: "{normal_pin}"' in workflow
        assert f"# {normal_pin}" in workflow
        assert "toolchain: stable" not in workflow
        assert "# stable" not in workflow

    toolchain_inputs = [
        (path.name, match.group(1))
        for path in (root / ".github/workflows").glob("*.yml")
        for match in re.finditer(r'^\s+toolchain:\s+("[^"]+"|\S+)\s*$', path.read_text(), re.MULTILINE)
    ]
    assert sum(value == f'"{normal_pin}"' for _, value in toolchain_inputs) == 2
    assert [(name, value) for name, value in toolchain_inputs if value != f'"{normal_pin}"'] == [("ci.yml", '"1.88.0"')]
