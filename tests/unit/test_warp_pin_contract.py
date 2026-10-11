"""WARP pins and actual namespace readiness gate recipient activation.

The role ships a real default sha256 for Cloudflare's WARP apt key and
fails closed when the pin is unset or malformed; the checksum verify +
assert pair runs unconditionally under the install toggle.
"""

from __future__ import annotations

import copy
import importlib.util
import re
from pathlib import Path

import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = REPO_ROOT / "ansible" / "roles" / "warp-outbound"
TASKS = ROLE / "tasks" / "prepare.yml"
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
    assert re.fullmatch(
        r"[0-9a-f]{64}", pin
    ), "warp_outbound.pubkey_sha256 must carry a pinned sha256 digest"


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
    protected = roles[names.index("transport-egress")]
    assert protected["tasks_from"] == "prepare-site"
    assert names.index("transport-egress") < names.index("xray")
    assert names.index("transport-egress") < names.index("nginx-xhttp")
    assert set(roles[names.index("xray")]["tags"]) <= set(protected["tags"])
    prepare = yaml.safe_load((REPO_ROOT / "ansible/playbooks/tasks/transport-egress-prepare.yml").read_text())
    adapter = next(task for task in prepare if task.get("ansible.builtin.include_role", {}).get("name") == "warp-outbound")
    stage = next(task for task in prepare if task.get("ansible.builtin.include_role", {}).get("tasks_from") == "stage")
    assert adapter["ansible.builtin.include_role"]["tasks_from"] == "prepare"
    assert prepare.index(adapter) < prepare.index(stage)
    activation = yaml.safe_load((REPO_ROOT / "ansible/playbooks/tasks/transport-egress-activate.yml").read_text())[0]["block"]
    assert [task["ansible.builtin.include_role"] for task in activation[:2]] == [
        {"name": "warp-outbound", "tasks_from": "activate"},
        {"name": "transport-egress", "tasks_from": "activate"},
    ]
    site = next(play for play in plays if "roles" in play)
    post = next(task for task in site["post_tasks"] if task.get("ansible.builtin.import_tasks") == "tasks/transport-egress-activate.yml")
    assert set(roles[names.index("xray")]["tags"]) <= set(post["tags"])
    vendor = yaml.safe_load((ROLE / "tasks/activate.yml").read_text())[0]["block"]
    readiness = next(task for task in vendor if task["name"] == "Require actual UP TUN identity before recipient gateway admission")
    identity = next(task for task in vendor if task["name"] == "Retain actual verified tunnel identity")
    assert readiness["ansible.builtin.command"]["argv"][-1] == "refresh"
    assert readiness["until"] == "_warp_tunnel_readiness.rc == 0"
    assert vendor.index(readiness) < vendor.index(identity)


@pytest.mark.parametrize("present,kind,tun_type,flags,admitted", [
    (False, "tun", "tun", ["UP"], False),
    (True, None, None, [], False),
    (True, "dummy", "tun", ["UP"], False),
    (True, "tun", "tap", ["UP"], False),
    (True, "tun", "tun", [], False),
    (True, "tun", "tun", ["UP"], True),
])
def test_health_gate_requires_owned_actual_up_tun_identity(monkeypatch, present, kind, tun_type, flags, admitted):
    # Portable predicate proof; real TUN/native and registered vendor acceptance
    # remain separate gates. HTTP/status text alone never enters this predicate.
    spec = importlib.util.spec_from_file_location("warp_pin_namespace", ROLE / "files/namespace.py")
    namespace = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(namespace)
    monkeypatch.setattr(namespace, "inspect", lambda: {"present": present})
    link = None if kind is None else {"ifindex": 42, "flags": copy.deepcopy(flags),
                                     "linkinfo": {"info_kind": kind, "info_data": {"type": tun_type}}}
    def actual_link(name, inside=False):
        assert name == namespace.TUNNEL and inside is True
        return link
    monkeypatch.setattr(namespace, "link", actual_link)
    if admitted:
        assert namespace.tunnel() == 42
    else:
        with pytest.raises(namespace.Refusal, match="namespace-(absent|tunnel-not-ready)"):
            namespace.tunnel()
