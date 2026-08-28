"""Real OpenSSH policy parity for the private, non-mutating migration planner."""

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ansible/roles/baseline/files/sshd_ownership.py"
CONTEXTS = [
    {"user": "deploy", "host": "controller.example", "addr": "198.51.100.2", "laddr": "192.0.2.10", "lport": 2222},
    {"user": "deploy", "host": "controller.example", "addr": "100.64.0.2", "laddr": "100.64.0.3", "lport": 2222},
]
BOOT = "sshd_config.d/10-cloud-init-hardening.conf"
MANAGED = "sshd_config.d/20-ansible-hardening.conf"
CLOUD = "sshd_config.d/50-cloud-init.conf"


@pytest.fixture
def planner(monkeypatch):
    spec = importlib.util.spec_from_file_location("sshd_ownership", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OWNER_UID", os.geteuid())
    return module


@pytest.fixture
def config():
    # Secure ancestors on both macOS and Linux: /tmp is intentionally forbidden.
    with tempfile.TemporaryDirectory(prefix=".sshd-ownership-", dir=Path.home()) as directory:
        root = Path(directory)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(root / "host_key")], check=True, timeout=10)
        (root / "sshd_config.d").mkdir(mode=0o755)
        (root / "sshd_config").write_text(f"HostKey {root}/host_key\nInclude {root}/sshd_config.d/*.conf\n")
        (root / BOOT).write_text("# bootstrap\nPort 2222\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\nPubkeyAuthentication yes\nX11Forwarding no\n")
        (root / MANAGED).write_text("# managed\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\nPubkeyAuthentication yes\nX11Forwarding no\nAllowTcpForwarding no\nAllowUsers deploy\nCiphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com\n")
        (root / CLOUD).write_text("# generated\nPasswordAuthentication no\n")
        (root / "sshd_config.d/90-unrelated.conf").write_text("# unrelated\nBanner none\n")
        for path in [root / "sshd_config", *(root / "sshd_config.d").iterdir()]:
            path.chmod(0o644)
        yield root


def test_known_legacy_migration_preserves_full_policy_without_writes(planner, config):
    originals = {p: p.read_bytes() for p in (config / "sshd_config.d").iterdir()}
    plan = planner.build_plan(config, contexts=CONTEXTS)
    assert plan["changed"] is True
    assert set(plan["files"]) == {BOOT, MANAGED, CLOUD}
    assert base64.b64decode(plan["files"][BOOT]["after"]["data_b64"]) == originals[config / BOOT].replace(b"X11Forwarding no\n", b"")
    candidate = base64.b64decode(plan["files"][MANAGED]["after"]["data_b64"])
    assert b"PasswordAuthentication" not in candidate
    assert b"Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com\n" in candidate
    assert base64.b64decode(plan["files"][CLOUD]["after"]["data_b64"]) == b"# generated\n"
    assert [entry["context"] for entry in plan["effective"]] == [None, *CONTEXTS]
    assert all(entry["before_sha256"] == entry["after_sha256"] for entry in plan["effective"])
    assert {p: p.read_bytes() for p in originals} == originals
    planner.assert_snapshot(plan, config)


def test_installed_candidate_is_effective_and_second_plan_is_noop(planner, config):
    plan = planner.build_plan(config, contexts=CONTEXTS)
    for relative, item in plan["files"].items():
        (config / relative).write_bytes(base64.b64decode(item["after"]["data_b64"]))
    planner.assert_effective(plan, config)
    with pytest.raises(planner.OwnershipError, match="snapshot-changed"):
        planner.assert_snapshot(plan, config)
    repeated = planner.build_plan(config, contexts=CONTEXTS)
    assert repeated["changed"] is False


def test_absent_cloud_file_and_x11_transfer_preserve_other_bytes(planner, config):
    (config / CLOUD).unlink()
    previous = (config / MANAGED).read_bytes().replace(b"X11Forwarding no\n", b"")
    (config / MANAGED).write_bytes(previous)
    plan = planner.build_plan(config, contexts=CONTEXTS)
    assert plan["files"][CLOUD]["before"] == plan["files"][CLOUD]["after"] == {
        "exists": False, "data_b64": None, "sha256": None, "mode": None, "uid": None, "gid": None,
    }
    candidate = base64.b64decode(plan["files"][MANAGED]["after"]["data_b64"])
    assert candidate.endswith(b"X11Forwarding no\n")
    assert b"Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com\n" in candidate


@pytest.mark.parametrize("fault", ["main", "unrelated", "membership", "inode", "mode", "absent-cloud"])
def test_snapshot_detects_complete_graph_drift(planner, config, fault):
    if fault == "absent-cloud":
        (config / CLOUD).unlink()
    plan = planner.build_plan(config, contexts=CONTEXTS)
    assert {entry["relative_path"] for entry in plan["read_set"]} >= {"sshd_config", BOOT, MANAGED, "sshd_config.d/90-unrelated.conf"}
    if fault in {"main", "unrelated"}:
        path = config / ("sshd_config" if fault == "main" else "sshd_config.d/90-unrelated.conf")
        path.write_bytes(path.read_bytes() + b"# concurrent edit\n")
    elif fault == "membership":
        (config / "sshd_config.d/80-new.conf").write_text("PrintMotd no\n")
    elif fault == "inode":
        path = config / MANAGED
        replacement = config / "replacement"
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(path.stat().st_mode & 0o777)
        replacement.replace(path)
    elif fault == "mode":
        (config / MANAGED).chmod(0o600)
    else:
        (config / CLOUD).write_text("# newly appeared\n")
    with pytest.raises(planner.OwnershipError, match="snapshot-changed"):
        planner.assert_snapshot(plan, config)


@pytest.mark.parametrize("relative,extra", [
    (BOOT, "X11Forwarding no\n"),
    (MANAGED, "Port 2222\n"),
    (CLOUD, "PermitRootLogin no\n"),
    ("sshd_config.d/90-unrelated.conf", "AllowTcpForwarding no\n"),
    ("sshd_config", "PasswordAuthentication no\n"),
    (MANAGED, "Match User deploy\n"),
    ("sshd_config.d/90-unrelated.conf", "Include /etc/ssh/other.conf\n"),
])
def test_unrecognized_ownership_and_contexts_refuse_without_mutation(planner, config, relative, extra):
    path = config / relative
    path.write_text(path.read_text() + extra)
    before = path.read_bytes()
    with pytest.raises(planner.OwnershipError):
        planner.build_plan(config, contexts=CONTEXTS)
    assert path.read_bytes() == before


@pytest.mark.parametrize("fault", ["missing", "relative", "twice"])
def test_noncanonical_main_include_refused(planner, config, fault):
    path = config / "sshd_config"
    if fault == "missing":
        path.write_text(path.read_text().split("Include")[0])
    elif fault == "relative":
        path.write_text(path.read_text().replace(str(config) + "/sshd_config.d", "sshd_config.d"))
    else:
        path.write_text(path.read_text() + f"Include {config}/sshd_config.d/*.conf\n")
    with pytest.raises(planner.OwnershipError):
        planner.build_plan(config, contexts=CONTEXTS)


@pytest.mark.parametrize("fault", ["symlink", "hardlink", "fifo", "writable-file", "writable-parent", "oversized"])
def test_unsafe_files_are_rejected_before_parser(planner, config, fault):
    path = config / MANAGED
    if fault in {"symlink", "hardlink", "fifo"}:
        original = config / "original"
        path.rename(original)
        if fault == "symlink":
            path.symlink_to(original)
        elif fault == "hardlink":
            os.link(original, path)
        else:
            os.mkfifo(path)
    elif fault == "writable-file":
        path.chmod(0o666)
    elif fault == "writable-parent":
        (config / "sshd_config.d").chmod(0o777)
    else:
        path.write_bytes(b"#" * (planner.MAX_FILE + 1))
    with pytest.raises(planner.OwnershipError):
        planner.build_plan(config, contexts=CONTEXTS)


@pytest.mark.parametrize("fault", ["empty", "bool-port", "injected-host", "duplicate", "invalid-ip"])
def test_contexts_are_structured_and_strict(planner, config, fault):
    contexts = [dict(item) for item in CONTEXTS]
    if fault == "empty":
        contexts = []
    elif fault == "bool-port":
        contexts[0]["lport"] = True
    elif fault == "injected-host":
        contexts[0]["host"] = "host,user=root"
    elif fault == "duplicate":
        contexts.append(dict(contexts[0]))
    else:
        contexts[0]["addr"] = "not-an-address"
    with pytest.raises(planner.OwnershipError, match="invalid-context"):
        planner.build_plan(config, contexts=contexts)


def test_installed_full_output_change_is_rejected(planner, config):
    plan = planner.build_plan(config, contexts=CONTEXTS)
    path = config / "sshd_config.d/90-unrelated.conf"
    path.write_text(path.read_text() + "PrintMotd no\n")
    with pytest.raises(planner.OwnershipError, match="effective-policy-changed"):
        planner.assert_effective(plan, config)


def test_real_parser_failure_does_not_echo_values(planner, config):
    canary = "PRIVATE-CONFIG-CANARY"
    path = config / MANAGED
    path.write_text(path.read_text().replace("AllowTcpForwarding no", "AllowTcpForwarding " + canary))
    with pytest.raises(planner.OwnershipError, match="sshd-rejected") as error:
        planner.build_plan(config, contexts=CONTEXTS)
    assert canary not in str(error.value)


@pytest.mark.parametrize("fault", ["timeout", "output"])
def test_parser_process_is_bounded(planner, config, monkeypatch, fault):
    import sys
    executable = config / "parser-fixture"
    executable.write_text(f"#!{sys.executable}\n" + ("import time\ntime.sleep(30)\n" if fault == "timeout" else "print('x' * 4096)\n"))
    executable.chmod(0o700)
    monkeypatch.setattr(planner, "SSHD", str(executable))
    monkeypatch.setattr(planner, "COMMAND_TIMEOUT", 0.2)
    monkeypatch.setattr(planner, "MAX_OUTPUT", 512)
    started = time.monotonic()
    with pytest.raises(planner.OwnershipError, match="sshd-timeout|sshd-output-too-large"):
        planner.build_plan(config, contexts=CONTEXTS)
    assert time.monotonic() - started < 5


def test_tampered_plan_is_rejected(planner, config):
    plan = planner.build_plan(config, contexts=CONTEXTS)
    plan = json.loads(json.dumps(plan))
    plan["effective"][0]["after_sha256"] = "0" * 64
    for operation in (planner.assert_snapshot, planner.assert_effective):
        with pytest.raises(planner.OwnershipError, match="invalid-plan"):
            operation(plan, config)


@pytest.mark.parametrize("fault", ["bool-version", "missing-read-set"])
def test_even_rehashed_malformed_plan_is_categorical(planner, config, fault):
    plan = planner.build_plan(config, contexts=CONTEXTS)
    if fault == "bool-version":
        plan["schema_version"] = True
    else:
        del plan["read_set"]
    del plan["snapshot_digest"]
    plan["snapshot_digest"] = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with pytest.raises(planner.OwnershipError, match="invalid-plan"):
        planner.assert_snapshot(plan, config)


def test_non_ascii_line_boundaries_are_not_reinterpreted(planner, config):
    path = config / MANAGED
    path.write_bytes(path.read_bytes() + "# comment\u2028LogLevel VERBOSE\n".encode())
    with pytest.raises(planner.OwnershipError, match="unsupported-directive"):
        planner.build_plan(config, contexts=CONTEXTS)


def test_effective_validation_has_one_aggregate_deadline(planner, config, monkeypatch):
    import sys
    executable = config / "slow-parser-fixture"
    executable.write_text(f"#!{sys.executable}\nimport os,sys,time\ntime.sleep(0.15)\nos.execv('/usr/sbin/sshd', ['/usr/sbin/sshd', *sys.argv[1:]])\n")
    executable.chmod(0o700)
    monkeypatch.setattr(planner, "SSHD", str(executable))
    monkeypatch.setattr(planner, "COMMAND_TIMEOUT", 2)
    monkeypatch.setattr(planner, "EFFECTIVE_TIMEOUT", 0.25, raising=False)
    started = time.monotonic()
    with pytest.raises(planner.OwnershipError, match="sshd-timeout"):
        planner.build_plan(config, contexts=CONTEXTS)
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("scratch_mode", [None, 0o700, 0o755])
def test_validation_tree_ignores_ambient_temporary_directory(planner, config, monkeypatch, scratch_mode):
    import sys
    poisoned = config / "operator-temp"
    poisoned.mkdir()
    observed = config / "parser-paths"
    executable = config / "recording-parser-fixture"
    executable.write_text(f"#!{sys.executable}\nimport os,sys\nwith open({str(observed)!r}, 'a') as stream: stream.write(sys.argv[sys.argv.index('-f')+1]+'\\n')\nos.execv('/usr/sbin/sshd', ['/usr/sbin/sshd', *sys.argv[1:]])\n")
    executable.chmod(0o700)
    monkeypatch.setattr(planner, "SSHD", str(executable))
    monkeypatch.setattr(planner.tempfile, "tempdir", str(poisoned))
    scratch = config / "validation"
    if scratch_mode is not None:
        scratch.mkdir(mode=scratch_mode)
        scratch.chmod(scratch_mode)
        monkeypatch.setattr(planner, "SCRATCH_ROOT", scratch, raising=False)
    planner.build_plan(config, contexts=CONTEXTS)
    assert observed.read_text().splitlines()
    assert all(not Path(path).is_relative_to(poisoned) for path in observed.read_text().splitlines())
    if scratch_mode is not None:
        assert all(Path(path).is_relative_to(scratch) for path in observed.read_text().splitlines())
        assert list(scratch.iterdir()) == []


@pytest.mark.parametrize("fault", ["writable", "symlink"])
def test_existing_unsafe_scratch_does_not_fall_back(planner, config, monkeypatch, fault):
    scratch = config / "validation"
    if fault == "writable":
        scratch.mkdir(mode=0o777)
        scratch.chmod(0o777)
    else:
        scratch.symlink_to(config, target_is_directory=True)
    monkeypatch.setattr(planner, "SCRATCH_ROOT", scratch, raising=False)
    with pytest.raises(planner.OwnershipError):
        planner.build_plan(config, contexts=CONTEXTS)


def test_nonmatching_directory_entries_are_also_bounded(planner, config):
    for number in range(257):
        (config / "sshd_config.d" / f".ignored-{number}").touch()
    with pytest.raises(planner.OwnershipError, match="unsupported-membership"):
        planner.build_plan(config, contexts=CONTEXTS)
