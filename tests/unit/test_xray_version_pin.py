"""Verify that the Xray-core version pin is consistent across the repo.

Cross-checks:
  docs/reference/xray-release-line.md  — the heading marked "(repository pin)"
  secrets/prod.secrets.example.yaml → xray.version  — the canonical pin

Both must agree. A mismatch means either the doc was updated after a release
bump without also bumping the example schema, or vice-versa.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check-xray-version-pin.py"


def test_xray_version_pin_consistent():
    """check-xray-version-pin.py exits 0 when doc and pin agree."""
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Xray-core version pin mismatch between docs/reference/xray-release-line.md "
        "and secrets/prod.secrets.example.yaml.\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


def checker():
    spec = importlib.util.spec_from_file_location("xray_pin_check", CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_latest_does_not_replace_the_reviewed_pin():
    text = "## v26.10.21 — security release (upstream Latest)\n## v26.3.27 — reviewed (repository pin)\n"
    assert checker().extract_doc_version(text) == "v26.3.27"


def test_missing_or_ambiguous_pin_refuses():
    module = checker()
    assert module.extract_doc_version("## v26.3.27 (current Latest)") is None
    assert module.extract_doc_version("## v26.3.27 (repository pin)\n## v26.10.21 (repository pin)") is None
    assert module.extract_doc_version("## v26.3.27 (repository pinning)") is None


def test_actual_cli_refuses_mismatch_and_duplicate_marker(tmp_path, monkeypatch):
    module = checker()
    document = tmp_path / "release.md"
    example = tmp_path / "example.yaml"
    example.write_text('xray: {version: "v26.3.27"}\n')
    monkeypatch.setattr(module, "RELEASE_LINE_DOC", document)
    monkeypatch.setattr(module, "EXAMPLE_PIN_FILE", example)
    document.write_text("## v26.10.21 (repository pin)\n")
    assert module.main() == 1
    document.write_text("## v26.3.27 (repository pin)\n## v26.3.27 (repository pin)\n")
    assert module.main() == 1


def test_actual_cli_refuses_repository_pin_outside_production_allowlist(tmp_path, monkeypatch):
    module = checker()
    document = tmp_path / "release.md"
    example = tmp_path / "example.yaml"
    allowlist = tmp_path / "defaults.yml"
    document.write_text("## v26.3.27 (repository pin)\n")
    example.write_text('xray: {version: "v26.3.27"}\n')
    monkeypatch.setattr(module, "RELEASE_LINE_DOC", document)
    monkeypatch.setattr(module, "EXAMPLE_PIN_FILE", example)
    monkeypatch.setattr(module, "PRODUCTION_ALLOWLIST_FILE", allowlist)
    allowlist.write_text("xray_runtime_production_versions: [v26.2.6]\n")
    assert module.main() == 1
    allowlist.write_text("xray_runtime_production_versions: [v26.2.6, v26.3.27]\n")
    assert module.main() == 0


@pytest.mark.parametrize(
    ("variables", "admitted"),
    [
        ({"env": "prod", "xray": {"version": "v26.3.27"}}, True),
        # Upstream prereleases carry plain tags, so a tag-shape check cannot refuse them.
        ({"env": "prod", "xray": {"version": "v26.10.17"}}, False),
        ({"env": "staging", "xray": {"version": "v26.10.17"}}, True),
    ],
)
def test_runtime_acquisition_admits_only_reviewed_production_pins(variables, admitted):
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    tasks = yaml.safe_load((REPO_ROOT / "ansible/roles/xray-runtime/tasks/main.yml").read_text())
    task = next(t for t in tasks if t["name"] == "Assert production Xray pin was reviewed for production")
    defaults = yaml.safe_load((REPO_ROOT / "ansible/roles/xray-runtime/defaults/main.yml").read_text())
    templar = Templar(loader=DataLoader(), variables={
        "xray_runtime_production_versions": defaults["xray_runtime_production_versions"], **variables})

    assert all(templar.template(trust_as_template("{{ " + c + " }}"))
               for c in task["ansible.builtin.assert"]["that"]) is admitted
