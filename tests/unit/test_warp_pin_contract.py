"""WARP repository signing key pin must be mandatory, never TOFU.

The role ships a real default sha256 for Cloudflare's WARP apt key and
fails closed when the pin is unset or malformed; the checksum verify +
assert pair runs unconditionally under the install toggle.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS = REPO_ROOT / "ansible" / "roles" / "warp-outbound" / "tasks" / "main.yml"
DEFAULTS = REPO_ROOT / "ansible" / "roles" / "warp-outbound" / "defaults" / "main.yml"


def _tasks() -> list[dict]:
    return yaml.safe_load(TASKS.read_text())


def _task_by_name(name: str) -> dict | None:
    for task in _tasks():
        if isinstance(task, dict) and task.get("name") == name:
            return task
    return None


def test_defaults_ship_a_real_sha256_pin() -> None:
    defaults = yaml.safe_load(DEFAULTS.read_text())
    pin = defaults["warp_outbound"]["pubkey_sha256"]
    assert isinstance(pin, str)
    assert re.fullmatch(r"[0-9a-f]{64}", pin), (
        "warp_outbound.pubkey_sha256 must carry a pinned sha256 digest"
    )


def test_pin_presence_assert_fails_closed_when_unset() -> None:
    task = _task_by_name("Assert the repository signing key pin is present")
    assert task is not None, "fail-closed pin assert missing from warp-outbound tasks"
    assert any(
        "^[0-9a-f]{64}$" in clause for clause in task["ansible.builtin.assert"]["that"]
    )


def test_checksum_tasks_are_not_gated_on_the_pin_being_set() -> None:
    content = TASKS.read_text()
    # The old TOFU escape hatch skipped verification when the pin was
    # empty; it must not exist anywhere in the role tasks.
    assert "length > 0" not in content.replace("install_warp_cli", "")
    verify = _task_by_name("Verify Cloudflare WARP GPG key checksum against the pin")
    assert verify is not None
    assert verify["when"] == "warp_outbound.install_warp_cli | default(true)"
    enforce = _task_by_name("Assert GPG key matches pinned sha256")
    assert enforce is not None
    assert enforce["when"] == "warp_outbound.install_warp_cli | default(true)"


def test_health_gate_runs_before_xray_can_activate_warp_routes() -> None:
    plays = yaml.safe_load((REPO_ROOT / "ansible/playbooks/site.yml").read_text())
    roles = next(play["roles"] for play in plays if "roles" in play)
    names = [role["role"] for role in roles]
    assert names.index("warp-outbound") < names.index("xray")
    assert names.index("warp-outbound") < names.index("nginx-xhttp")
    warp = roles[names.index("warp-outbound")]
    assert set(roles[names.index("xray")]["tags"]) <= set(warp["tags"])


def test_health_gate_rejects_successful_http_with_inactive_tunnel() -> None:
    from jinja2 import Environment

    gate = _task_by_name("Verify WARP exit IP is reachable")["failed_when"]
    evaluate = Environment(autoescape=True).compile_expression(gate)
    assert evaluate(warp_trace={"rc": 0, "stdout": "warp=off\n"})
    assert evaluate(warp_trace={"rc": 7, "stdout": "warp=on\n"})
    assert not evaluate(warp_trace={"rc": 0, "stdout": "warp=on\n"})
