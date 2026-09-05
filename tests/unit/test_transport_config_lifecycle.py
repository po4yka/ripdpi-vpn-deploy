"""Transport configs fail before publication and restarts prove liveness."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"
VALIDATOR = ANSIBLE / "roles/runtime-release/files/validate_yaml_mapping.py"


def _tasks(role: str) -> list[dict]:
    return yaml.safe_load((ANSIBLE / f"roles/{role}/tasks/main.yml").read_text())


def _handlers(role: str) -> list[dict]:
    return yaml.safe_load((ANSIBLE / f"roles/{role}/handlers/main.yml").read_text())


def _named(items: list[dict], name: str) -> dict:
    return next(item for item in items if item["name"] == name)


def test_shared_yaml_validator_rejects_invalid_duplicate_and_missing_keys(
    tmp_path: Path,
) -> None:
    valid = tmp_path / "valid.yaml"
    valid.write_text("listen: endpoint\nforward: {}\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--require-string",
            "listen",
            "--require-mapping",
            "forward",
            str(valid),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr

    for content in (
        "- item\n",
        "listen: {}\nlisten: {}\n",
        "listen: {}\n",
        "? [listen, forward]\n: value\n",
        "listen: endpoint\nforward: []\n",
    ):
        invalid = tmp_path / "invalid.yaml"
        invalid.write_text(content, encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--require-string",
                "listen",
                "--require-mapping",
                "forward",
                str(invalid),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode != 0
        assert str(invalid) not in result.stderr


def test_role_profiles_reject_wrong_types_and_missing_nested_fields(
    tmp_path: Path,
) -> None:
    valid = {
        "hysteria": {
            "listen": ":443",
            "tls": {"cert": "/cert", "key": "/key"},
            "auth": {"type": "userpass", "userpass": {"alice": "secret"}},
            "bandwidth": {"up": "100 mbps", "down": "200 mbps"},
            "masquerade": {"type": "proxy", "proxy": {"url": "https://example.test"}},
            "quic": {
                "initStreamReceiveWindow": 1,
                "maxStreamReceiveWindow": 1,
                "initConnReceiveWindow": 1,
                "maxConnReceiveWindow": 1,
            },
        },
        "dns-morph": {
            "listen": {"address": "0.0.0.0", "port": 53},
            "forward": {"address": "127.0.0.1", "port": 5353, "protocol": "udp"},
            "morph": {"signing_key": "fixture", "upstream_endpoint": ""},
            "limits": {"events_per_minute_max": 1},
            "log": {"dir": "/var/log/dns-morph"},
        },
    }
    invalid = {
        "hysteria": {**valid["hysteria"], "listen": {}},
        "dns-morph": {
            **valid["dns-morph"],
            "listen": {"address": "0.0.0.0", "port": "53"},
        },
    }

    for profile in valid:
        path = tmp_path / f"{profile}.yaml"
        path.write_text(yaml.safe_dump(valid[profile]), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--profile", profile, str(path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0, result.stderr

        path.write_text(yaml.safe_dump(invalid[profile]), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--profile", profile, str(path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode != 0

    for listen in (":invalid", ":0", ":65536", ":443,50000-40000", ":443,1-invalid"):
        path = tmp_path / "hysteria-listen.yaml"
        path.write_text(
            yaml.safe_dump({**valid["hysteria"], "listen": listen}), encoding="utf-8"
        )
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--profile", "hysteria", str(path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode != 0


def test_transport_templates_use_format_specific_validation() -> None:
    hysteria = _named(_tasks("hysteria"), "Render Hysteria config")[
        "ansible.builtin.template"
    ]
    realm = _named(_tasks("hysteria-realm"), "Render sing-box realm config")[
        "ansible.builtin.template"
    ]
    naive = _named(_tasks("naive"), "Render Caddyfile")["ansible.builtin.template"]
    dns = _named(_tasks("dns-morph-bridge"), "Render bridge config")[
        "ansible.builtin.template"
    ]

    assert hysteria["validate"].endswith("--profile hysteria %s")
    assert realm["validate"] == "/usr/local/bin/sing-box-realm check -c %s"
    assert naive["validate"] == (
        "/usr/local/bin/caddy-naive validate --config %s --adapter caddyfile"
    )
    assert dns["validate"].endswith("--profile dns-morph %s")


def test_restart_only_handlers_wait_for_service_liveness() -> None:
    for role, topic, service in (
        ("naive", "Restart caddy-naive", "caddy-naive.service"),
        ("dns-morph-bridge", "Restart dns-morph-bridge", "dns-morph-bridge.service"),
    ):
        handlers = _handlers(role)
        waits = [
            item
            for item in handlers
            if item.get("listen") == topic and "ansible.builtin.command" in item
        ]
        assert len(waits) == 1
        wait = waits[0]
        assert (
            wait["ansible.builtin.command"]["cmd"] == f"systemctl is-active {service}"
        )
        assert wait["retries"] == 5
        assert wait["delay"] == 2
        assert wait["changed_when"] is False
        assert wait["when"] == "not ansible_check_mode"


def test_every_transport_molecule_runs_a_negative_validation_case() -> None:
    for role in ("hysteria", "hysteria-realm", "naive", "dns-morph-bridge"):
        scenario = yaml.safe_load(
            (ANSIBLE / f"roles/{role}/molecule/default/molecule.yml").read_text()
        )
        assert "side_effect" in scenario["scenario"]["test_sequence"]
        side_effect = yaml.safe_load(
            (ANSIBLE / f"roles/{role}/molecule/default/side_effect.yml").read_text()
        )
        serialized = yaml.safe_dump(side_effect)
        assert "failed_when: false" in serialized
        assert "rc != 0" in serialized
