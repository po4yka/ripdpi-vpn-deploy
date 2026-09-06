"""Onboarding orchestration fixtures; fake tools/SSH are not live VPN proof."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pty
import select
import stat
import sys
import tempfile
import termios

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def receiver_root():
    # Production refuses writable ancestors, including sticky /tmp. Keep the
    # real receiver checks intact by placing its fixture beneath a safe home.
    parent = Path.home()
    assert parent.is_absolute(), "receiver fixture requires an absolute home"
    for ancestor in (parent, *parent.parents):
        info = ancestor.lstat()
        assert (stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.geteuid())
                and not info.st_mode & 0o022), "receiver fixture requires owner-controlled ancestors"
    with tempfile.TemporaryDirectory(prefix=".vpn-liveness-receiver-", dir=parent) as directory:
        path = Path(directory)
        info = path.lstat()
        assert info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700
        yield path / "root"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    module = load(ROOT / "scripts/install_liveness_sentinel.py", "installer")
    fixture = load(ROOT / "tests/unit/test_liveness_profiles.py", "profile_fixture")
    values = fixture.inputs()
    for document in (values["standard_doc"], values["ripdpi_doc"]):
        for outbound in document["outbounds"]:
            if outbound.get("tag", "").startswith(("p0-reality-", "p1-xhttp-", "p2-hysteria2-")):
                outbound["server"] = "192.0.2.3"
    config = {"schema_version": 2, "probe_url": "https://192.0.2.9/health", "expected_status": 204,
              "expected_runtime": {"sing_box": "1.14.0", "xray": "26.3.27", "awg": "1.0.0", "awg_toolchain": "d" * 64},
              "policies": [{"id": "fullstack", "required_profiles": values["required_profiles"], "min_failed_vantages": 1}],
              "sentinels": [{"id": "probe-a", "ssh_target": "sentinel-a", "ssh_transport_host": "sentinel-direct",
                             "ssh_host_key_alias": "sentinel-a", "policy": "fullstack", "vantage": "external",
                             "target": {"inventory_alias": "vpn-p2-fixture", "public_service_address_sha256": hashlib.sha256(b"192.0.2.3").hexdigest(),
                                        "deployable_digest": "f" * 64, "applied_at": 1_700_000_000},
                             "awg_target": values["awg_binding"]}]}
    path = tmp_path / "liveness.yaml"
    path.write_text(yaml.safe_dump(config))
    path.chmod(0o600)
    registry = tmp_path / "registry.json"
    calls, bundles, plaintexts = [], [], []
    state = {"receipt": None, "parser_failure": False, "lost_launch": False, "unknown": False}
    environment = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "HOSTS": "upcloud:probe,scaleway:probe,vultr:probe",
                   "COHORTS": "p0,p1-web,p2-udp", "SOPS_FILE": str(tmp_path / "encrypted.yaml")}

    def fake_run(command, *, environment=None, input_bytes=b"", timeout=30, **_kwargs):
        calls.append((list(command), dict(environment or {}), input_bytes))
        name = Path(command[0]).name
        if name == "audit-log.sh":
            return b""
        if name == "decrypt-secrets.sh":
            destination = Path(environment["SECRETS_FILE"])
            assert destination.parent.stat().st_mode & 0o777 == 0o700
            destination.write_text(yaml.safe_dump(values["secrets_doc"]))
            destination.chmod(0o600)
            plaintexts.append(destination)
            return b"decrypted\n"
        if name == "emit-singbox.sh":
            assert environment["VPN_SECRETS_FILE"] == str(plaintexts[-1])
            doc = values["ripdpi_doc"] if command[-1] == "ripdpi" else values["standard_doc"]
            return json.dumps(doc).encode()
        if name == "terraform-env.sh":
            assert environment["PROVIDER"] == "vultr" and environment["ENV"] == "probe"
            assert command[1:] == ["output", "-raw", "server_ipv4"]
            return b"192.0.2.3"
        if name in ("awg", "wg"):
            assert command[1:] == ["pubkey"]
            return (values["derive_public_key"](input_bytes.decode().strip()) + "\n").encode()
        if name in ("sing-box", "xray"):
            if command[1] == "version":
                return ("Xray 26.3.27\n" if name == "xray" else "sing-box version 1.14.0\n").encode()
            if state["parser_failure"]:
                raise module.InstallError("fixture-parser-failed")
            assert Path(command[-1]).stat().st_mode & 0o777 == 0o600
            return b""
        if name == "ssh":
            if command[-1] == "id -un":
                return b"probe\n"
            if command[-1] == "sudo -n true":
                return b""
            if input_bytes:
                bundle = json.loads(input_bytes)
                bundles.append(bundle)
                metadata = json.loads(base64.b64decode(bundle["files"]["metadata.json"]))
                state["receipt"] = {"generation_id": bundle["generation_id"], "status": "committed",
                                    "runner_sha256": metadata["provenance"]["runner_sha256"], "provenance": metadata["provenance"],
                                    "target_identity": metadata["target_identity"]}
                if state["lost_launch"]:
                    raise module.InstallError("fixture-ssh-lost")
                return b'{"status":"queued"}'
            if state["unknown"]:
                raise module.InstallError("fixture-unknown")
            if state["receipt"] is None:
                return b'{"state":"uncommitted"}'
            return json.dumps({"state": "committed", "receipt": state["receipt"]}).encode()
        raise AssertionError(f"unexpected fixture command {command}")

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_source_identity", lambda _repo: ("a" * 40, b"# runner fixture\n", b"# engine fixture\n"))
    monkeypatch.setattr(module.shutil, "which", lambda name, **_kwargs: name)
    monkeypatch.setattr(module, "RECEIPT_TIMEOUT", 0)

    def install():
        path.write_text(yaml.safe_dump(config))
        return module.install(path, "probe-a", "sentinel", registry, read_awg_stdin=True,
                              stdin=io.StringIO(values["private_key"] + "\n"), environment=environment)
    return locals()


def test_four_profiles_use_one_decrypt_and_receipt_before_assignment(setup):
    s = setup
    result = s["install"]()
    calls, bundle = s["calls"], s["bundles"][0]
    assert result["status"] == "committed"
    assert sum(Path(c[0][0]).name == "decrypt-secrets.sh" for c in calls) == 1
    assert [c[0][-1] for c in calls if Path(c[0][0]).name == "emit-singbox.sh"] == ["sing-box", "ripdpi"]
    assert not any(p.exists() for p in s["plaintexts"])
    assert set(bundle["files"]) == {"runner.py", "config.json", "metadata.json", "profiles/sing-box.json", "profiles/xray.json", "profiles/awg.conf"}
    contents = b"\n".join(base64.b64decode(v) for v in bundle["files"].values())
    assert s["values"]["secrets_doc"]["amneziawg_secrets"]["server_private_key"].encode() not in contents
    assert b"client_registry" not in contents
    config = json.loads(base64.b64decode(bundle["files"]["config.json"]))
    assert config["xray"]["config"].endswith("/profiles/xray.json")
    assert config["expected_runtime"] == s["config"]["expected_runtime"]
    registry = json.loads(s["registry"].read_text())
    assert registry["sentinels"]["probe-a"]["generation_id"] == result["generation_id"]
    assert s["registry"].stat().st_mode & 0o777 == 0o600
    for command, environment, _stdin in calls:
        exposed = json.dumps([command, environment])
        assert s["values"]["private_key"] not in exposed
        assert s["values"]["secrets_doc"]["amneziawg_secrets"]["server_private_key"] not in exposed
    ssh = [c[0] for c in calls if c[0][0] == "ssh"]
    assert all("StrictHostKeyChecking=yes" in c and "BatchMode=yes" in c and "ProxyCommand=none" in c for c in ssh)
    assert not any("scp" == Path(c[0][0]).name for c in calls)


def test_awg_context_resolves_canonical_listener_default(monkeypatch):
    module = load(ROOT / "scripts/install_liveness_sentinel.py", "installer_awg_context")
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: b"192.0.2.3\n")

    defaults, _cohort, endpoint = module._awg_context(
        {"amneziawg_secrets": {"instances": []}},
        {"awg_target": {"provider": "vultr", "environment": "probe"}},
        {"vultr:probe": "p2-udp"},
        {"PATH": os.environ["PATH"]},
    )

    assert defaults["listen_port"] == 51820
    assert endpoint == "192.0.2.3"


def test_bound_executor_routes_fixed_command_through_colima_not_host_ssh(setup):
    s = setup
    captured = []
    captured_environment = {}
    s["environment"]["UPCLOUD_TOKEN"] = "must-not-be-forwarded"
    s["environment"]["SSH_AUTH_SOCK"] = "/private/agent.sock"

    def fake_run(command, *, environment, **_kwargs):
        captured.extend(command)
        captured_environment.update(environment)
        return b"probe\n"

    s["module"]._run = fake_run
    result = s["module"]._ssh(s["config"]["sentinels"][0], "id -un", s["environment"],
                              executor={"profile": "vpn-liveness-one-shot"})
    assert result == b"probe\n"
    assert captured == ["colima", "ssh", "--profile", "vpn-liveness-one-shot", "--",
                        "/bin/sh", "-c", "id -un"]
    assert "sentinel-a" not in captured
    assert captured_environment == {
        "PATH": s["environment"]["PATH"],
        "HOME": s["environment"]["HOME"],
        "LANG": "C",
        "LC_ALL": "C",
    }


def test_install_binds_executor_before_any_remote_material_transfer(setup, tmp_path, monkeypatch):
    s = setup
    manifest, binding, cleanup = (tmp_path / name for name in
                                  ("executor.json", "binding.json", "cleanup.json"))
    for path in (manifest, cleanup):
        path.write_text("{}\n")
        path.chmod(0o600)
    events = []
    s["environment"]["UPCLOUD_TOKEN"] = "must-not-be-forwarded"
    original_run = s["module"]._run

    def capture_executor_environment(command, *, environment, **kwargs):
        if command[:3] == ["docker", "context", "show"]:
            assert environment == {
                "PATH": s["environment"]["PATH"],
                "HOME": s["environment"]["HOME"],
            }
            return b"default\n"
        return original_run(command, environment=environment, **kwargs)

    monkeypatch.setattr(s["module"], "_run", capture_executor_environment)

    def load_executor(*_args, runner, **_kwargs):
        runner(("docker", "context", "show"), timeout=10)
        events.append("preflight")
        return {"profile": "vpn-liveness-one-shot"}

    monkeypatch.setattr(s["module"], "load_live_executor", load_executor)

    def bind(*_args, **_kwargs):
        assert not any(Path(call[0][0]).name == "ssh" for call in s["calls"])
        events.append("bound")
        binding.write_text('{"bound":true}\n')
        binding.chmod(0o600)
        return {"bound": True}

    monkeypatch.setattr(s["module"], "bind_executor", bind)
    seen = []

    def executor_ssh(sentinel, command, environment, input_bytes=b"", timeout=30, executor=None):
        assert executor == {"profile": "vpn-liveness-one-shot"}
        seen.append(command)
        return s["fake_run"](["ssh", sentinel["ssh_target"], command], environment=environment,
                             input_bytes=input_bytes, timeout=timeout)

    monkeypatch.setattr(s["module"], "_ssh", executor_ssh)
    result = s["module"].install(
        s["path"], "probe-a", "sentinel", s["registry"], read_awg_stdin=True,
        stdin=io.StringIO(s["values"]["private_key"] + "\n"), environment=s["environment"],
        executor_manifest=manifest, executor_binding=binding, cleanup_manifest=cleanup)
    assert result["status"] == "committed"
    assert events == ["preflight", "bound"]
    assert seen[:2] == ["id -un", "sudo -n true"]
    installed = json.loads(s["registry"].read_text())["sentinels"]["probe-a"]
    assert installed["executor_binding_sha256"] == hashlib.sha256(binding.read_bytes()).hexdigest()


def test_executor_install_refuses_multi_sentinel_config_before_tools(setup, tmp_path):
    s = setup
    s["config"]["sentinels"].append(
        {**s["config"]["sentinels"][0], "id": "probe-b", "ssh_target": "sentinel-b"}
    )
    s["path"].write_text(yaml.safe_dump(s["config"]))
    manifest, binding, cleanup = (
        tmp_path / name for name in ("executor.json", "binding.json", "cleanup.json")
    )

    with pytest.raises(s["module"].InstallError, match="executor-config"):
        s["module"].install(
            s["path"],
            "probe-a",
            "sentinel",
            s["registry"],
            read_awg_stdin=True,
            stdin=io.StringIO(s["values"]["private_key"] + "\n"),
            environment=s["environment"],
            executor_manifest=manifest,
            executor_binding=binding,
            cleanup_manifest=cleanup,
        )
    assert not s["calls"]
    assert not binding.exists()


@pytest.mark.parametrize(
    "previous,current,accepted",
    [
        ({}, None, True),
        ({"executor_binding_sha256": "a" * 64}, "a" * 64, True),
        ({"executor_binding_sha256": "a" * 64}, None, False),
        ({}, "a" * 64, False),
        ({"executor_binding_sha256": "a" * 64}, "b" * 64, False),
    ],
)
def test_pending_retry_cannot_change_executor_transport(setup, previous, current, accepted):
    check = lambda: setup["module"]._require_pending_executor(previous, current)
    if accepted:
        assert check() is None
    else:
        with pytest.raises(setup["module"].InstallError, match="pending-executor-conflict"):
            check()


def test_public_profile_endpoint_must_match_exact_target_digest(setup):
    setup["config"]["sentinels"][0]["target"]["public_service_address_sha256"] = "e" * 64

    with pytest.raises(setup["module"].InstallError, match="target-profile-address-mismatch"):
        setup["install"]()

    assert not any(call[0][0] == "ssh" for call in setup["calls"])


@pytest.mark.parametrize("outcome", ["valid", "invalid", "interrupt", "read-error"])
def test_terminal_key_input_hides_bytes_and_restores_terminal(setup, outcome):
    s = setup
    master, slave = pty.openpty()
    original = termios.tcgetattr(slave)
    echoed_flags = []
    key = s["values"]["private_key"] if outcome == "valid" else "invalid-private-key"
    try:
        with os.fdopen(slave, "r", closefd=False) as reader:
            class TerminalInput:
                def isatty(self):
                    return True

                def fileno(self):
                    return slave

                def readline(self, limit):
                    assert limit == 128
                    echoed_flags.append(termios.tcgetattr(slave)[3] & (termios.ECHO | termios.ECHONL))
                    if outcome == "interrupt":
                        raise KeyboardInterrupt
                    if outcome == "read-error":
                        raise OSError("fixture read failure")
                    os.write(master, (key + "\n").encode())
                    return reader.readline(limit)

            def invoke():
                return s["module"].install(s["path"], "probe-a", "sentinel", s["registry"],
                                           read_awg_stdin=True, stdin=TerminalInput(), environment=s["environment"])

            if outcome == "valid":
                assert invoke()["status"] == "committed"
            else:
                error = KeyboardInterrupt if outcome == "interrupt" else (s["module"].InstallError, OSError)
                with pytest.raises(error):
                    invoke()
                assert not any(c[0][0] == "ssh" for c in s["calls"])
            assert termios.tcgetattr(slave) == original
            transcript = os.read(master, 4096) if select.select([master], [], [], 0.05)[0] else b""
            assert key.encode() not in transcript
            assert echoed_flags == [0]
    finally:
        termios.tcsetattr(slave, termios.TCSANOW, original)
        os.close(slave)
        os.close(master)


@pytest.mark.parametrize("failure", ["inspect", "disable", "restore"])
def test_terminal_key_input_refuses_without_echo_control(setup, monkeypatch, failure):
    s = setup
    master, slave = pty.openpty()
    get_attributes, set_attributes = termios.tcgetattr, termios.tcsetattr
    original = get_attributes(slave)
    transitions, reads = [], []

    class TerminalInput:
        def isatty(self):
            return True

        def fileno(self):
            return slave

        def readline(self, limit):
            assert limit == 128
            assert not get_attributes(slave)[3] & (termios.ECHO | termios.ECHONL)
            reads.append(True)
            return s["values"]["private_key"] + "\n"

    def inspect(fd):
        if failure == "inspect":
            raise termios.error("fixture inspection failure")
        return get_attributes(fd)

    def transition(fd, action, attributes):
        transitions.append(action)
        if failure == "restore" and action == termios.TCSAFLUSH:
            raise termios.error("fixture restoration failure")
        set_attributes(fd, action, attributes)
        if failure == "disable" and action == termios.TCSADRAIN:
            raise termios.error("fixture failure after applying hidden mode")

    monkeypatch.setattr(termios, "tcgetattr", inspect)
    monkeypatch.setattr(termios, "tcsetattr", transition)
    try:
        with pytest.raises(s["module"].InstallError, match="private-key-terminal-unavailable"):
            s["module"].install(s["path"], "probe-a", "sentinel", s["registry"],
                                read_awg_stdin=True, stdin=TerminalInput(), environment=s["environment"])
        assert not s["calls"]
        assert bool(reads) == (failure == "restore")
        assert transitions == ([] if failure == "inspect" else [termios.TCSADRAIN, termios.TCSAFLUSH])
        if failure != "restore":
            assert get_attributes(slave) == original
    finally:
        set_attributes(slave, termios.TCSANOW, original)
        os.close(slave)
        os.close(master)


@pytest.mark.parametrize("fault", ["parser", "revoked", "wrong-key", "bad-binding", "missing-hosts", "missing-cohorts", "cohort-mismatch", "dirty", "missing-key", "oversized-key"])
def test_local_failures_never_contact_ssh_and_clean_plaintext(setup, fault, monkeypatch):
    s, module = setup, setup["module"]
    if fault == "parser":
        s["state"]["parser_failure"] = True
    elif fault == "revoked":
        s["values"]["secrets_doc"]["client_registry"]["sentinel"]["status"] = "revoked"
    elif fault == "wrong-key":
        s["values"]["private_key"] = s["fixture"].key(9)
    elif fault == "bad-binding":
        s["config"]["sentinels"][0]["awg_target"]["environment"] = "other"
    elif fault in ("missing-hosts", "missing-cohorts"):
        s["environment"].pop("HOSTS" if fault == "missing-hosts" else "COHORTS")
    elif fault == "cohort-mismatch":
        s["environment"]["COHORTS"] = "p0"
    elif fault == "dirty":
        monkeypatch.setattr(module, "_source_identity", lambda _repo: (_ for _ in ()).throw(module.InstallError("source-dirty")))
    elif fault == "missing-key":
        s["values"]["private_key"] = ""
    else:
        s["values"]["private_key"] = "A" * 10000
    with pytest.raises((module.InstallError, module.ProfileError)):
        s["install"]()
    assert not any(c[0][0] == "ssh" for c in s["calls"])
    assert not any(p.exists() for p in s["plaintexts"])
    assert not s["registry"].exists()


@pytest.mark.parametrize("bad", ["malformed", "world-readable", "symlink", "duplicate-client"])
def test_registry_is_strict_and_blocks_decrypt_and_ssh(setup, bad):
    s = setup
    content = {"schema_version": 2, "sentinels": {"other": {"client": "sentinel", "ssh_target": "other"}}}
    s["registry"].write_text("{" if bad == "malformed" else json.dumps(content if bad == "duplicate-client" else {"schema_version": 2, "sentinels": {}}))
    s["registry"].chmod(0o644 if bad == "world-readable" else 0o600)
    if bad == "symlink":
        original = s["registry"].with_suffix(".original")
        s["registry"].rename(original)
        s["registry"].symlink_to(original)
    before = s["registry"].read_bytes()
    with pytest.raises(s["module"].InstallError):
        s["install"]()
    assert s["registry"].read_bytes() == before
    assert not s["calls"]


def test_lost_launch_is_reconciled_only_from_exact_receipt(setup):
    setup["state"]["lost_launch"] = True
    assert setup["install"]()["status"] == "committed"
    assert setup["registry"].exists()


def test_unknown_keeps_old_assignment_and_retry_needs_no_plaintext(setup):
    s = setup
    provenance = {"controller_revision": "1" * 40, "runner_sha256": "2" * 64,
                  "client_generation_id": "7f574d16-931e-42b4-a940-853b92f53a14",
                  "public_profile_digest": "3" * 64, "vantage": "external"}
    target = {**s["config"]["sentinels"][0]["target"], "required_profiles": sorted(s["values"]["required_profiles"]),
              "source_revision": provenance["controller_revision"], "runner_sha256": provenance["runner_sha256"],
              "public_profile_digest": provenance["public_profile_digest"]}
    old = {"schema_version": 2, "sentinels": {"probe-a": {"client": "old-client", "ssh_target": "old-host",
           "generation_id": provenance["client_generation_id"], "provenance": provenance,
           "required_profiles": s["values"]["required_profiles"], "policy": "fullstack", "vantage": "external",
           "target_identity": target}}}
    s["registry"].write_text(json.dumps(old))
    s["registry"].chmod(0o600)
    s["state"]["unknown"] = True
    with pytest.raises(s["module"].InstallError, match="unknown"):
        s["install"]()
    assert json.loads(s["registry"].read_text()) == old
    assert not any(p.exists() for p in s["plaintexts"])
    before = len(s["calls"])
    s["state"]["unknown"] = False
    assert s["install"]()["status"] == "committed"
    assert all(Path(c[0][0]).name in ("ssh", "audit-log.sh") for c in s["calls"][before:])


def test_reachable_uncommitted_retry_reuses_same_generation(setup):
    s = setup
    s["state"]["unknown"] = True
    with pytest.raises(s["module"].InstallError):
        s["install"]()
    first = s["bundles"][0]["generation_id"]
    s["state"].update(unknown=False, receipt=None)
    s["install"]()
    assert s["bundles"][1]["generation_id"] == first
    assert len(s["plaintexts"]) == 2


def test_wrong_receipt_cannot_publish_assignment(setup):
    s = setup
    run = s["module"]._run
    def wrong(command, **kwargs):
        result = run(command, **kwargs)
        if command[0] == "ssh" and not kwargs.get("input_bytes") and result.startswith(b'{"state": "committed"'):
            report = json.loads(result)
            report["receipt"]["provenance"]["public_profile_digest"] = "f" * 64
            return json.dumps(report).encode()
        return result
    s["module"]._run = wrong
    with pytest.raises(s["module"].InstallError):
        s["install"]()
    assert not s["registry"].exists()


def test_policy_without_awg_does_not_read_key_or_resolve_endpoint(setup):
    s = setup
    s["config"]["policies"][0]["required_profiles"] = ["p0-reality"]
    del s["config"]["sentinels"][0]["awg_target"]
    s["values"]["private_key"] = ""
    s["install"]()
    config = json.loads(base64.b64decode(s["bundles"][0]["files"]["config.json"]))
    assert config["expected_runtime"] == {"sing_box": "1.14.0"}
    assert not any(Path(c[0][0]).name in ("awg", "wg", "terraform-env.sh") for c in s["calls"])


def test_registry_lock_excludes_concurrent_authoring(setup):
    s = setup
    with s["module"].registry_lock(s["registry"]):
        with pytest.raises(s["module"].InstallError, match="busy"):
            s["install"]()
    assert not s["calls"]


def test_shell_is_only_a_python_entrypoint():
    script = (ROOT / "scripts/install-liveness-sentinel.sh").read_text()
    assert 'exec python3' in script and 'install_liveness_sentinel.py' in script
    assert 'scp ' not in script and 'sops ' not in script


@pytest.mark.parametrize("field", ["ssh_transport_host", "required_profiles", "provenance"])
def test_registry_rejects_malformed_entry_fields_before_commands(setup, field):
    s = setup
    value = {"client": "someone", "ssh_target": "other", field: 42}
    s["registry"].write_text(json.dumps({"schema_version": 2, "sentinels": {"other": value}}))
    s["registry"].chmod(0o600)
    with pytest.raises(s["module"].InstallError):
        s["install"]()
    assert not s["calls"]


def test_yaml_duplicate_identity_is_not_silently_overwritten(setup):
    s = setup
    s["path"].write_text("schema_version: 1\nschema_version: 2\n")
    with pytest.raises(s["module"].InstallError, match="duplicate"):
        s["module"]._yaml(s["path"])


def test_bound_awg_cohort_cannot_disable_actual_role(setup):
    s = setup
    s["environment"]["COHORTS"] = "p0,p1-web,p0"
    with pytest.raises(s["module"].InstallError, match="awg-disabled"):
        s["install"]()
    assert not any(c[0][0] == "ssh" for c in s["calls"])


def test_same_generation_retry_refuses_changed_public_profile(setup):
    s = setup
    s["state"]["unknown"] = True
    with pytest.raises(s["module"].InstallError):
        s["install"]()
    s["state"].update(unknown=False, receipt=None)
    s["values"]["standard_doc"]["outbounds"][0]["server_port"] = 8443
    before = len(s["bundles"])
    with pytest.raises(s["module"].InstallError, match="conflict"):
        s["install"]()
    assert len(s["bundles"]) == before


def test_local_runtime_version_pin_is_checked_before_parser_or_ssh(setup):
    s = setup
    s["config"]["expected_runtime"]["xray"] = "26.3.28"
    with pytest.raises(s["module"].InstallError, match="pin-mismatch"):
        s["install"]()
    assert not any(c[0][0] == "ssh" for c in s["calls"])


def test_real_source_identity_rejects_dirty_git_before_reading_runner(setup, monkeypatch):
    fresh = load(ROOT / "scripts/install_liveness_sentinel.py", "source_installer")
    calls = []
    def dirty(command, **_kwargs):
        calls.append(command)
        return b" M scripts/example.py\n"
    monkeypatch.setattr(fresh, "_run", dirty)
    with pytest.raises(fresh.InstallError, match="clean-and-committed"):
        fresh._source_identity(ROOT)
    assert len(calls) == 1


def receiver_run(module, root, bundle, monkeypatch, *, code=None, engine_result=None):
    """Execute the actual receiver with only fixed root/owner and systemd adapted.

    Filesystem reads/writes/locking/rename are real. This is not a privileged
    host installation or systemd execution proof.
    """
    import subprocess
    import types
    root.parent.mkdir(mode=0o700, exist_ok=True)
    source = (code or module.REMOTE_STAGE).replace("ROOT = pathlib.Path('/etc/vpn-liveness')", f"ROOT = pathlib.Path({str(root)!r})")
    source = source.replace("OWNER = 0", "OWNER = os.geteuid()")
    source = source.replace("pathlib.Path('/usr/local/lib/vpn-liveness/liveness_generation.py')", f"pathlib.Path({str(root.parent / 'installed-engine.py')!r})")
    assert "OWNER = os.geteuid()" in source
    calls = []
    def systemd(command, **kwargs):
        if engine_result is not None and command[0] == "/usr/bin/python3":
            return types.SimpleNamespace(returncode=engine_result, stdout=b'{}')
        assert command[0] in ("/usr/bin/systemctl", "/usr/bin/systemd-run")
        calls.append(command)
        return types.SimpleNamespace(returncode=0, stdout=b"inactive\n")
    monkeypatch.setattr(subprocess, "run", systemd)
    monkeypatch.setattr(sys, "argv", ["fixture", bundle["generation_id"]])
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(json.dumps(bundle).encode())))
    namespace = {}
    try:
        exec(compile(source, "receiver-fixture", "exec"), namespace)
    except BaseException:
        if "lock" in namespace:
            os.close(namespace["lock"])
        raise
    return calls


def test_receiver_atomically_stages_private_candidate_and_reuses_identical_bytes(setup, receiver_root, monkeypatch):
    s = setup
    s["install"]()
    bundle = s["bundles"][0]
    root = receiver_root
    calls = receiver_run(s["module"], root, bundle, monkeypatch)
    stage = root / "staging" / bundle["generation_id"]
    for name, encoded in bundle["files"].items():
        assert (stage / name).read_bytes() == base64.b64decode(encoded)
        assert (stage / name).stat().st_mode & 0o777 == 0o600
    assert root.stat().st_mode & 0o777 == 0o700
    assert stage.stat().st_mode & 0o777 == 0o700
    assert not list(stage.parent.glob(".candidate-*"))
    receiver_run(s["module"], root, bundle, monkeypatch)
    job = next(c for c in calls if c[0] == "/usr/bin/systemd-run")
    assert "--no-block" in job and "--collect" in job
    assert "--property=KillMode=control-group" in job and "--property=TimeoutStartSec=600" in job
    assert "--property=RuntimeMaxSec=600" in job


def test_receipt_deadline_outlives_maximum_probe_and_root_job(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    module = load(ROOT / "scripts/install_liveness_sentinel.py", "deadline_installer")
    engine = load(ROOT / "scripts/liveness_generation.py", "deadline_engine")
    assert engine.probe_deadline(60, sorted(engine.PROFILES)) < engine.JOB_TIMEOUT_SECONDS < module.RECEIPT_TIMEOUT
    assert module.RECEIPT_TIMEOUT == engine.RECEIPT_TIMEOUT == 660


@pytest.mark.parametrize("fault", ["path-traversal", "stage-symlink", "profile-symlink", "changed-profile", "changed-engine", "root-world-writable"])
def test_receiver_rejects_unsafe_or_conflicting_staging_without_overwriting(setup, receiver_root, monkeypatch, fault):
    s = setup
    s["install"]()
    bundle = s["bundles"][0]
    root = receiver_root
    receiver_run(s["module"], root, bundle, monkeypatch)
    stage = root / "staging" / bundle["generation_id"]
    original = (stage / "runner.py").read_bytes()
    if fault == "path-traversal":
        bundle["files"]["../outside"] = base64.b64encode(b"unexpected").decode()
    elif fault == "stage-symlink":
        moved = stage.with_name("original")
        stage.rename(moved)
        stage.symlink_to(moved)
    elif fault == "profile-symlink":
        profile = stage / "profiles/awg.conf"
        profile.unlink()
        profile.symlink_to(stage / "runner.py")
    elif fault == "changed-profile":
        bundle["files"]["profiles/awg.conf"] = base64.b64encode(b"changed").decode()
    elif fault == "changed-engine":
        bundle["engine"] = base64.b64encode(b"changed").decode()
    else:
        root.chmod(0o777)
    with pytest.raises((ValueError, OSError)):
        receiver_run(s["module"], root, bundle, monkeypatch)
    assert (stage / "runner.py").read_bytes() == original
    assert not (root / "outside").exists()


def test_ssh_does_not_inherit_provider_or_secret_environment(setup):
    s = setup
    s["environment"]["PROVIDER_TOKEN"] = "fixture-provider-token"
    s["install"]()
    for command, environment, _stdin in s["calls"]:
        if command[0] == "ssh":
            assert "PROVIDER_TOKEN" not in environment and "SOPS_FILE" not in environment


def test_actual_git_source_identity_requires_all_inputs_committed(setup, tmp_path):
    import subprocess
    fresh = load(ROOT / "scripts/install_liveness_sentinel.py", "git_installer")
    repo = tmp_path / "git-fixture"
    repo.mkdir()
    (repo / "scripts").mkdir()
    (repo / "scripts/vpn-protocol-liveness.py").write_bytes(b"# committed runner\n")
    (repo / "scripts/liveness_generation.py").write_bytes(b"# committed engine\n")
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    for args in (["init", "-q"], ["add", "scripts"], ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"]):
        subprocess.run(["git", "-C", str(repo), *args], env=env, check=True, capture_output=True)
    revision, runner, engine = fresh._source_identity(repo)
    assert len(revision) == 40 and runner == b"# committed runner\n" and engine == b"# committed engine\n"
    (repo / "uncommitted").write_text("fixture")
    with pytest.raises(fresh.InstallError, match="clean-and-committed"):
        fresh._source_identity(repo)


@pytest.mark.parametrize("state", ["running", "refused", "malformed"])
def test_pending_state_cannot_trigger_new_activation(setup, state):
    s = setup
    s["state"]["unknown"] = True
    with pytest.raises(s["module"].InstallError):
        s["install"]()
    before = len(s["bundles"])
    run = s["module"]._run
    def reply(command, **kwargs):
        if command[0] == "ssh" and not kwargs.get("input_bytes"):
            return json.dumps({"state": state}).encode()
        return run(command, **kwargs)
    s["module"]._run = reply
    with pytest.raises(s["module"].InstallError):
        s["install"]()
    assert len(s["bundles"]) == before
    assert not s["registry"].exists()


@pytest.mark.parametrize("code,state", [(3, "uncommitted"), (75, "running"), (1, "refused")])
def test_remote_receipt_distinguishes_retryable_busy_and_corrupt(setup, receiver_root, monkeypatch, capsys, code, state):
    s = setup
    s["install"]()
    bundle = s["bundles"][0]
    root = receiver_root
    receiver_run(s["module"], root, bundle, monkeypatch)
    capsys.readouterr()
    receiver_run(s["module"], root, bundle, monkeypatch, code=s["module"].REMOTE_RECEIPT, engine_result=code)
    assert json.loads(capsys.readouterr().out) == {"state": state}


@pytest.mark.parametrize("existing", ["pending.json", "current", "receipts"])
def test_missing_engine_with_existing_transaction_state_refuses(setup, receiver_root, monkeypatch, existing):
    s = setup
    s["install"]()
    bundle = s["bundles"][0]
    root = receiver_root
    root.mkdir(parents=True, mode=0o700)
    if existing == "receipts":
        (root / existing).mkdir(mode=0o700)
        (root / existing / "evidence.json").write_text("{}")
    else:
        (root / existing).write_text("private transaction fixture")
    with pytest.raises(ValueError, match="unresolved-state-without-engine"):
        receiver_run(s["module"], root, bundle, monkeypatch, code=s["module"].REMOTE_RECEIPT)


def test_missing_job_engine_can_query_safe_fixed_installed_engine(setup, receiver_root, monkeypatch, capsys):
    s = setup
    s["install"]()
    root = receiver_root
    root.mkdir(parents=True, mode=0o700)
    (root.parent / "installed-engine.py").write_bytes(b"# installed engine fixture\n")
    (root.parent / "installed-engine.py").chmod(0o644)
    receiver_run(s["module"], root, s["bundles"][0], monkeypatch, code=s["module"].REMOTE_RECEIPT, engine_result=75)
    assert json.loads(capsys.readouterr().out) == {"state": "running"}


@pytest.mark.parametrize("url", ["https://host.example:444/health", "https://user:password@192.0.2.9/", "https://[2001:db8::1]/", "https://192.0.2.9/#fragment"])
def test_awg_runtime_url_contract_is_checked_before_any_ssh(setup, url):
    s = setup
    s["config"]["probe_url"] = url
    with pytest.raises(s["module"].InstallError):
        s["install"]()
    assert not any(c[0][0] == "ssh" for c in s["calls"])


@pytest.mark.parametrize("filename", ["awg.conf", "engine.py"])
def test_receiver_failed_copy_removes_only_owned_temporary_and_retry_works(setup, receiver_root, monkeypatch, filename):
    s = setup
    s["install"]()
    root = receiver_root
    bundle = s["bundles"][0]
    original_open = os.open
    def failed_open(path, flags, *args, **kwargs):
        if Path(path).is_relative_to(root) and Path(path).name == filename and flags & os.O_CREAT:
            raise OSError("fixture ENOSPC")
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", failed_open)
    with pytest.raises(OSError):
        receiver_run(s["module"], root, bundle, monkeypatch)
    if filename == "engine.py":
        assert not (root / "jobs" / bundle["generation_id"]).exists()
        assert not list((root / "jobs").glob(".job-*"))
    else:
        assert not (root / "staging" / bundle["generation_id"]).exists()
        assert not list((root / "staging").glob(".candidate-*"))
    monkeypatch.setattr(os, "open", original_open)
    receiver_run(s["module"], root, bundle, monkeypatch)
    assert (root / "jobs" / bundle["generation_id"] / "engine.py").read_bytes() == base64.b64decode(bundle["engine"])


def test_success_preserves_audit_per_explicit_host_and_audit_failure_is_not_rollback(setup):
    s = setup
    run = s["module"]._run
    audits = []
    def audit(command, **kwargs):
        if Path(command[0]).name == "audit-log.sh":
            audits.append(command)
            raise s["module"].InstallError("fixture-audit-unavailable")
        return run(command, **kwargs)
    s["module"]._run = audit
    assert s["install"]()["status"] == "committed"
    assert len(audits) == 3
    assert {c[c.index("--provider") + 1] for c in audits} == {"upcloud", "scaleway", "vultr"}
    assert all(c[c.index("--env") + 1] == "probe" for c in audits)
    assert s["registry"].exists()


def test_invalid_policy_quorum_or_reference_fails_before_any_tools(setup):
    s = setup
    s["config"]["policies"][0]["min_failed_vantages"] = 2
    with pytest.raises(s["module"].InstallError):
        s["install"]()
    assert not s["calls"]
