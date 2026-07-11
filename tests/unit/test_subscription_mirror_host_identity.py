"""Lock the subscription mirror's pinned SSH host-identity contract."""
from __future__ import annotations

from pathlib import Path

import yaml

from scripts.template_render import merge_render_vars, render_template

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = REPO_ROOT / "ansible" / "roles" / "subscription-host"
DEFAULTS = ROLE / "defaults" / "main.yml"
TASKS = ROLE / "tasks" / "mirror.yml"
TEMPLATE = ROLE / "templates" / "vpn-sub-mirror.sh.j2"


def _render_rsync(*, ssh_opts: str = "-o ConnectTimeout=10") -> str:
    variables = merge_render_vars()
    variables["subscription"] = {
        **variables["subscription"],
        "subscription_dir": "/var/lib/vpn-subscription",
        "mirror": {
            "enabled": True,
            "backend": "rsync",
            "source": "build@worker.example.test:/var/lib/vpn-subscription/",
            "rsync_opts": "-az --delete",
            "ssh_key_path": "/etc/vpn-subscription/mirror_ssh_key",
            "known_hosts": "worker.example.test ssh-ed25519 TEST-FIXTURE",
            "known_hosts_path": "/etc/vpn-subscription/mirror_known_hosts",
            "ssh_opts": ssh_opts,
        },
    }
    return render_template(TEMPLATE, variables)


def test_rsync_template_pins_host_identity_before_additive_options():
    rendered = _render_rsync()

    assert 'SSH_KNOWN_HOSTS="/etc/vpn-subscription/mirror_known_hosts"' in rendered
    assert 'SSH_OPTS="-o ConnectTimeout=10"' in rendered
    command = next(line for line in rendered.splitlines() if line.strip().startswith('-e "ssh '))
    fixed = [
        "-o StrictHostKeyChecking=yes",
        "-o UserKnownHostsFile=${SSH_KNOWN_HOSTS}",
        "-o GlobalKnownHostsFile=/dev/null",
        "-o BatchMode=yes",
    ]
    for option in fixed:
        assert option in command
        assert command.index(option) < command.index("${SSH_OPTS}")

    lowered = rendered.lower()
    assert "accept-new" not in lowered
    assert "stricthostkeychecking=no" not in lowered
    assert "ssh-keyscan" not in lowered


def test_rsync_rejects_unsafe_types_before_permission_repair():
    rendered = _render_rsync()
    rsync = rendered.index("rsync -az --delete")
    shell = rendered.index('-e "ssh ')

    for option in ("--no-links", "--no-devices", "--no-specials"):
        assert option in rendered[rsync:shell]
        assert rendered.index(option) > rendered.index("-az --delete")
    assert "--exclude=/revoked" in rendered[rsync:shell]
    assert "find \"$route_dir\" -mindepth 1 -maxdepth 1 -print0" in rendered
    assert "read -r -d '' entry" in rendered
    assert "^[0-9a-f]{64}(\\.meta)?$" in rendered
    assert 'validate_payload_dir "${DEST}/sub"' in rendered
    assert 'validate_payload_dir "${DEST}/bootstrap"' in rendered
    validation = rendered.index('validate_payload_dir "${DEST}/sub"')
    assert validation < rendered.index("chown -R")
    assert validation < rendered.index('find "$DEST" -type d -exec chmod')


def test_defaults_leave_pin_and_additive_options_empty():
    defaults = yaml.safe_load(DEFAULTS.read_text())
    mirror = defaults["subscription"]["mirror"]

    assert mirror["known_hosts"] == ""
    assert mirror["known_hosts_path"] == "/etc/vpn-subscription/mirror_known_hosts"
    assert mirror["ssh_opts"] == ""


def test_preflight_precedes_side_effects_and_pin_is_private():
    tasks = yaml.safe_load(TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert names[0] == "Validate mirror configuration before making host changes"
    assert names.index("Validate mirror configuration before making host changes") < names.index("Install mirror client (rsync)")
    preflight = tasks[0]["ansible.builtin.assert"]
    assert any("known_hosts" in condition for condition in preflight["that"])
    known_hosts_task = next(task for task in tasks if task["name"] == "Drop rsync known-hosts pin")
    copy = known_hosts_task["ansible.builtin.copy"]
    assert copy["mode"] == "0600"
    assert copy["owner"] == "vpn-bootstrap"
    assert copy["group"] == "vpn-bootstrap"
    assert known_hosts_task["no_log"] is True
    assert known_hosts_task["diff"] is False
