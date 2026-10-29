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
    verdict: str = "accept",
) -> dict:
    expressions: list[dict] = []
    if broad_protocol is not None:
        expressions.append(
            {
                "match": {
                    "op": "==",
                    "left": {"meta": {"key": "l4proto"}},
                    "right": broad_protocol,
                }
            }
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
        source_value = source_address or "203.0.113.7"
        source_protocol = "ip6" if ":" in source_value else "ip"
        expressions.append(
            {
                "match": {
                    "op": "in",
                    "left": {
                        "payload": {"protocol": source_protocol, "field": "saddr"}
                    },
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
    expressions.append({verdict: None})
    return {
        "rule": {
            "family": "inet",
            "table": "filter",
            "chain": "input",
            "expr": expressions,
        }
    }


def _nft_document(*rules: dict) -> str:
    return json.dumps({"nftables": list(rules)})


def _nft_for_contract(contract: list[dict]) -> str:
    rules: list[dict] = []
    for listener in contract:
        target = (
            listener["port"] if listener["port"] is not None else listener["port_range"]
        )
        rules.append(_nft_rule(listener["protocol"], target))
    return _nft_document(*rules)


def _dhcpv6_reply(source=None, *, interface="uplink0") -> dict:
    rule = _nft_rule("udp", 546, input_interface=interface)
    rule["rule"]["expr"][-1:-1] = [
        {"match": {"op": "==", "left": {"payload": {"protocol": "ip6", "field": "saddr"}},
                   "right": source if source is not None else {"prefix": {"addr": "fe80::", "len": 10}}}},
        {"match": {"op": "==", "left": {"fib": {"result": "type", "flags": ["daddr"]}}, "right": "local"}},
        {"match": {"op": "==", "left": {"payload": {"protocol": "udp", "field": "sport"}}, "right": 547}},
        {"counter": {"packets": 0, "bytes": 0}},
    ]
    return rule


def _dhcpv6_deny() -> dict:
    rule = _nft_rule('udp', 546, verdict='drop')
    rule['rule']['expr'][-1:-1] = [
        {'match': {'op': '==', 'left': {'meta': {'key': 'nfproto'}}, 'right': 'ipv6'}},
        {'match': {'op': '==', 'left': {'payload': {'protocol': 'udp', 'field': 'sport'}}, 'right': 547}},
        {'counter': {'packets': 0, 'bytes': 0}},
    ]
    return rule


def _verify_listeners(
    tmp_path: Path,
    contract: list[dict],
    ss_output: str,
    *,
    nft_output: str | None = None,
    ssh_port: int = 22,
    tailnet_sources: list[str] | None = None,
    include_tailnet_drop: bool = True,
    native_acme: bool = False,
    dhcpv6_rules: list[dict] | None = None,
    dhcpv6_servers=None,
    dhcpv6_uplink: str = "uplink0",
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    for command, variable in (("ss", "FAKE_SS_OUTPUT"), ("nft", "FAKE_NFT_OUTPUT")):
        executable = fake_bin / command
        executable.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "${variable}"\n', encoding="utf-8"
        )
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    encoded_contract = base64.b64encode(json.dumps(contract).encode()).decode()
    encoded_tailnet = base64.b64encode(
        json.dumps(tailnet_sources or []).encode()
    ).decode()
    resolved_nft = nft_output if nft_output is not None else _nft_for_contract(contract)
    document = json.loads(resolved_nft)
    document["nftables"][0:0] = [_dhcpv6_reply(), _dhcpv6_deny()] if dhcpv6_rules is None else dhcpv6_rules
    resolved_nft = json.dumps(document)
    if include_tailnet_drop:
        document = json.loads(resolved_nft)
        drop = _nft_rule("tcp", ssh_port, input_interface="tailscale0", verdict="drop")
        insertion = len(document["nftables"]) if tailnet_sources else 0
        document["nftables"].insert(insertion, drop)
        resolved_nft = json.dumps(document)
    env = {
        **os.environ,
        "FAKE_SS_OUTPUT": ss_output,
        "FAKE_NFT_OUTPUT": resolved_nft,
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
            "--dhcpv6-uplink", dhcpv6_uplink,
            "--dhcpv6-servers-b64", base64.b64encode(json.dumps(
                [] if dhcpv6_servers is None else dhcpv6_servers
            ).encode()).decode(),
        ] + (["--native-acme"] if native_acme else []),
        capture_output=True,
        env=env,
        text=True,
    )


def _ss_line(protocol: str, address: str) -> str:
    return f"{protocol} LISTEN 0 128 {address} 0.0.0.0:*"


@pytest.mark.parametrize('active', [False, True])
@pytest.mark.parametrize('native_acme', [False, True])
def test_native_acme_socket_is_transient_but_its_firewall_allowance_is_required(tmp_path, active, native_acme):
    contract = [_listener('hysteria-acme', 'tcp', port=80), _listener('hysteria', 'udp', port=443)]
    sockets = _ss_line('udp', '0.0.0.0:443') + ('\n' + _ss_line('tcp', '0.0.0.0:80') if active else '')
    result = _verify_listeners(tmp_path, contract, sockets, native_acme=native_acme)
    assert result.returncode == (0 if native_acme or active else 1), result.stdout + result.stderr
    if not native_acme and not active: assert 'missing tcp 80' in result.stdout
    result = _verify_listeners(tmp_path, contract, sockets, nft_output=_nft_for_contract(contract[1:]), native_acme=native_acme)
    assert result.returncode == 1 and 'missing firewall tcp 80' in result.stdout


def test_ordinary_http_listener_remains_required(tmp_path):
    result = _verify_listeners(tmp_path, [_listener('public-site-http', 'tcp', port=80)], '', native_acme=True)
    assert result.returncode == 1 and result.stdout == 'missing tcp 80\n'


@pytest.mark.parametrize('protocol,port', [('tcp', 443), ('udp', 80)])
def test_transient_acme_role_cannot_relax_another_socket(tmp_path, protocol, port):
    result = _verify_listeners(tmp_path, [_listener('hysteria-acme', protocol, port=port)], '')
    assert result.returncode == 2 and 'requires exactly TCP/80' in result.stderr


def test_playbook_runs_repository_listener_verifier() -> None:
    play = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))[0]
    task = next(
        task
        for task in play["tasks"]
        if task["name"] == "Public listeners match enabled profile manifest"
    )

    assert "ansible.builtin.script" in task
    assert "scripts/verify-public-listeners.py" in task["ansible.builtin.script"]["cmd"]
    assert "--ssh-port" in task["ansible.builtin.script"]["cmd"]
    assert "security_effective_ssh_ports[0]" in task["ansible.builtin.script"]["cmd"]
    assert "--tailnet-sources-b64" in task["ansible.builtin.script"]["cmd"]
    assert "vpn.enable_tailnet_management" in task["ansible.builtin.script"]["cmd"]
    assert task["failed_when"] == "security_unexpected_public_listeners.rc != 0"
    gather = next(t for t in play['tasks'] if t['name'] == 'Gather network facts for DHCPv6 scope verification')
    admission = next(t for t in play['tasks'] if t['name'] == 'Admit DHCPv6 scope before listener verification')
    assert gather['ansible.builtin.setup']['gather_subset'] == ['!all', '!min', 'network']
    assert admission['ansible.builtin.import_tasks'] == '../roles/firewall/tasks/dhcpv6-admission.yml'
    assert play['tasks'].index(gather) < play['tasks'].index(admission) < play['tasks'].index(task)


@pytest.mark.parametrize('enabled,native,subscription_only,expected', [
    (True, True, False, True), (True, False, False, False),
    (False, True, False, False), (True, True, True, False),
])
@pytest.mark.parametrize('tailnet_enabled', [False, True])
@pytest.mark.parametrize('path_with_spaces', [False, True])
def test_security_playbook_declares_transience_only_for_enabled_native_acme(
    tmp_path, enabled, native, subscription_only, expected,
    tailnet_enabled, path_with_spaces,
):
    from scripts.template_render import render_fragment

    play = yaml.safe_load(PLAYBOOK.read_text())[0]
    task = next(task for task in play['tasks'] if task['name'] == 'Public listeners match enabled profile manifest')
    root = tmp_path / ('command path' if path_with_spaces else 'command-path')
    script = root / 'scripts' / 'verify-public-listeners.py'
    script.parent.mkdir(parents=True)
    script.write_text(
        '#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n'
    )
    script.chmod(0o755)
    playbook_dir = root / 'ansible' / 'playbooks'
    playbook_dir.mkdir(parents=True)
    command = render_fragment('security-command.sh.j2', task['ansible.builtin.script']['cmd'], {
        'playbook_dir': str(playbook_dir), 'terraform_public_listeners_b64': 'W10=',
        'security_effective_ssh_ports': [2202],
        'vpn': {'enable_hysteria': enabled, 'enable_tailnet_management': tailnet_enabled},
        'tailnet_management': {'approved_sources': ['100.64.0.2']},
        'firewall_effective_dhcpv6_uplink_interface': 'uplink0',
        'firewall_effective_dhcpv6_server_addresses': ['2001:db8::20'],
        'vpn_subscription_only': subscription_only, 'hysteria': {'acme': {}} if native else {},
    })
    result = subprocess.run(['/bin/sh', '-c', command], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == [
        '--contract-b64', 'W10=', '--ssh-port', '2202',
        '--dhcpv6-uplink', 'uplink0', '--dhcpv6-servers-b64', 'WyIyMDAxOmRiODo6MjAiXQ==',
        '--tailnet-sources-b64', 'WyIxMDAuNjQuMC4yIl0=' if tailnet_enabled else 'W10=',
    ] + (['--native-acme'] if expected else [])

    tailnet_check = next(
        item
        for item in play["tasks"]
        if item["name"] == "Tailnet management state matches the restricted policy"
    )
    assert tailnet_check["ansible.builtin.command"]["argv"][-1].endswith(
        "tailnet-check.py"
    )
    assert "vpn.enable_tailnet_management" in tailnet_check["when"]


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


@pytest.mark.parametrize(
    "address", ["0.0.0.0:443", "[::]:443", "8.8.8.8:443", "[2001:4860::1]:443"]
)
def test_public_socket_satisfies_public_listener_contract(
    tmp_path: Path, address: str
) -> None:
    result = _verify_listeners(
        tmp_path,
        [_listener("xray", "tcp", port=443)],
        _ss_line("tcp", address),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_blocked_wildcard_and_private_auxiliary_sockets_are_not_public_exposure(
    tmp_path: Path,
) -> None:
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


def test_unexpected_firewall_exposure_fails_even_when_socket_is_listening(
    tmp_path: Path,
) -> None:
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


def test_partial_udp_range_does_not_satisfy_public_listener_contract(
    tmp_path: Path,
) -> None:
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
        nft_output=_nft_document(
            _nft_rule("tcp", 443), _nft_rule(broad_protocol="tcp")
        ),
    )

    assert result.returncode == 1
    assert "unexpected broad firewall accept" in result.stdout


def test_source_or_interface_restricted_rule_does_not_satisfy_public_contract(
    tmp_path: Path,
) -> None:
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


def test_tailnet_ssh_resolves_exact_members_of_named_nft_sets(tmp_path: Path) -> None:
    source = "100.64.10.20"
    rule = _nft_rule(
        "tcp", 22, source_address="@vpn_tailnet_ssh_v4", input_interface="tailscale0"
    )
    nft_set = {
        "set": {
            "family": "inet",
            "table": "filter",
            "name": "vpn_tailnet_ssh_v4",
            "type": "ipv4_addr",
            "elem": [source],
        }
    }
    drop = _nft_rule("tcp", 22, input_interface="tailscale0", verdict="drop")
    public = _nft_rule("tcp", 22, source_restricted=True)

    accepted = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(nft_set, rule, drop, public),
        tailnet_sources=[source],
        include_tailnet_drop=False,
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr

    for members in ([], [source, "100.64.10.21"], ["100.64.10.21"]):
        nft_set["set"]["elem"] = members
        refused = _verify_listeners(
            tmp_path,
            [],
            "",
            nft_output=_nft_document(nft_set, rule, drop, public),
            tailnet_sources=[source],
            include_tailnet_drop=False,
        )
        assert refused.returncode == 1
        assert "missing Tailnet SSH source rule" in refused.stdout


def test_icmp_type_accept_is_narrow_but_broad_icmp_accept_is_rejected(
    tmp_path: Path,
) -> None:
    typed = {
        "rule": {
            "family": "inet",
            "table": "filter",
            "chain": "input",
            "expr": [
                {
                    "match": {
                        "op": "==",
                        "left": {"payload": {"protocol": "icmpv6", "field": "type"}},
                        "right": "echo-request",
                    }
                },
                {"accept": None},
            ],
        }
    }
    accepted = _verify_listeners(tmp_path, [], "", nft_output=_nft_document(typed))
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr

    typed["rule"]["expr"] = [
        {
            "match": {
                "op": "==",
                "left": {"meta": {"key": "l4proto"}},
                "right": "ipv6-icmp",
            }
        },
        {"accept": None},
    ]
    refused = _verify_listeners(tmp_path, [], "", nft_output=_nft_document(typed))
    assert refused.returncode == 1
    assert "unexpected broad firewall accept" in refused.stdout


def test_ordinary_ssh_accepts_nested_nftables_prefix_sets(tmp_path: Path) -> None:
    rule = _nft_rule("tcp", 22, source_restricted=True)
    source_match = next(
        expression["match"]
        for expression in rule["rule"]["expr"]
        if expression.get("match", {}).get("left", {}).get("payload", {}).get("field")
        == "saddr"
    )
    source_match["right"] = {
        "set": [
            {"prefix": {"addr": "203.0.113.0", "len": 24}},
            "198.51.100.7",
        ]
    }

    result = _verify_listeners(tmp_path, [], "", nft_output=_nft_document(rule))

    assert result.returncode == 0


def test_tailnet_ssh_still_rejects_prefix_source_expressions(tmp_path: Path) -> None:
    rule = _nft_rule(
        "tcp",
        22,
        source_restricted=True,
        source_address="100.64.1.2",
        input_interface="tailscale0",
    )
    source_match = next(
        expression["match"]
        for expression in rule["rule"]["expr"]
        if expression.get("match", {}).get("left", {}).get("payload", {}).get("field")
        == "saddr"
    )
    source_match["right"] = {"prefix": {"addr": "100.64.1.2", "len": 32}}

    result = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(rule),
        tailnet_sources=["100.64.1.2"],
    )

    assert result.returncode == 1
    assert "unexpected unrestricted firewall tcp 22" in result.stdout


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
        tmp_path,
        [],
        "",
        nft_output=_nft_document(
            _nft_rule("tcp", 22, source_address=source, input_interface="tailscale0")
        ),
        tailnet_sources=[source],
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_tailnet_ssh_requires_drop_between_exact_and_public_accepts(
    tmp_path: Path,
) -> None:
    exact = _nft_rule(
        "tcp", 22, source_address="100.64.10.20", input_interface="tailscale0"
    )
    drop = _nft_rule("tcp", 22, input_interface="tailscale0", verdict="drop")
    public = _nft_rule("tcp", 22, source_restricted=True)

    accepted = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(exact, drop, public),
        tailnet_sources=["100.64.10.20"],
        include_tailnet_drop=False,
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr

    for rules in ((exact, public), (drop, exact, public), (exact, public, drop)):
        refused = _verify_listeners(
            tmp_path,
            [],
            "",
            nft_output=_nft_document(*rules),
            tailnet_sources=["100.64.10.20"],
            include_tailnet_drop=False,
        )
        assert refused.returncode == 1
        assert "invalid Tailnet SSH drop ordering" in refused.stdout


@pytest.mark.parametrize(
    ("source", "interface"), [("100.64.10.21", "tailscale0"), ("100.64.10.20", "eth0")]
)
def test_wrong_tailnet_source_or_interface_scoped_ssh_rule_is_rejected(
    tmp_path: Path, source: str, interface: str
) -> None:
    result = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(
            _nft_rule("tcp", 22, source_address=source, input_interface=interface)
        ),
        tailnet_sources=["100.64.10.20"],
    )
    assert result.returncode == 1
    assert "unexpected unrestricted firewall tcp 22" in result.stdout
    assert "missing Tailnet SSH source rule" in result.stdout


@pytest.mark.parametrize("copies", [0, 2])
def test_missing_or_duplicate_tailnet_ssh_source_rule_is_rejected(
    tmp_path: Path, copies: int
) -> None:
    rule = _nft_rule(
        "tcp", 22, source_address="100.64.10.20", input_interface="tailscale0"
    )
    result = _verify_listeners(
        tmp_path,
        [],
        "",
        nft_output=_nft_document(*(rule for _ in range(copies))),
        tailnet_sources=["100.64.10.20"],
    )
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


def test_baseline_loopback_conntrack_and_icmp_accepts_are_allowed(
    tmp_path: Path,
) -> None:
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
            accepted(
                {"payload": {"protocol": "icmp", "field": "type"}}, "echo-request"
            ),
            accepted(
                {"payload": {"protocol": "icmpv6", "field": "type"}}, "echo-request"
            ),
        ),
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('servers,source', [
    (['2001:db8::20'], '2001:db8::20'),
    (['2001:db8::20'], {'set': ['2001:db8::20']}),
    (['2001:db8::20', '2001:db8::21'], {'set': ['2001:db8::21', '2001:db8::20']}),
])
def test_exact_dhcpv6_server_authority_is_not_a_public_listener(tmp_path, servers, source):
    result = _verify_listeners(tmp_path, [], '', dhcpv6_servers=servers,
        dhcpv6_rules=[_dhcpv6_reply(), _dhcpv6_reply(source), _dhcpv6_deny()])
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('path,replacement', [
    ((1,), None),
    ((1, 'match', 'right'), 'other0'),
    ((1, 'match', 'right'), {'set': ['uplink0', 'other0']}),
    ((2,), None),
    ((2, 'match', 'left', 'payload', 'protocol'), 'ip'),
    ((2, 'match', 'right'), {'prefix': {'addr': '::', 'len': 0}}),
    ((2, 'match', 'right'), {'prefix': {'addr': 'fe80::', 'len': 10.0}}),
    ((2, 'match', 'right'), '2001:db8::20'),
    ((3,), None),
    ((3, 'match', 'right'), 'unicast'),
    ((3, 'match', 'left', 'fib', 'flags'), ['saddr']),
    ((4,), None),
    ((4, 'match', 'right'), 548),
    ((4, 'match', 'right'), 547.0),
    ((0, 'match', 'right'), {'range': [546, 547]}),
    ((5,), {'unknown': None}),
    ((5,), {'match': {'op': '==', 'left': {'meta': {'key': 'iifname'}}, 'right': 'uplink0'}}),
])
def test_dhcpv6_reply_requires_every_exact_scope_predicate(tmp_path, path, replacement):
    rule = _dhcpv6_reply()
    rule['rule']['comment'] = 'dhcpv6-client-reply'
    expressions = rule['rule']['expr']
    if len(path) == 1 and replacement is None:
        del expressions[path[0]]
    else:
        target = expressions
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = replacement
    result = _verify_listeners(tmp_path, [], '', dhcpv6_rules=[rule, _dhcpv6_deny()])
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.parametrize('rules,servers', [
    ([], []),
    ([_dhcpv6_reply(), _dhcpv6_reply()], []),
    ([_dhcpv6_reply()], ['2001:db8::20']),
    ([_dhcpv6_reply(), _dhcpv6_reply('2001:db8::20')], []),
    ([_dhcpv6_reply(), _dhcpv6_reply('2001:db8::21')], ['2001:db8::20']),
    ([_dhcpv6_reply(), _dhcpv6_reply('2001:db8::20'), _dhcpv6_reply('2001:db8::20')], ['2001:db8::20']),
])
def test_dhcpv6_rule_coverage_is_exact(tmp_path, rules, servers):
    result = _verify_listeners(tmp_path, [], '', dhcpv6_rules=[*rules, _dhcpv6_deny()], dhcpv6_servers=servers)
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.parametrize('rules', [
    [_dhcpv6_reply()],
    [_dhcpv6_reply(), _dhcpv6_deny(), _dhcpv6_deny()],
])
def test_dhcpv6_requires_one_exact_deny(tmp_path, rules):
    result = _verify_listeners(tmp_path, [], '', dhcpv6_rules=rules)
    assert result.returncode == 1
    assert 'invalid DHCPv6 reply deny rule count' in result.stdout


@pytest.mark.parametrize('path,replacement', [
    ((1,), None),
    ((1, 'match', 'right'), 'ipv4'),
    ((2,), None),
    ((2, 'match', 'right'), 548),
    ((0, 'match', 'right'), {'range': [546, 547]}),
    ((3,), {'match': {'op': '==', 'left': {'meta': {'key': 'iifname'}}, 'right': 'uplink0'}}),
    ((4,), None),
])
def test_dhcpv6_deny_cannot_be_widened_or_narrowed(tmp_path, path, replacement):
    rule = _dhcpv6_deny()
    target = rule['rule']['expr']
    if len(path) == 1 and replacement is None:
        del target[path[0]]
    else:
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = replacement
    result = _verify_listeners(tmp_path, [], '', dhcpv6_rules=[_dhcpv6_reply(), rule])
    assert result.returncode == 1
    assert 'invalid DHCPv6 reply deny rule count' in result.stdout


@pytest.mark.parametrize('order,accepted', [
    (['reply', 'deny', 'established'], True),
    (['established', 'reply', 'deny'], False),
    (['reply', 'established', 'deny'], False),
    (['deny', 'reply', 'established'], False),
    (['established', 'reply', 'deny', 'established'], False),
])
def test_dhcpv6_scope_precedes_conntrack_acceptance(tmp_path, order, accepted):
    established = _nft_rule()
    established['rule']['expr'].insert(0, {'match': {
        'op': 'in', 'left': {'ct': {'key': 'state'}},
        'right': {'set': ['established', 'related']},
    }})
    rules = {'reply': _dhcpv6_reply(), 'deny': _dhcpv6_deny(), 'established': established}
    result = _verify_listeners(tmp_path, [], '', dhcpv6_rules=[rules[name] for name in order])
    assert result.returncode == (0 if accepted else 1), result.stdout + result.stderr
    if not accepted:
        assert 'invalid DHCPv6 reply rule ordering' in result.stdout


@pytest.mark.parametrize('servers', [
    '2001:db8::20', [True], ['::'], ['::1'], ['::/0'], ['ff02::1:2'],
    ['192.0.2.2'], ['::ffff:c000:202'], ['fe80::20%uplink0'], ['2001:DB8::20'],
    ['2001:db8::20', '2001:db8::20'], [f'2001:db8::{i:x}' for i in range(17)],
])
def test_dhcpv6_server_authority_rejects_noncanonical_or_unbounded_values(tmp_path, servers):
    result = _verify_listeners(tmp_path, [], '', dhcpv6_servers=servers)
    assert result.returncode == 2
    assert 'DHCPv6 servers' in result.stderr


@pytest.mark.parametrize('predicate', [
    {'match': {'op': '==', 'left': {'payload': {'protocol': 'udp', 'field': 'sport'}}, 'right': 547}},
    {'match': {'op': '==', 'left': {'fib': {'result': 'type', 'flags': ['daddr']}}, 'right': 'local'}},
])
def test_dhcpv6_predicates_do_not_relax_public_service_rules(tmp_path, predicate):
    rule = _nft_rule('udp', 443)
    rule['rule']['expr'].insert(0, predicate)
    result = _verify_listeners(tmp_path, [_listener('hysteria', 'udp', port=443)],
        _ss_line('udp', '0.0.0.0:443'), nft_output=_nft_document(rule))
    assert result.returncode == 1
    assert 'restricted or unsupported firewall udp 443' in result.stdout


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
