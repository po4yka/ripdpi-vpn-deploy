"""Snapshot updates must report failed renders while retaining valid updates."""

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("snapshot_renderer", ROOT / "scripts/render-snapshots.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


@pytest.fixture
def snapshot_tree(tmp_path, monkeypatch):
    roles = tmp_path / "roles"
    goldens = tmp_path / "goldens"
    roles.mkdir()
    goldens.mkdir()
    (roles / "good.j2").write_text("valid output\n")
    (goldens / "good.j2").write_text("old output\n")
    monkeypatch.setattr(renderer, "ROLES_DIR", roles)
    monkeypatch.setattr(renderer, "GOLDEN_DIR", goldens)
    return roles, goldens


def test_update_reports_errors_and_keeps_successful_updates(snapshot_tree, monkeypatch, capsys):
    roles, goldens = snapshot_tree
    (roles / "bad.j2").write_text("{{ missing_snapshot_variable }}")
    monkeypatch.setattr(sys, "argv", ["render-snapshots", "--update"])
    assert renderer.main() == 1
    assert "bad.j2" in capsys.readouterr().err
    assert (goldens / "good.j2").read_text() == "valid output\n"
    assert not (goldens / "bad.j2").exists()


def test_clean_update_succeeds_and_check_detects_drift(snapshot_tree, monkeypatch, capsys):
    _, goldens = snapshot_tree
    monkeypatch.setattr(sys, "argv", ["render-snapshots"])
    assert renderer.main() == 1
    assert "drift" in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", ["render-snapshots", "--update"])
    assert renderer.main() == 0
    assert (goldens / "good.j2").read_text() == "valid output\n"
    monkeypatch.setattr(sys, "argv", ["render-snapshots"])
    assert renderer.main() == 0
