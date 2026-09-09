"""Bootstrap input and transport boundaries; no provider or guest mutation."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/bootstrap-tailnet.py"


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("bootstrap_tailnet", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path.resolve()
    key = root / "identity"
    generated = subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        capture_output=True, timeout=10, check=False,
    )
    assert generated.returncode == 0
    public = key.with_suffix(".pub").read_text().split()
    known_hosts = root / "known_hosts"
    known_hosts.write_text(f"[192.0.2.10]:2222 {public[0]} {public[1]}\n")
    inventory = root / "inventory.ini"
    inventory.write_text(
        "[vpn]\nnode-one ansible_host=192.0.2.10 ansible_user=deploy ansible_port=2222\n"
        f"[vpn:vars]\nansible_ssh_private_key_file={key}\n"
    )
    config = {
        "schema_version": 1,
        "environment": "prod",
        "provider": "upcloud",
        "inventory_alias": "node-one",
        "public_address": "192.0.2.10",
        "ssh_port": 2222,
        "host_key_sha256": hashlib.sha256(base64.b64decode(public[1])).hexdigest(),
        "public_sources": ["198.51.100.10"],
        "approved_sources": ["100.64.0.10", "fd7a:115c:a1e0::10"],
        "source_revision": "a" * 40,
        "deployable_digest": "b" * 64,
        "known_hosts": str(known_hosts),
        "cleanup_manifest": None,
        "output": str(root / "handoff.json"),
    }
    path = root / "config.json"
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    return root, inventory, path, config


def load(controller, inputs, monkeypatch, **changes):
    root, inventory, path, config = inputs
    config.update(changes)
    path.write_text(json.dumps(config))
    directory = root / "frozen"
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(controller, "INVENTORY", inventory)
    monkeypatch.setattr(controller.deploy, "source_identity", lambda *a, **kw: {
        "DEPLOY_SOURCE_REVISION": "a" * 40, "DEPLOYABLE_SOURCE_DIGEST": "b" * 64,
    })
    return controller.load_inputs({
        "BOOTSTRAP_TARGET": "node-one", "TAILNET_BOOTSTRAP_CONFIG": str(path),
        "PATH": os.environ["PATH"], "HOME": str(root),
    }, directory)


def test_fresh_node_inputs_freeze_public_transport_and_one_host_key(controller, inputs, monkeypatch):
    selected = load(controller, inputs, monkeypatch)
    assert selected.host["transport"] == selected.host["address"] == "192.0.2.10"
    assert selected.host["key"] != str(inputs[0] / "identity")
    command = selected.ssh
    for option in ("ProxyCommand=none", "ControlMaster=no", "IdentityAgent=none",
                   "StrictHostKeyChecking=yes", "HostKeyAlgorithms=ssh-ed25519"):
        assert option in command
    assert "198.51.100.10" not in " ".join(command)
    assert selected.config["approved_sources"] == inputs[3]["approved_sources"]
    assert not Path(selected.config["output"]).exists()


def test_installer_real_ansible_preserves_local_delegation(controller, inputs, monkeypatch):
    """Exercise Ansible variable precedence, not package or guest acceptance."""
    selected = load(controller, inputs, monkeypatch)
    key = selected.directory / "identity with spaces"
    key.write_bytes(Path(selected.host["key"]).read_bytes())
    key.chmod(0o600)
    host = {**selected.host, "key": str(key)}
    ssh = controller.inspection.ssh_command(host, selected.known_hosts)
    ssh[1:1] = ["-o", "HostKeyAlgorithms=ssh-ed25519"]
    project = inputs[0] / "project"
    playbooks = project / "ansible/playbooks"
    playbooks.mkdir(parents=True)
    (project / "ansible/ansible.cfg").write_text("[defaults]\n")
    transport = controller.deploy.transport_variables(host, ssh)
    play = [{"hosts": "vpn", "gather_facts": False, "vars": {"expected_transport": transport},
             "tasks": [
                 {"name": "Keep every pinned connection value on the selected node",
                  "ansible.builtin.assert": {"that": [
                      "hostvars[inventory_hostname][item.key] | string == item.value | string"]},
                  "loop": "{{ expected_transport | dict2items }}"},
                 {"name": "Run the real source validator on the controller",
                  "ansible.builtin.command": {
                      "argv": [sys.executable, str(ROOT / "scripts/tailnet-validate-sources.py")],
                      "stdin": "{{ tailnet_management.approved_sources | to_json }}"},
                  "delegate_to": "localhost", "become": False, "changed_when": False}]}]
    (playbooks / "bootstrap-tailnet.yml").write_text(json.dumps(play))
    bin_dir = inputs[0] / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "ansible-playbook"
    # Match the existing real-Ansible deploy tests: accidental SSH/sudo must
    # fail before any network or privilege operation, rather than be mocked OK.
    executable.write_text(f"""#!{sys.executable}
import runpy
from ansible.plugins.connection.ssh import Connection
from ansible.plugins.become.sudo import BecomeModule
def forbidden(*args, **kwargs):
    raise AssertionError('local delegation attempted SSH or sudo')
Connection._run = forbidden
BecomeModule.build_become_command = forbidden
runpy.run_module('ansible.cli.playbook', run_name='__main__')
""")
    executable.chmod(0o700)
    environment = controller.deploy.execution_environment(project, selected.directory)
    environment.update(PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
                       HOME=str(inputs[0]), LANG="en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8",
                       LC_ALL="en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8")
    selected = selected._replace(host=host, ssh=ssh, environment=environment)
    monkeypatch.setattr(controller, "ROOT", project)
    monkeypatch.setattr(controller, "_installed", lambda *_: "ready")

    controller._install(selected)


@pytest.mark.parametrize("changes", [
    {"inventory_alias": "other"}, {"public_address": "192.0.2.11"},
    {"ssh_port": True}, {"source_revision": "c" * 40},
    {"host_key_sha256": "0" * 64}, {"public_sources": ["0.0.0.0/0"]},
    {"approved_sources": ["100.64.0.10/32"]}, {"extra": "unknown"},
    {"environment": "ci-staging-test", "cleanup_manifest": None},
])
def test_invalid_inputs_refuse_before_guest_commands(controller, inputs, monkeypatch, changes):
    with pytest.raises(controller.BootstrapError):
        load(controller, inputs, monkeypatch, **changes)
    assert not (inputs[0] / "handoff.json").exists()


def test_existing_output_is_not_overwritten(controller, inputs, monkeypatch):
    output = inputs[0] / "handoff.json"
    output.write_text("user-owned")
    output.chmod(0o600)
    with pytest.raises(controller.BootstrapError):
        load(controller, inputs, monkeypatch)
    assert output.read_text() == "user-owned"


@pytest.mark.parametrize("field", ["ANSIBLE_LIMIT", "TAILNET_BOOTSTRAP_CONFIG", "TAILSCALE_AUTH_KEY"])
def test_make_never_expands_bootstrap_input(controller, tmp_path, field):
    marker = tmp_path / "expanded"
    result = subprocess.run(
        ["make", "bootstrap-tailnet", f"{field}=$(shell touch {marker})"],
        cwd=ROOT, env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]},
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode != 0
    assert not marker.exists()


def capability(controller, selected, *, status="pending"):
    nonce = "d" * 32
    return {"status": status, "changed": status == "pending", "nonce": nonce,
            "generation": controller.tailnet.RECOVERY_GENERATION,
            "binding_sha256": hashlib.sha256(controller.tailnet._canonical_bytes(controller._binding(selected))).hexdigest(),
            "lease": {"boot_id": "12345678-1234-4234-9234-123456789abc", "started_ms": 1000, "deadline_ms": 301000},
            "node": {"id": "node-id", "hostname": "vpn-enroll-" + nonce,
                     "ipv4": "100.64.1.9", "ipv6": "fd7a:115c:a1e0::9"}}


def execution_fixture(controller, inputs, monkeypatch):
    import bootstrap_readiness
    selected = load(controller, inputs, monkeypatch)
    pending = capability(controller, selected)
    contexts = [
        {"user": "deploy", "host": source, "addr": source, "laddr": address, "lport": 2222}
        for source, address in (("198.51.100.10", "192.0.2.10"), ("100.64.0.10", "100.64.1.9"))
    ]
    monkeypatch.setattr(bootstrap_readiness, "wait_for_bootstrap", lambda *a, **kw: None)
    monkeypatch.setattr(controller.deploy, "require_recovery_foundation", lambda *a, **kw: None)
    monkeypatch.setattr(controller, "_installed", lambda *a: "ready")
    monkeypatch.setattr(controller, "_probe", lambda *a, **kw: contexts[0])
    monkeypatch.setattr(controller, "_proofs", lambda *a: contexts)
    return selected, pending, contexts


def test_bootstrap_publishes_only_after_external_commit(controller, inputs, monkeypatch):
    selected, pending, contexts = execution_fixture(controller, inputs, monkeypatch)
    actions = []
    def rpc(_inputs, action, **values):
        actions.append(action)
        if action == "status": return {"status": "idle"}
        if action == "enroll":
            assert values["auth_key"] == "tskey-auth-fixture_key"
            return pending
        assert action == "confirm" and values["contexts"] == contexts
        assert not Path(selected.config["output"]).exists()
        return capability(controller, selected, status="configured")
    monkeypatch.setattr(controller, "_rpc", rpc)
    result = controller.run(selected, "tskey-auth-fixture_key")
    assert result["status"] == "configured" and result["vpn_acceptance"] == "not-performed"
    assert actions == ["status", "enroll", "confirm"]
    output = Path(selected.config["output"])
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["contexts"] == contexts
    assert "tskey-auth" not in output.read_text()


def test_lost_confirm_reply_reconciles_without_logout(controller, inputs, monkeypatch):
    selected, pending, _ = execution_fixture(controller, inputs, monkeypatch)
    actions = []
    def rpc(_inputs, action, **values):
        actions.append(action)
        if action == "status":
            return {"status": "idle"} if len(actions) == 1 else capability(controller, selected, status="configured")
        if action == "enroll": return pending
        if action == "confirm": raise controller.BootstrapError("lost-reply")
        pytest.fail("confirmed identity must not be rolled back")
    monkeypatch.setattr(controller, "_rpc", rpc)
    assert controller.run(selected, "tskey-auth-fixture_key")["status"] == "configured"
    assert actions == ["status", "enroll", "confirm", "status"]


def test_failed_path_proof_requests_rollback_and_publishes_nothing(controller, inputs, monkeypatch):
    selected, pending, _ = execution_fixture(controller, inputs, monkeypatch)
    actions = []
    def rpc(_inputs, action, **values):
        actions.append(action)
        if action == "status": return {"status": "idle"} if len(actions) == 1 else pending
        if action == "enroll": return pending
        assert action == "rollback" and values["capability"] == pending
        return {"status": "rolled_back"}
    monkeypatch.setattr(controller, "_rpc", rpc)
    def fail(*args): raise controller.BootstrapError("path-failed")
    monkeypatch.setattr(controller, "_proofs", fail)
    with pytest.raises(controller.BootstrapError, match="path-failed"):
        controller.run(selected, "tskey-auth-fixture_key")
    assert actions == ["status", "enroll", "status", "rollback"]
    assert not Path(selected.config["output"]).exists()


def test_handoff_publication_never_replaces_another_file(controller, inputs, monkeypatch):
    selected, _, contexts = execution_fixture(controller, inputs, monkeypatch)
    output = Path(selected.config["output"])
    output.write_text("another writer")
    with pytest.raises(FileExistsError):
        controller._publish(selected, capability(controller, selected, status="configured"), contexts, selected.output_parent_identity)
    assert output.read_text() == "another writer"
    assert not list(output.parent.glob(".bootstrap-*"))


def test_probe_decodes_kernel_ipv4_and_ipv6_words(controller):
    probe = controller.module("tailnet_bootstrap_probe")
    assert probe.decode_endpoint("0100007F:0016") == ("127.0.0.1", 22)
    assert probe.decode_endpoint("00000000000000000000000001000000:0016") == ("::1", 22)


@pytest.mark.parametrize("reply_kind,flags,reply_sequence,error", [(3, 0, 1, False), (2, 0, 1, True), (3, 0x10, 1, True), (3, 0, 2, True)])
def test_empty_netfilter_dump_requires_complete_kernel_reply(controller, monkeypatch, reply_kind, flags, reply_sequence, error):
    import struct
    probe = controller.module("tailnet_bootstrap_probe")
    requests = []
    class Channel:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def settimeout(self, value): assert value == 3
        def bind(self, address): assert address == (0, 0)
        def getsockname(self): return 1234, 0
        def sendto(self, payload, address): requests.append(payload)
        def recvmsg(self, limit):
            return struct.pack("=IHHII", 20, reply_kind, flags, reply_sequence, 1234) + bytes(4), [], 0, (0, 0)
    monkeypatch.setattr(probe.os, "urandom", lambda n: bytes([1, 0, 0, 0]))
    monkeypatch.setattr(probe.socket, "AF_NETLINK", 16, raising=False)
    monkeypatch.setattr(probe.socket, "socket", lambda *args: Channel())
    if error:
        with pytest.raises(probe.ProbeError): probe.nftables_empty()
    else:
        assert probe.nftables_empty() is True
    assert struct.unpack_from("=IHHII", requests[0])[1:3] == (0xA01, 0x301)


@pytest.mark.parametrize("extra", [None, {"table": {"family": "ip", "name": "foreign"}},
    {"chain": {"family": "ip", "table": "filter", "name": "INPUT"}}])
def test_preinstall_inert_baseline_uses_the_complete_ruleset(controller, monkeypatch, extra):
    import tailnet_bootstrap_probe as probe
    entries = [{"table": {"family": family, "name": name, "handle": number}}
               for number, (family, name) in enumerate(
                   [(family, name) for family in ("ip", "ip6") for name in ("filter", "nat")], 1)]
    if extra:
        entries.append(extra)
    monkeypatch.setattr(probe, "nftables_empty", lambda: False)
    calls = []
    def command(argv):
        calls.append(argv)
        return json.dumps({"nftables": [{"metainfo": {"version": "fixture"}}, *entries]}).encode()
    monkeypatch.setattr(probe, "command", command)
    assert probe.empty_firewall_baseline() is (extra is None)
    assert calls == [["nft", "-j", "list", "ruleset"]]


def test_preinstall_truly_empty_kernel_needs_no_nft_binary(controller, monkeypatch):
    import tailnet_bootstrap_probe as probe
    monkeypatch.setattr(probe, "nftables_empty", lambda: True)
    monkeypatch.setattr(probe, "command", lambda _: pytest.fail("unexpected subprocess"))
    assert probe.empty_firewall_baseline() is True


@pytest.mark.parametrize("address,expected", [
    ("192.0.2.10", "192.0.2.10"),
    ("fd7a:115c:a1e0::10", "fd7a:115c:a1e0::10"),
    ("::ffff:192.0.2.10", "192.0.2.10"),
])
def test_proc_socket_identity_normalizes_dual_stack_ipv4(controller, address, expected):
    import ipaddress
    import struct
    import tailnet_bootstrap_probe as probe
    packed = ipaddress.ip_address(address).packed
    rendered = "".join(f"{struct.unpack('=I', packed[offset:offset + 4])[0]:08X}" for offset in range(0, len(packed), 4))
    assert probe.decode_endpoint(rendered + ":08AE") == (expected, 2222)


@pytest.mark.parametrize("fault", [None, "foreign-table", "foreign-chain", "runtime-rule", "fragment", "service"])
def test_owned_preinstall_rejects_runtime_drift_before_installation(controller, monkeypatch, fault):
    import tailnet_bootstrap_probe as probe
    binding = {"ssh_port": 22}
    main = (b"#!/usr/sbin/nft -f\n# Managed by Ansible role `firewall`.\n"
            b'table inet filter {\ninclude "/etc/nftables.d/vpn-tailnet-ssh-sets.nft"\n'
            b'chain input { type filter hook input priority 0; policy drop;\n'
            b'iifname "tailscale0" tcp dport 22 ip saddr @vpn_tailnet_ssh_v4 accept\n'
            b'iifname "tailscale0" tcp dport 22 ip6 saddr @vpn_tailnet_ssh_v6 accept\n'
            b'iifname "tailscale0" tcp dport 22 drop\n}\n}\n')
    fragment = controller.tailnet.canonical_sources_fragment(["100.64.0.10"]).encode()
    if fault == "fragment":
        fragment += b'include "/foreign.nft"\n'
    monkeypatch.setattr(probe, "read", lambda path, *args: main if str(path).endswith('nftables.conf') else fragment)
    canonical = [{"table": {"family": "inet", "name": "filter"}}]
    extra = {
        "foreign-table": {"table": {"family": "inet", "name": "foreign"}},
        "foreign-chain": {"chain": {"family": "inet", "table": "filter", "name": "foreign"}},
        "runtime-rule": {"rule": {"family": "inet", "table": "filter", "chain": "input", "expr": [{"accept": None}]}},
    }.get(fault)
    calls = []
    def command(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[0] == "systemctl":
            return b"ActiveState=failed\nUnitFileState=enabled\n" if fault == "service" else b"ActiveState=active\nUnitFileState=enabled\n"
        if argv[0] == "nft":
            return json.dumps({"nftables": canonical + ([extra] if extra else [])}).encode()
        assert argv[0] == "unshare" and "--net" in argv
        assert fragment in kwargs["input_data"] and b"include" not in kwargs["input_data"]
        return json.dumps({"nftables": canonical}).encode()
    monkeypatch.setattr(probe, "command", command)
    parser = controller.module("tailnet-network-guest").canonical_fragment
    if fault:
        with pytest.raises(probe.ProbeError):
            probe.validate_owned_firewall(binding, fragment_parser=parser)
    else:
        probe.validate_owned_firewall(binding, fragment_parser=parser)
        assert [argv[0] for argv, _ in calls] == ["systemctl", "nft", "unshare"]
    assert all(argv[0] in {"systemctl", "nft", "unshare"} for argv, _ in calls)


def test_preinstall_payload_loads_shared_parser_without_guest_install(controller, inputs, monkeypatch):
    import ast
    import sys
    selected = load(controller, inputs, monkeypatch)
    def remote(_inputs, _host, _command, payload):
        program = ast.parse(payload)
        # Inspect the source payload without invoking the remote host probe.
        program.body.pop()
        prefix = ast.unparse(program).encode()
        fragment = controller.tailnet.canonical_sources_fragment(["100.64.0.10"]).encode()
        result = subprocess.run([sys.executable, "-I", "-B", "-S", "-"],
            input=prefix + b"\nassert fragment_parser(" + repr(fragment).encode() + b")\n",
            capture_output=True, timeout=10, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return {"user": "deploy", "host": "198.51.100.10", "addr": "198.51.100.10", "laddr": "192.0.2.10", "lport": 2222}
    monkeypatch.setattr(controller, "_remote", remote)
    assert controller._probe(selected, selected.host, preinstall=True)["lport"] == 2222


def test_input_change_during_install_refuses_before_enrollment(controller, inputs, monkeypatch):
    selected, pending, _ = execution_fixture(controller, inputs, monkeypatch)
    monkeypatch.setattr(controller, "_installed", lambda *_: "absent")
    monkeypatch.setattr(controller, "_install", lambda *_: inputs[2].write_text("changed during installation"))
    actions = []
    def rpc(_inputs, action, **_values):
        actions.append(action)
        return pending
    monkeypatch.setattr(controller, "_rpc", rpc)
    with pytest.raises(controller.deploy.DeployError):
        controller.run(selected, "tskey-auth-fixture_key")
    assert actions == []
    assert not Path(selected.config["output"]).exists()


def test_preinstall_refusal_never_installs_or_enrolls(controller, inputs, monkeypatch):
    selected, _, _ = execution_fixture(controller, inputs, monkeypatch)
    monkeypatch.setattr(controller, "_installed", lambda *_: "absent")
    def refuse(*args, **kwargs):
        assert kwargs["preinstall"] is True
        raise controller.BootstrapError("bootstrap-remote-refused")
    monkeypatch.setattr(controller, "_probe", refuse)
    monkeypatch.setattr(controller, "_install", lambda *_: pytest.fail("installation after failed preflight"))
    monkeypatch.setattr(controller, "_rpc", lambda *a, **kw: pytest.fail("enrollment after failed preflight"))
    with pytest.raises(controller.BootstrapError, match="bootstrap-remote-refused"):
        controller.run(selected, "tskey-auth-fixture_key")
    assert not Path(selected.config["output"]).exists()


@pytest.mark.parametrize("already_configured", [False, True])
def test_source_change_during_proofs_refuses_commit_and_handoff(controller, inputs, monkeypatch, already_configured):
    selected, pending, contexts = execution_fixture(controller, inputs, monkeypatch)
    actions = []
    def proofs(*_):
        monkeypatch.setattr(controller.deploy, "source_identity", lambda *a, **kw: {
            "DEPLOY_SOURCE_REVISION": "c" * 40, "DEPLOYABLE_SOURCE_DIGEST": "b" * 64,
        })
        return contexts
    def rpc(_inputs, action, **_values):
        actions.append(action)
        if action == "status":
            if already_configured:
                return capability(controller, selected, status="configured")
            return {"status": "idle"} if len(actions) == 1 else pending
        if action == "enroll": return pending
        if action == "rollback": return {"status": "rolled_back"}
        return capability(controller, selected, status="configured")
    monkeypatch.setattr(controller, "_proofs", proofs)
    monkeypatch.setattr(controller, "_rpc", rpc)
    with pytest.raises(controller.BootstrapError, match="bootstrap-source-changed"):
        controller.run(selected, "tskey-auth-fixture_key")
    assert "confirm" not in actions
    assert ("rollback" in actions) is (not already_configured)
    assert not Path(selected.config["output"]).exists()
