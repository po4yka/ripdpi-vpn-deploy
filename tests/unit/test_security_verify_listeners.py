"""Exercise the public-listener and firewall exposure verifier."""

from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "security-verify.yml"
VERIFIER = REPO_ROOT / "scripts" / "verify-public-listeners.py"


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


def _nft_rule(
    protocol: str | None = None,
    target: int | str | None = None,
    *,
    source_restricted: bool = False,
    source_address: str | None = None,
    input_interface: str | None = None,
    broad_protocol: str | None = None,
) -> dict:
    expressions: list[dict] = []
    if broad_protocol is not None:
        expressions.append(
            {"match": {"op": "==", "left": {"meta": {"key": "l4proto"}}, "right": broad_protocol}}
        )
    if protocol is not None and target is not None:
        right: object
        if isinstance(target, str) and "-" in target:
            right = {"range": [int(value) for value in target.split("-", 1)]}
        else:
            right = target
        expressions.append(
            {
                "match": {
                    "op": "==",
                    "left": {"payload": {"protocol": protocol, "field": "dport"}},
                    "right": right,
                }
            }
        )
    if source_restricted or source_address is not None:
        source_value = source_address or "@allowed_sources"
        source_protocol = "ip6" if ":" in source_value else "ip"
        expressions.append(
            {
                "match": {
                    "op": "in",
                    "left": {"payload": {"protocol": source_protocol, "field": "saddr"}},
                    "right": source_value,
                }
            }
        )
    if input_interface is not None:
        expressions.append(
            {
                "match": {
                    "op": "==",
                    "left": {"meta": {"key": "iifname"}},
                    "right": input_interface,
                }
            }
        )
    expressions.append({"accept": None})
    return {"rule": {"family": "inet", "table": "filter", "chain": "input", "expr": expressions}}


def _nft_document(*rules: dict) -> str:
    return json.dumps({"nftables": list(rules)})


def _nft_for_contract(contract: list[dict]) -> str:
    rules: list[dict] = []
    for listener in contract:
        target = listener["port"] if listener["port"] is not None else listener["port_range"]
        rules.append(_nft_rule(listener["protocol"], target))
    return _nft_document(*rules)


def _verify_listeners(
    tmp_path: Path,
    contract: list[dict],
    ss_output: str,
    *,
    nft_output: str | None = None,
    ssh_port: int = 22,
    tailnet_sources: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    for command, variable in (("ss", "FAKE_SS_OUTPUT"), ("nft", "FAKE_NFT_OUTPUT")):
        executable = fake_bin / command
        executable.write_text(f'#!/bin/sh\nprintf "%s\\n" "${variable}"\n', encoding="utf-8")
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    encoded_contract = base64.b64encode(json.dumps(contract).encode()).decode()
    encoded_tailnet = base64.b64encode(json.dumps(tailnet_sources or []).encode()).decode()
    env = {
        **os.environ,
        "FAKE_SS_OUTPUT": ss_output,
        "FAKE_NFT_OUTPUT": nft_output if nft_output is not None else _nft_for_contract(contract),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    return subprocess.run(
        [
            str(VERIFIER),
            "--contract-b64",
            encoded_contract,
            "--ssh-port",
            str(ssh_port),
            "--tailnet-sources-b64",
            encoded_tailnet,
        ],
        capture_output=True,
        env=env,
        text=True,
    )


def _ss_line(protocol: str, address: str) -> str:
    return f"{protocol} LISTEN 0 128 {address} 0.0.0.0:*"


def test_playbook_runs_repository_listener_verifier() -> None:
    play = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))[0]
    task = next(
        task for task in play["tasks"] if task["name"] == "Public listeners match enabled profile manifest"
    )

    assert "ansible.builtin.script" in task
    assert "scripts/verify-public-listeners.py" in task["ansible.builtin.script"]["cmd"]
    assert "--ssh-port {{ security_effective_ssh_ports[0] }}" in task[
        "ansible.builtin.script"
    ]["cmd"]
    assert "--tailnet-sources-b64" in task["ansible.builtin.script"]["cmd"]
    assert task["failed_when"] == "security_unexpected_public_listeners.rc != 0"


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1:443", "127.9.8.7:443", "localhost:443", "[::1]:443", "::1:443"],
)
def test_loopback_only_socket_does_not_satisfy_public_listener_contract(
    tmp_path: Path, address: str
) -> None:
    result = _verify_listeners(
        tmp_path,
        [_listener("xray", "tcp", port=443)],
        _ss_line("tcp", address),
    )

    assert result.returncode == 1
    assert result.stdout == "missing tcp 443\n"


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.2:443",
        "172.20.0.2:443",
        "192.168.1.2:443",
        "100.64.0.2:443",
        "169.254.1.2:443",
        "[fd00::2]:443",
        "[fe80::2%eth0]:443",
    ],
)
def test_private_socket_does_not_satisfy_public_listener_contract(
    tmp_path: Path, address: str
) -> None:
    result = _verify_listeners(
        tmp_path,
        [_listener("xray", "tcp", port=443)],
        _ss_line("tcp", address),
    )

    assert result.returncode == 1
    assert result.stdout == "missing tcp 443\n"


@pytest.mark.parametrize("address", ["0.0.0.0:443", "[::]:443", "8.8.8.8:443", "[2001:4860::1]:443"])
def test_public_socket_satisfies_public_listener_contract(tmp_path: Path, address: str) -> None:
    result = _verify_listeners(
        tmp_path,
        [_listener("xray", "tcp", port=443)],
        _ss_line("tcp", address),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_blocked_wildcard_and_private_auxiliary_sockets_are_not_public_exposure(tmp_path: Path) -> None:
    contract = [_listener("xray", "tcp", port=443)]
    result = _verify_listeners(
        tmp_path,
        contract,
        "\n".join(
            [
                _ss_line("tcp", "0.0.0.0:443"),
                _ss_line("tcp", "0.0.0.0:9100"),
                _ss_line("udp", "0.0.0.0:68"),
                _ss_line("tcp", "100.64.0.2:9090"),
                _ss_line("udp", "[fe80::2%eth0]:5353"),
            ]
        ),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_unexpected_firewall_exposure_fails_even_when_socket_is_listening(tmp_path: Path) -> None:
    contract = [_listener("xray", "tcp", port=443)]
    result = _verify_listeners(
        tmp_path,
        contract,
        "\n".join([_ss_line("tcp", "0.0.0.0:443"), _ss_line("tcp", "0.0.0.0:9100")]),
        nft_output=_nft_document(_nft_rule("tcp", 443), _nft_rule("tcp", 9100)),
    )

    assert result.returncode == 1
    assert result.stdout == "unexpected firewall tcp 9100\n"


def test_missing_firewall_exposure_fails_for_listening_socket(tmp_path: Path) -> None:
    result = _verify_listeners(
        tmp_path,
        [_listener("xray", "tcp", port=443)],
        _ss_line("tcp", "0.0.0.0:443"),
        nft_output=_nft_document(),
    )

    assert result.returncode == 1
    assert result.stdout == "missing firewall tcp 443\n"


def test_partial_udp_range_does_not_satisfy_public_listener_contract(tmp_path: Path) -> None:
    result = _verify_listeners(
        tmp_path,
        [_listener("hysteria", "udp", port_range="20000-20002")],
        "\n".join(
            [
                _ss_line("udp", "0.0.0.0:20000"),
                _ss_line("udp", "0.0.0.0:20002"),
            ]
        ),
    )

    assert result.returncode == 1
    assert result.stdout == "missing udp 20001 (required by range 20000-20002)\n"


def test_complete_udp_range_satisfies_public_listener_contract(tmp_path: Path) -> None:
    result = _verify_listeners(
        tmp_path,
        [_listener("hysteria", "udp", port_range="20000-20002")],
        "\n".join(_ss_line("udp", f"[::]:{port}") for port in range(20000, 20003)),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_broad_transport_accept_is_rejected(tmp_path: Path) -> None:
    contract = [_listener("xray", "tcp", port=443)]
    result = _verify_listeners(
        tmp_path,
        contract,
        _ss_line("tcp", "0.0.0.0:443"),
        nft_output=_nft_document(_nft_rule("tcp", 443), _nft_rule(broad_protocol="tcp")),
    )

    assert result.returncode == 1
    assert "unexpected broad firewall accept" in result.stdout


def test_source_or_interface_restricted_rule_does_not_satisfy_public_contract(tmp_path: Path) -> None:
    contract = [_listener("xray", "tcp", port=443)]
    for rule in (
        _nft_rule("tcp", 443, source_restricted=True),
        _nft_rule("tcp", 443, input_interface="tailscale0"),
    ):
        result = _verify_listeners(
            tmp_path,
            contract,
            _ss_line("tcp", "0.0.0.0:443"),
            nft_output=_nft_document(rule),
        )

        assert result.returncode == 1
        assert "restricted or unsupported firewall tcp 443" in result.stdout
        assert "missing firewall tcp 443" in result.stdout


def test_restricted_duplicate_cannot_hide_behind_public_rule(tmp_path: Path) -> None:
    contract = [_listener("xray", "tcp", port=443)]
    result = _verify_listeners(
        tmp_path,
        contract,
        _ss_line("tcp", "0.0.0.0:443"),
        nft_output=_nft_document(
            _nft_rule("tcp", 443),
            _nft_rule("tcp", 443, source_restricted=True),
        ),
    )

    assert result.returncode == 1
    assert result.stdout == "restricted or unsupported firewall tcp 443\n"


def test_unrestricted_ssh_rule_is_rejected(tmp_path: Path) -> None:
    result = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(_nft_rule("tcp", 22)),
    )

    assert result.returncode == 1
    assert result.stdout == "unexpected unrestricted firewall tcp 22\n"


def test_source_scoped_ssh_rule_is_allowed(tmp_path: Path) -> None:
    result = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(_nft_rule("tcp", 22, source_restricted=True)),
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("source", ["100.64.10.20", "fd7a:115c:a1e0::1234"])
def test_exact_tailnet_source_and_interface_scoped_ssh_rule_is_allowed(
    tmp_path: Path, source: str
) -> None:
    result = _verify_listeners(
        tmp_path, [], "",
        nft_output=_nft_document(_nft_rule(
            "tcp", 22, source_address=source, input_interface="tailscale0")),
        tailnet_sources=[source])
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(("source", "interface"), [
    ("100.64.10.21", "tailscale0"), ("100.64.10.20", "eth0")])
def test_wrong_tailnet_source_or_interface_scoped_ssh_rule_is_rejected(
    tmp_path: Path, source: str, interface: str
) -> None:
    result = _verify_listeners(
        tmp_path, [], "",
        nft_output=_nft_document(_nft_rule(
            "tcp", 22, source_address=source, input_interface=interface)),
        tailnet_sources=["100.64.10.20"])
    assert result.returncode == 1
    assert "unexpected unrestricted firewall tcp 22" in result.stdout
    assert "missing Tailnet SSH source rule" in result.stdout


@pytest.mark.parametrize("copies", [0, 2])
def test_missing_or_duplicate_tailnet_ssh_source_rule_is_rejected(
    tmp_path: Path, copies: int
) -> None:
    rule = _nft_rule("tcp", 22, source_address="100.64.10.20",
                     input_interface="tailscale0")
    result = _verify_listeners(
        tmp_path, [], "", nft_output=_nft_document(*(rule for _ in range(copies))),
        tailnet_sources=["100.64.10.20"])
    assert result.returncode == 1
    expected = "missing" if copies == 0 else "duplicate"
    assert f"{expected} Tailnet SSH source rule" in result.stdout


def test_custom_source_scoped_ssh_port_is_allowed(tmp_path: Path) -> None:
    result = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(_nft_rule("tcp", 2222, source_restricted=True)),
        ssh_port=2222,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_custom_unrestricted_ssh_port_is_rejected(tmp_path: Path) -> None:
    result = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(_nft_rule("tcp", 2222)),
        ssh_port=2222,
    )

    assert result.returncode == 1
    assert result.stdout == "unexpected unrestricted firewall tcp 2222\n"


def test_default_port_is_not_exempt_when_sshd_uses_custom_port(tmp_path: Path) -> None:
    result = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(_nft_rule("tcp", 22, source_restricted=True)),
        ssh_port=2222,
    )

    assert result.returncode == 1
    assert result.stdout == "unexpected firewall tcp 22\n"


def test_baseline_loopback_conntrack_and_icmp_accepts_are_allowed(tmp_path: Path) -> None:
    def accepted(left: dict, right: object) -> dict:
        return {
            "rule": {
                "family": "inet",
                "table": "filter",
                "chain": "input",
                "expr": [
                    {"match": {"op": "==", "left": left, "right": right}},
                    {"accept": None},
                ],
            }
        }

    result = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(
            accepted({"meta": {"key": "iif"}}, "lo"),
            accepted({"ct": {"key": "state"}}, ["established", "related"]),
            accepted({"payload": {"protocol": "ip", "field": "protocol"}}, "icmp"),
            accepted({"payload": {"protocol": "ip6", "field": "nexthdr"}}, "ipv6-icmp"),
        ),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_nft_port_set_is_rejected_fail_closed(tmp_path: Path) -> None:
    port_set_rule = {
        "rule": {
            "family": "inet",
            "table": "filter",
            "chain": "input",
            "expr": [
                {
                    "match": {
                        "op": "==",
                        "left": {"payload": {"protocol": "tcp", "field": "dport"}},
                        "right": {"set": [80, 443]},
                    }
                },
                {"accept": None},
            ],
        }
    }
    result = _verify_listeners(
        tmp_path,
        [_listener("xray", "tcp", port=443)],
        _ss_line("tcp", "0.0.0.0:443"),
        nft_output=_nft_document(port_set_rule),
    )

    assert result.returncode == 2
    assert "unsupported nftables tcp dport expression" in result.stderr


@pytest.mark.parametrize(
    "left,right",
    [
        ({"payload": {"protocol": "tcp", "field": "dport"}}, 443),
        ({"meta": {"key": "iif"}}, "lo"),
    ],
)
def test_negative_match_operator_is_rejected_fail_closed(
    tmp_path: Path, left: dict, right: object
) -> None:
    negative_rule = {
        "rule": {
            "family": "inet",
            "table": "filter",
            "chain": "input",
            "expr": [
                {"match": {"op": "!=", "left": left, "right": right}},
                {"accept": None},
            ],
        }
    }
    result = _verify_listeners(
        tmp_path,
        [_listener("xray", "tcp", port=443)],
        _ss_line("tcp", "0.0.0.0:443"),
        nft_output=_nft_document(negative_rule),
    )

    assert result.returncode == 1
    assert "unexpected broad firewall accept" in result.stdout
    assert "missing firewall tcp 443" in result.stdout


def test_unrecognized_accept_expression_is_rejected_fail_closed(tmp_path: Path) -> None:
    rule = _nft_rule("tcp", 443)
    rule["rule"]["expr"].insert(1, {"limit": {"rate": 1, "per": "second"}})
    result = _verify_listeners(
        tmp_path,
        [_listener("xray", "tcp", port=443)],
        _ss_line("tcp", "0.0.0.0:443"),
        nft_output=_nft_document(rule),
    )

    assert result.returncode == 1
    assert "restricted or unsupported firewall tcp 443" in result.stdout
