"""Tests for the provider-edge to runtime listener contract guard."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check-listener-contract.py"
MANIFEST_TEMPLATE = REPO_ROOT / "ansible" / "templates" / "listener-manifest.json.j2"
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"

spec = importlib.util.spec_from_file_location("listener_contract", SCRIPT)
contract = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = contract
spec.loader.exec_module(contract)

renderer_spec = importlib.util.spec_from_file_location("listener_renderer", RENDERER)
renderer = importlib.util.module_from_spec(renderer_spec)
sys.modules[renderer_spec.name] = renderer
renderer_spec.loader.exec_module(renderer)


def _expected(name: str, protocol: str, port: int) -> dict:
    return {"name": name, "protocol": protocol, "port": port, "port_range": None}


def _actual(role: str, protocol: str, port: int, *, enabled: bool = True) -> dict:
    return {"role": role, "protocol": protocol, "port": port, "enabled": enabled}


def test_matching_contract_passes() -> None:
    assert contract.check({
        "expected": [_expected("xray", "tcp", 443), _expected("amneziawg", "udp", 51820)],
        "actual": [_actual("xray", "tcp", 443), _actual("amneziawg", "udp", 51820)],
    }) == []


def test_missing_provider_edge_listener_fails_closed() -> None:
    findings = contract.check({
        "expected": [_expected("xray", "tcp", 443)],
        "actual": [_actual("xray", "tcp", 443), _actual("xray-fallback", "tcp", 2053)],
    })
    assert "runtime manifest lacks provider contract listener" in findings[0]
    assert "xray-fallback" in findings[0]


def test_disabled_runtime_listener_does_not_require_edge_rule() -> None:
    assert contract.check({
        "expected": [_expected("xray", "tcp", 443)],
        "actual": [_actual("xray", "tcp", 443), _actual("honeypot", "tcp", 4443, enabled=False)],
    }) == []


def test_port_range_is_compared_as_a_contract_value() -> None:
    assert contract.check({
        "expected": [{"name": "hysteria", "protocol": "udp", "port": None, "port_range": "20000-40000"}],
        "actual": [{"role": "hysteria", "protocol": "udp", "range": "20000-40000", "enabled": True}],
    }) == []


def test_default_runtime_manifest_matches_default_provider_contract() -> None:
    variables = renderer.merge_render_vars()
    actual = json.loads(renderer.render_template(MANIFEST_TEMPLATE, variables))
    expected = [
        _expected("xray", "tcp", 443),
        _expected("xray-fallback", "tcp", 2053),
        _expected("public-site-http", "tcp", 80),
        _expected("nginx-xhttp", "tcp", 8443),
        _expected("hysteria", "udp", 443),
        _expected("amneziawg", "udp", 51820),
    ]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_awg_evidence_server_listener_is_explicit_and_additive() -> None:
    variables = renderer.merge_render_vars()
    variables["real_vps_awg_nat_mode"] = "server"
    variables["real_vps_awg_nat_listen_port"] = 51920
    actual = json.loads(renderer.render_template(MANIFEST_TEMPLATE, variables))
    expected = [
        _expected("xray", "tcp", 443),
        _expected("xray-fallback", "tcp", 2053),
        _expected("public-site-http", "tcp", 80),
        _expected("nginx-xhttp", "tcp", 8443),
        _expected("hysteria", "udp", 443),
        _expected("amneziawg", "udp", 51820),
        _expected("awg-evidence", "udp", 51920),
    ]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_awg_evidence_echo_listeners_are_explicit_and_additive() -> None:
    variables = renderer.merge_render_vars()
    variables["real_vps_awg_nat_mode"] = "echo"
    variables["real_vps_awg_nat_tcp_echo_port"] = 10001
    variables["real_vps_awg_nat_udp_echo_port"] = 10002
    actual = json.loads(renderer.render_template(MANIFEST_TEMPLATE, variables))
    expected = [
        _expected("xray", "tcp", 443),
        _expected("xray-fallback", "tcp", 2053),
        _expected("public-site-http", "tcp", 80),
        _expected("nginx-xhttp", "tcp", 8443),
        _expected("hysteria", "udp", 443),
        _expected("amneziawg", "udp", 51820),
        _expected("awg-evidence-echo-tcp", "tcp", 10001),
        _expected("awg-evidence-echo-udp", "udp", 10002),
    ]
    assert contract.check({"expected": expected, "actual": actual}) == []


def _profile_manifest(name: str) -> list[dict]:
    variables = renderer.merge_render_vars()
    profile = yaml.safe_load((REPO_ROOT / "ansible" / "group_vars" / name).read_text())
    variables.update(profile)
    return json.loads(renderer.render_template(MANIFEST_TEMPLATE, variables))


def test_p0_minimal_listener_surface_is_reality_only() -> None:
    actual = _profile_manifest("vpn-p0-minimal.yml")
    expected = [_expected("xray", "tcp", 443), _expected("xray-fallback", "tcp", 2053)]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_p0_self_steal_keeps_the_same_public_listener_surface() -> None:
    actual = _profile_manifest("vpn-p0-self-steal.yml")
    expected = [_expected("xray", "tcp", 443), _expected("xray-fallback", "tcp", 2053)]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_p1_web_listener_surface_is_normal_http_and_https() -> None:
    actual = _profile_manifest("vpn-p1-web.yml")
    expected = [
        _expected("public-site-http", "tcp", 80),
        _expected("nginx-xhttp", "tcp", 443),
        # Subscription delivery co-located on the p1 web node (v1 default,
        # SUBSCRIPTION-HOST-SEPARATION.md) — the only non-web TCP listener.
        _expected("subscription-host", "tcp", 8444),
    ]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_p2_udp_listener_surface_has_no_public_tcp_service() -> None:
    actual = _profile_manifest("vpn-p2-udp.yml")
    expected = [_expected("hysteria", "udp", 443), _expected("amneziawg", "udp", 51820)]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_listener_contract_pre_tasks_run_during_tagged_deploys() -> None:
    play = yaml.safe_load((REPO_ROOT / "ansible" / "playbooks" / "site.yml").read_text())[0]
    required = {
        "Build effective public listener manifest",
        "Decode provider listener contract from rendered inventory",
        "Guard — provider edge and runtime listener contracts agree",
        "Guard — block public listener collisions before convergence",
    }
    tasks = {task["name"]: task for task in play["pre_tasks"] if task["name"] in required}
    assert set(tasks) == required
    assert all("always" in task.get("tags", []) for task in tasks.values())


@pytest.mark.parametrize(
    "case, expected_failure",
    [
        ("missing-secrets", "VPN_SECRETS_FILE is not set"),
        ("empty-allowlist", "allowed_ssh_cidrs is empty"),
        ("research", "RESEARCH-tier role(s)"),
        ("exception", "EXCEPTION-tier role(s)"),
        ("standard", None),
        ("approved-research", None),
    ],
)
def test_tagged_convergence_executes_source_preflight_guards(tmp_path, case, expected_failure):
    """Execute unchanged source guards, never the host-mutating site roles."""
    executable = shutil.which("ansible-playbook")
    assert executable, "ansible-playbook is required to exercise tag filtering"
    source = yaml.safe_load((REPO_ROOT / "ansible/playbooks/site.yml").read_text())[0]
    names = {
        "Ensure VPN_SECRETS_FILE was provided",
        "Ensure the SSH management-path allowlist is populated",
        "Load role tier manifest",
        "Guard — block RESEARCH-tier roles in a family deploy",
        "Guard — block unapproved EXCEPTION-tier roles",
    }
    guards = [task for task in source["pre_tasks"] if task["name"] in names]
    assert {task["name"] for task in guards} == names
    playbooks = tmp_path / "ansible/playbooks"
    playbooks.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "ansible/role-tiers.yml", playbooks.parent / "role-tiers.yml")
    variables = {"vpn": {}, "allowed_ssh_cidrs": ["203.0.113.1/32"]}
    if case == "empty-allowlist":
        variables["allowed_ssh_cidrs"] = []
    if case in {"research", "approved-research"}:
        variables["vpn"]["enable_split_hop_egress"] = True
    if case == "approved-research":
        variables["allow_research_roles"] = ["split-hop-egress"]
    if case == "exception":
        variables["vpn"]["enable_cascade_ingress"] = True
    play = {
        "name": "Exercise tagged source guards without deploying roles",
        "hosts": "localhost", "gather_facts": False, "become": False,
        "vars": variables, "pre_tasks": guards,
        "tasks": [{"name": "Convergence sentinel", "tags": ["p0"],
                   "ansible.builtin.debug": {"msg": "CONVERGENCE_REACHED"}}],
    }
    playbook = playbooks / "guards.yml"
    playbook.write_text(yaml.safe_dump([play], sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\n")
    env = {**os.environ, "ANSIBLE_CONFIG": str(config), "ANSIBLE_NOCOLOR": "1",
           "ANSIBLE_FORCE_COLOR": "0", "ANSIBLE_STDOUT_CALLBACK": "default",
           "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"),
           "VPN_SECRETS_FILE": "" if case == "missing-secrets" else "synthetic-test-input"}
    result = subprocess.run(
        [executable, "-i", "localhost,", "-c", "local", str(playbook), "--tags", "p0"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=40,
    )
    output = result.stdout + result.stderr
    if expected_failure:
        assert result.returncode != 0, output
        assert expected_failure in output
        assert "CONVERGENCE_REACHED" not in output
    else:
        assert result.returncode == 0, output
        assert "CONVERGENCE_REACHED" in output


def _run_listener_task(tmp_path, match, variables, protocol, port):
    """Run the unchanged verification task; only the external ss output is a fixture."""
    executable = shutil.which("ansible-playbook")
    assert executable, "real Ansible is required for listener verification regressions"
    source = yaml.safe_load((REPO_ROOT / "ansible/playbooks/verify.yml").read_text())[0]
    tasks = [task for task in source["tasks"]
             if match in task.get("ansible.builtin.shell", {}).get("cmd", "")]
    assert len(tasks) == 1, f"expected one production listener task for {match}"
    binary = tmp_path / "ss"
    trace = tmp_path / "ss-called"
    binary.write_text(
        f"#!{sys.executable}\nimport pathlib, sys\n"
        f"pathlib.Path({str(trace)!r}).write_text(' '.join(sys.argv[1:]))\n"
        f"if sys.argv[1:] == [{'-lnu' if protocol == 'udp' else '-lnt'!r}] and {port!r} is not None:\n"
        f"    print('LISTEN 0 128 0.0.0.0:{port} *:*')\n"
    )
    binary.chmod(0o755)
    return _run_verify_task_slice(tmp_path, tasks, variables), trace.exists()


def _run_verify_task_slice(tmp_path, tasks, variables):
    """Execute source tasks/conditions with external inspection supplied by the caller."""
    executable = shutil.which("ansible-playbook")
    assert executable, "real Ansible is required for verification regressions"
    playbook = tmp_path / "listeners.yml"
    playbook.write_text(yaml.safe_dump([{
        "name": "Exercise production listener verification without host calls",
        "hosts": "localhost", "gather_facts": False, "become": False,
        "vars": {**variables, "ansible_python_interpreter": sys.executable},
        "environment": {"PATH": str(tmp_path) + ":" + os.environ["PATH"]},
        "tasks": tasks,
    }], sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
    env.update(ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local"))
    result = subprocess.run(
        [executable, "-i", "localhost,", "-c", "local", str(playbook)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=40,
    )
    return result


@pytest.mark.parametrize("observed_port, success", [(7443, True), (443, False)])
def test_verify_hysteria_uses_configured_udp_port(tmp_path, observed_port, success):
    result, inspected = _run_listener_task(
        tmp_path, "ss -lnu", {"vpn": {"enable_hysteria": True}, "hysteria_port": 7443},
        "udp", observed_port,
    )
    assert inspected, result.stdout + result.stderr
    assert (result.returncode == 0) == success, result.stdout + result.stderr


@pytest.mark.parametrize("fallback, configured_port, observed_port, success", [
    ("xray", 2443, 2443, True),
    ("xray", 2443, 443, False),
    ("nginx_xhttp", 2444, 2444, True),
    ("nginx_xhttp", 2444, 8443, False),
])
def test_verify_requires_enabled_fallback_listener(tmp_path, fallback, configured_port, observed_port, success):
    variables = {"vpn": {"enable_xray_reality": True, "enable_nginx_xhttp": True},
                 "xray": {}, "nginx_xhttp": {"fallback_enabled": True},
                 fallback + "_fallback_port": configured_port}
    result, inspected = _run_listener_task(tmp_path, fallback + "_fallback_port", variables, "tcp", observed_port)
    assert inspected, result.stdout + result.stderr
    assert (result.returncode == 0) == success, result.stdout + result.stderr


@pytest.mark.parametrize("match", ["ss -lnu", "xray_fallback_port", "nginx_xhttp_fallback_port"])
def test_verify_listener_tasks_skip_subscription_only_hosts(tmp_path, match):
    variables = {"vpn_subscription_only": True,
                 "vpn": {"enable_hysteria": True, "enable_xray_reality": True, "enable_nginx_xhttp": True},
                 "xray": {}, "xray_fallback_port": 2443, "nginx_xhttp": {"fallback_enabled": True}}
    result, inspected = _run_listener_task(tmp_path, match, variables, "tcp", None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not inspected, result.stdout + result.stderr


@pytest.mark.parametrize("match, variables", [
    ("ss -lnu", {"vpn": {"enable_hysteria": False}}),
    ("ss -lnu", {"vpn": {}}),
    ("xray_fallback_port", {"vpn": {"enable_xray_reality": False}, "xray_fallback_port": 2443}),
    ("xray_fallback_port", {"vpn": {}, "xray": {"cohorts": [{"name": "explicit", "port": 443}]},
                            "xray_fallback_port": 2443}),
    ("xray_fallback_port", {"vpn": {}, "xray_fallback_port": 0}),
    ("xray_fallback_port", {"vpn": {}, "xray_fallback_port": 2443, "xray_port": 2443}),
    ("xray_fallback_port", {"vpn": {}}),
    ("nginx_xhttp_fallback_port", {"vpn": {"enable_nginx_xhttp": False},
                                   "nginx_xhttp": {"fallback_enabled": True}}),
    ("nginx_xhttp_fallback_port", {"vpn": {}, "nginx_xhttp": {"fallback_enabled": False}}),
    ("nginx_xhttp_fallback_port", {"vpn": {}, "nginx_xhttp": {}}),
])
def test_verify_does_not_require_undeployed_listener(tmp_path, match, variables):
    result, inspected = _run_listener_task(tmp_path, match, variables, "tcp", None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not inspected, result.stdout + result.stderr


@pytest.mark.parametrize("match, variables, protocol, port", [
    ("ss -lnu", {"vpn": {"enable_hysteria": True}}, "udp", 443),
    ("nginx_xhttp_fallback_port", {"vpn": {"enable_nginx_xhttp": True},
                                   "nginx_xhttp": {"fallback_enabled": True}}, "tcp", 2083),
])
def test_verify_listener_defaults_match_rendered_configuration(tmp_path, match, variables, protocol, port):
    result, inspected = _run_listener_task(tmp_path, match, variables, protocol, port)
    assert inspected, result.stdout + result.stderr
    assert result.returncode == 0, result.stdout + result.stderr


HOSTCLASS_TASKS = (
    'Xray TCP listener active', 'nginx-xhttp public TCP listener active', 'nginx -t',
    'P1 public hostname resolves to its service address', 'P1 public IPv6 service address is available',
    'P1 public hostname exposes its IPv6 service address', 'Hysteria service active',
    'Snell configuration is valid', 'Snell service active', 'Snell TCP listeners active',
    'AmneziaWG interface up',
)


def _run_hostclass_task_slice(tmp_path, names, *, subscription_only, enabled=True, bad_sysctl=False):
    source = yaml.safe_load((REPO_ROOT / 'ansible/playbooks/verify.yml').read_text())[0]
    tasks = [task for task in source['tasks'] if task['name'] in names]
    assert {task['name'] for task in tasks} == set(names)
    trace = tmp_path / 'inspection-calls.jsonl'
    program = rf"""#!{sys.executable}
import json
import pathlib
import sys
name = pathlib.Path(sys.argv[0]).name
with pathlib.Path({str(trace)!r}).open('a') as stream:
    stream.write(json.dumps({{'name': name, 'argv': sys.argv[1:]}}) + '\n')
if name == 'ss':
    for port in (443, 8443, 4443):
        print(f'LISTEN 0 128 0.0.0.0:{{port}} *:*')
elif name == 'systemctl':
    print('active')
elif name == 'getent':
    print('192.0.2.7 STREAM fixture.invalid')
elif name == 'sshd':
    print('passwordauthentication no\npermitrootlogin no\nkbdinteractiveauthentication no\npubkeyauthentication yes\nx11forwarding no\nallowtcpforwarding no')
elif name == 'sysctl':
    values = {{'fs.protected_hardlinks': '1', 'fs.protected_symlinks': '1',
               'kernel.randomize_va_space': '2', 'kernel.kptr_restrict': '2',
               'kernel.yama.ptrace_scope': '2', 'net.ipv4.conf.all.accept_redirects': '0'}}
    print('wrong' if {bad_sysctl!r} else values[sys.argv[-1]])
elif name not in ('nginx', 'python3', 'sing-box-snell', 'awg', 'nft'):
    raise AssertionError(name)
"""
    for name in ('ss', 'systemctl', 'getent', 'nginx', 'python3', 'sing-box-snell', 'awg', 'nft', 'sshd', 'sysctl'):
        binary = tmp_path / name
        binary.write_text(program)
        binary.chmod(0o755)
    # Relocate only the absolute external binary and bootstrap marker. All
    # original task conditions, assertion expressions and command arguments stay.
    for task in tasks:
        command = task.get('ansible.builtin.command', {})
        if command.get('cmd', '').startswith('/usr/local/bin/sing-box-snell '):
            command['cmd'] = command['cmd'].replace('/usr/local/bin/sing-box-snell', str(tmp_path / 'sing-box-snell'), 1)
        if task['name'] == 'Cloud-init bootstrap marker exists':
            marker = tmp_path / 'bootstrap.done'
            marker.touch()
            task['ansible.builtin.stat']['path'] = str(marker)
    variables = {
        'vpn_subscription_only': subscription_only,
        'vpn': {key: enabled for key in ('enable_xray_reality', 'enable_nginx_xhttp',
                                        'enable_hysteria', 'enable_snell', 'enable_amneziawg')},
        'nginx_xhttp': {'server_name': 'fixture.invalid'}, 'vpn_service_address': '192.0.2.7',
        'server_ipv6': '2001:db8::7',
        'snell': {'variants': [{'id': 'v4-stream', 'listen_port': 4443}]},
        'security_controls': {'ssh_strict': False},
    }
    result = _run_verify_task_slice(tmp_path, tasks, variables)
    calls = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
    return result, calls


@pytest.mark.parametrize('name', HOSTCLASS_TASKS)
def test_verify_hostclass_skips_each_transport_inspection(tmp_path, name):
    result, calls = _run_hostclass_task_slice(tmp_path, [name], subscription_only=True)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert not calls, output
    assert 'skipping: [localhost]' in output, output


def test_verify_hostclass_enabled_transports_still_inspect_state(tmp_path):
    result, calls = _run_hostclass_task_slice(tmp_path, HOSTCLASS_TASKS, subscription_only=False)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert 'skipping: [localhost]' not in output, output
    assert [call['name'] for call in calls] == [
        'ss', 'ss', 'nginx', 'getent', 'python3', 'systemctl', 'sing-box-snell', 'systemctl', 'ss', 'awg',
    ]


def test_verify_hostclass_disabled_transports_do_not_inspect_state(tmp_path):
    result, calls = _run_hostclass_task_slice(tmp_path, HOSTCLASS_TASKS, subscription_only=False, enabled=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not calls, result.stdout + result.stderr


@pytest.mark.parametrize('bad_sysctl', (False, True))
def test_verify_hostclass_preserves_shared_hardening_checks(tmp_path, bad_sysctl):
    names = ('Cloud-init bootstrap marker exists', 'nftables config syntax valid',
             'SSH password auth disabled', 'SSH effective hardening is applied', 'Sysctl hardening values are applied')
    result, calls = _run_hostclass_task_slice(tmp_path, names, subscription_only=True, bad_sysctl=bad_sysctl)
    output = result.stdout + result.stderr
    assert (result.returncode == 0) is (not bad_sysctl), output
    assert 'skipping: [localhost]' not in output, output
    assert [call['name'] for call in calls] == ['nft', 'sshd'] + ['sysctl'] * 6
