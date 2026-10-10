"""The baseline contract survives OpenSpec archival and task retirement."""

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_baseline_inventory_does_not_require_an_active_openspec_change(tmp_path):
    package = tmp_path / "vpnd"
    package.mkdir()
    (package / "test-inventory.md").write_bytes((ROOT / "vpnd/test-inventory.md").read_bytes())
    spec = importlib.util.spec_from_file_location(
        "vpnd_test_transfer", ROOT / "scripts/check-vpnd-test-transfer.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path
    assert not (tmp_path / "openspec").exists()
    expected = set(json.loads((ROOT / "vpnd/test-transfer.json").read_text())["cases"])
    assert len(expected) == 206
    assert module.source_cases() == expected
