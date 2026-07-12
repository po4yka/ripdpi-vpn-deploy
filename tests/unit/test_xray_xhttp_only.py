"""XHTTP-only profile must still run a valid localhost Xray backend."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "xray" / "templates" / "config.json.j2"
SITE_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "site.yml"

spec = importlib.util.spec_from_file_location("xhttp_only_renderer", RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def test_p1_web_renders_only_the_local_xhttp_inbound() -> None:
    variables = renderer.merge_render_vars()
    profile = yaml.safe_load((REPO_ROOT / "ansible" / "group_vars" / "vpn-p1-web.yml").read_text())
    variables.update(profile)
    config = json.loads(renderer.render_template(TEMPLATE, variables))

    assert [inbound["tag"] for inbound in config["inbounds"]] == ["vless-xhttp-localhost"]
    assert config["inbounds"][0]["listen"] == "127.0.0.1"
    assert config["inbounds"][0]["streamSettings"]["network"] == "xhttp"


def test_site_playbook_runs_xray_for_reality_or_xhttp() -> None:
    playbook = SITE_PLAYBOOK.read_text()
    xray_role = playbook.split("- role: xray", 1)[1].split("- role: nginx-xhttp", 1)[0]
    assert "enable_xray_reality" in xray_role
    assert "enable_nginx_xhttp" in xray_role
    assert ") or\n" in xray_role
