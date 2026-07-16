"""Exercise the public-listener verification embedded in the playbook."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "security-verify.yml"


def _listener(
    name: str,
    protocol: str,
    *,
    port: int | None = None,
    port_range: str | None = None,
) -> dict:
    return {
        "name": name,
        "protocol": protocol,
        "port": port,
        "port_range": port_range,
    }


def _verify_listeners(tmp_path: Path, contract: list[dict], ss_output: str) -> str:
    play = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))[0]
    task = next(task for task in play["tasks"] if task["name"] == "Public listeners match enabled profile manifest")
    command = (
        jinja2.Environment(undefined=jinja2.StrictUndefined)
        .from_string(task["ansible.builtin.shell"]["cmd"])
        .render(public_listener_contract=contract)
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ss = fake_bin / "ss"
    fake_ss.write_text('#!/bin/sh\nprintf "%s\\n" "$FAKE_SS_OUTPUT"\n', encoding="utf-8")
    fake_ss.chmod(fake_ss.stat().st_mode | stat.S_IXUSR)
    env = {
        **os.environ,
        "FAKE_SS_OUTPUT": ss_output,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    result = subprocess.run(
        ["/bin/bash", "-c", command],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


def _ss_line(protocol: str, address: str) -> str:
    return f"{protocol} LISTEN 0 128 {address} 0.0.0.0:*"


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1:443", "127.9.8.7:443", "localhost:443", "[::1]:443", "::1:443"],
)
def test_loopback_only_socket_does_not_satisfy_public_listener_contract(tmp_path: Path, address: str) -> None:
    output = _verify_listeners(
        tmp_path,
        [_listener("xray", "tcp", port=443)],
        _ss_line("tcp", address),
    )

    assert output == "missing tcp 443\n"


def test_public_socket_satisfies_public_listener_contract(tmp_path: Path) -> None:
    output = _verify_listeners(
        tmp_path,
        [_listener("xray", "tcp", port=443)],
        _ss_line("tcp", "0.0.0.0:443"),
    )

    assert output == ""


def test_partial_udp_range_does_not_satisfy_public_listener_contract(tmp_path: Path) -> None:
    output = _verify_listeners(
        tmp_path,
        [_listener("hysteria", "udp", port_range="20000-20002")],
        "\n".join(
            [
                _ss_line("udp", "0.0.0.0:20000"),
                _ss_line("udp", "0.0.0.0:20002"),
            ]
        ),
    )

    assert output == "missing udp 20001 (required by range 20000-20002)\n"


def test_complete_udp_range_satisfies_public_listener_contract(tmp_path: Path) -> None:
    output = _verify_listeners(
        tmp_path,
        [_listener("hysteria", "udp", port_range="20000-20002")],
        "\n".join(_ss_line("udp", f"[::]:{port}") for port in range(20000, 20003)),
    )

    assert output == ""
