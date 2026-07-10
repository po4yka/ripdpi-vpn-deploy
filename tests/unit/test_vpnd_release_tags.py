"""Keep release-please and binary release tags on one contract."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_please_emits_vpnd_component_tags():
    config = json.loads((ROOT / ".github/release-please-config.json").read_text())
    assert config["include-component-in-tag"] is True
    assert config["packages"]["."]["component"] == "vpnd"


def test_binary_workflow_validates_vpnd_tag_contract():
    workflow = (ROOT / ".github/workflows/release-vpnd.yml").read_text()
    assert "vpnd-v*" in workflow
    assert "^vpnd-v[0-9]+" in workflow
