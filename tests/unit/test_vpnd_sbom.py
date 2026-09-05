"""Exercise the release SBOM boundary before any external publication."""

import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mode", ["success", "tool-failure", "lock-drift", "wrong-product", "missing-output"])
def test_sbom_action_stages_only_a_valid_locked_vpnd_inventory(tmp_path, mode):
    action = yaml.safe_load((ROOT / ".github/actions/vpnd-sbom/action.yml").read_text())
    generate = next(step for step in action["runs"]["steps"]
                    if step["name"] == "Generate vpnd SBOM")
    crate = tmp_path / "vpnd"
    crate.mkdir()
    (crate / "Cargo.toml").write_text('[package]\nname = "vpnd"\nversion = "1.3.0"\n')
    (crate / "Cargo.lock").write_text("locked input\n")
    (crate / "sbom.json").write_text("stale output\n")
    binary = tmp_path / "bin"
    binary.mkdir()
    cargo = binary / "cargo"
    cargo.write_text('''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
args = sys.argv[1:]
if args[0] == "metadata":
    assert "--locked" in args
    sys.exit(0)
assert args[0] == "cyclonedx"
assert args[args.index("--target") + 1] == "all"
assert os.environ["CARGO_NET_OFFLINE"] == "true"
mode = os.environ["SBOM_TEST_MODE"]
if mode == "tool-failure":
    sys.exit(17)
if mode == "missing-output":
    sys.exit(0)
if mode == "lock-drift":
    Path("vpnd/Cargo.lock").write_text("changed resolution")
Path("vpnd/sbom.json").write_text(json.dumps({
    "bomFormat": "CycloneDX", "specVersion": "1.5",
    "metadata": {"component": {"name": "vpn-deploy" if mode == "wrong-product" else "vpnd", "version": "1.3.0"}},
    "components": [{"name": "clap", "purl": "pkg:cargo/clap@4.5.0"}],
    "dependencies": [{"ref": "vpnd", "dependsOn": ["clap"]}],
}))
''')
    cargo.chmod(0o755)
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", generate["run"]],
        cwd=tmp_path, env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}",
                           "SBOM_TEST_MODE": mode, "RUNNER_TEMP": str(tmp_path)},
        capture_output=True, text=True, timeout=10,
    )
    output = tmp_path / "dist/sbom.json"
    if mode == "success":
        assert result.returncode == 0, result.stderr
        assert json.loads(output.read_text())["metadata"]["component"]["name"] == "vpnd"
    else:
        assert result.returncode != 0
        assert not output.exists()


def test_release_and_required_ci_share_sbom_generation():
    release = yaml.safe_load((ROOT / ".github/workflows/release-vpnd.yml").read_text())
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = release["jobs"]["release"]["steps"]
    generation = next(i for i, step in enumerate(steps)
                      if step.get("uses") == "./.github/actions/vpnd-sbom")
    publish = next(i for i, step in enumerate(steps) if step["name"] == "Publish GitHub release")
    assert generation < publish
    assert "vpnd-sbom" in ci["jobs"]["required"]["needs"]
    assert any(step.get("uses") == "./.github/actions/vpnd-sbom"
               for step in ci["jobs"]["vpnd-sbom"]["steps"])
