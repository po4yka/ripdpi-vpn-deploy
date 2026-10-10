"""Exercise the release SBOM boundary before any external publication."""

import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "mode",
    [
        "success",
        "tool-failure",
        "lock-drift",
        "wrong-product",
        "missing-output",
        "stale-lock",
    ],
)
def test_sbom_action_stages_only_a_valid_locked_vpnd_inventory(tmp_path, mode):
    action = yaml.safe_load((ROOT / ".github/actions/vpnd-sbom/action.yml").read_text())
    generate = next(
        step
        for step in action["runs"]["steps"]
        if step.get("name") == "Generate vpnd SBOM"
    )
    package = tmp_path / "vpnd"
    package.mkdir()
    (package / "pyproject.toml").write_text(
        '[project]\nname = "vpnd"\nversion = "1.3.0"\nrequires-python = ">=3.12"\ndependencies = ["qrcode==8.2"]\n'
    )
    (package / "requirements.txt").write_text(
        "qrcode==8.2 --hash=sha256:" + "a" * 64 + "\n"
    )
    if mode == "stale-lock":
        (package / "requirements.txt").write_text(
            "qrcode==8.1 --hash=sha256:" + "a" * 64 + "\n"
        )
    (package / "sbom.json").write_text("stale output\n")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "vpnd-sbom.py").write_text((ROOT / "scripts/vpnd-sbom.py").read_text())
    binary = tmp_path / "bin"
    binary.mkdir()
    # Stub only the wheel transport. Actual production METADATA validation,
    # dependency graph construction and SBOM emission remain exercised.
    interpreter = binary / "python3"
    interpreter.write_text(
        "#!"
        + sys.executable
        + "\n"
        + """import importlib.util, os, subprocess, sys, zipfile
from pathlib import Path
if Path(sys.argv[1]).name != 'vpnd-sbom.py':
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
spec = importlib.util.spec_from_file_location('sbom_boundary', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original = subprocess.run
def transport(args, **kwargs):
    if args[1:4] == ['-m', 'pip', 'download']:
        assert '--require-hashes' in args and '--no-deps' in args
        assert '--only-binary=:all:' in args
        directory = Path(args[args.index('--dest') + 1])
        with zipfile.ZipFile(directory / 'qrcode-8.2-py3-none-any.whl', 'w') as archive:
            archive.writestr('qrcode-8.2.dist-info/METADATA', 'Name: qrcode\\nVersion: 8.2\\n')
        return subprocess.CompletedProcess(args, 0)
    return original(args, **kwargs)
module.subprocess.run = transport
module.emit(Path(sys.argv[sys.argv.index('--out') + 1]))
"""
    )
    interpreter.chmod(0o755)
    tool = binary / "cyclonedx-py"
    tool.write_text("""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
args = sys.argv[1:]
assert args[0] == "requirements"
lock = Path(args[1])
assert lock.name == "requirements.txt"
assert Path(args[args.index("--pyproject") + 1]).name == "pyproject.toml"
assert args[args.index("--spec-version") + 1] == "1.5"
assert "--output-reproducible" in args
mode = os.environ["SBOM_TEST_MODE"]
if mode == "tool-failure":
    sys.exit(17)
if mode == "missing-output":
    sys.exit(0)
if mode == "lock-drift":
    lock.write_text("changed resolution")
Path(args[args.index("--output-file") + 1]).write_text(json.dumps({
    "bomFormat": "CycloneDX", "specVersion": "1.5",
    "metadata": {"component": {"name": "vpn-deploy" if mode == "wrong-product" else "vpnd", "version": "1.3.0"}},
    "components": [{"name": "qrcode", "version": "8.2", "purl": "pkg:pypi/qrcode@8.2", "bom-ref": "qrcode"}],
    "dependencies": [{"ref": "vpnd", "dependsOn": ["qrcode"]}],
}))
""")
    tool.chmod(0o755)
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", generate["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{binary}:{os.environ['PATH']}",
            "SBOM_TEST_MODE": mode,
            "RUNNER_TEMP": str(tmp_path),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
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
    generation = next(
        i
        for i, step in enumerate(steps)
        if step.get("uses") == "./.github/actions/vpnd-sbom"
    )
    publish = next(
        i
        for i, step in enumerate(steps)
        if step.get("name") == "Publish GitHub release"
    )
    assert generation < publish
    assert "vpnd-sbom" in ci["jobs"]["required"]["needs"]
    assert any(
        step.get("uses") == "./.github/actions/vpnd-sbom"
        for step in ci["jobs"]["vpnd-sbom"]["steps"]
    )


def sbom_module():
    spec = importlib.util.spec_from_file_location(
        "sbom_graph_contract", ROOT / "scripts/vpnd-sbom.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wheel(directory, name, version, dependencies=()):
    path = directory / f"{name}-{version}-py3-none-any.whl"
    metadata = f"Name: {name}\nVersion: {version}\n"
    metadata += "".join(f"Requires-Dist: {dependency}\n" for dependency in dependencies)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}-{version}.dist-info/METADATA", metadata)
    return path


def test_runtime_graph_retains_jinja2_transitive_dependency_and_extra_markers(tmp_path):
    module = sbom_module()
    wheel(
        tmp_path, "Jinja2", "3.1.6", ["MarkupSafe>=2.0", 'Babel>=2.7; extra == "i18n"']
    )
    wheel(tmp_path, "MarkupSafe", "3.0.4")
    assert module.runtime_dependency_graph(
        tmp_path, {"jinja2": "3.1.6", "markupsafe": "3.0.4"}
    ) == {
        "jinja2": ["markupsafe"],
        "markupsafe": [],
    }


@pytest.mark.parametrize(
    "case",
    [
        "missing-dependency",
        "invalid-version",
        "direct-url",
        "incomplete-inventory",
        "ambiguous-metadata",
    ],
)
def test_runtime_graph_refuses_invalid_wheel_closure(tmp_path, case):
    module = sbom_module()
    expected = {"jinja2": "3.1.6", "markupsafe": "3.0.4"}
    dependency = "MarkupSafe>=2.0"
    if case == "missing-dependency":
        expected.pop("markupsafe")
    if case == "invalid-version":
        expected["markupsafe"] = "1.0"
    if case == "direct-url":
        dependency = "MarkupSafe @ https://example.invalid/unbound.whl"
    path = wheel(tmp_path, "Jinja2", "3.1.6", [dependency])
    if case == "ambiguous-metadata":
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("other.dist-info/METADATA", "Name: other\nVersion: 1.0\n")
    if case not in {"missing-dependency", "incomplete-inventory"}:
        wheel(tmp_path, "MarkupSafe", expected["markupsafe"])
    with pytest.raises(ValueError):
        module.runtime_dependency_graph(tmp_path, expected)
