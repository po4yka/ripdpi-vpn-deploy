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
PACKAGED_SFTP = b"Subsystem sftp /usr/lib/openssh/sftp-server\n"
PACKAGED_MAIN_DEFAULTS = (b"KbdInteractiveAuthentication no\nX11Forwarding yes\n" + PACKAGED_SFTP)
OWNERSHIP_FILES = ("sshd_config", BOOT, MANAGED, CLOUD)
BASELINE_HARDENING = (b"X11Forwarding no\nAllowTcpForwarding no\nAllowAgentForwarding no\n"
                      b"AllowUsers deploy\nClientAliveInterval 60\n"
                      b"Subsystem sftp internal-sftp -f AUTHPRIV -l INFO\n")


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
    originals = configuration_records(config)
    plan = planner.build_plan(config, contexts=CONTEXTS)
    assert plan["schema_version"] == 2
    assert plan["changed"] is True
    assert tuple(plan["files"]) == OWNERSHIP_FILES
    assert base64.b64decode(plan["files"][BOOT]["after"]["data_b64"]) == originals[BOOT][0].replace(b"X11Forwarding no\n", b"")
    candidate = base64.b64decode(plan["files"][MANAGED]["after"]["data_b64"])
    assert b"PasswordAuthentication" not in candidate
    assert b"Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com\n" in candidate
    assert base64.b64decode(plan["files"][CLOUD]["after"]["data_b64"]) == b"# generated\n"
    assert [entry["context"] for entry in plan["effective"]] == [None, *CONTEXTS]
    assert all(entry["before_sha256"] == entry["after_sha256"] for entry in plan["effective"])
    assert configuration_records(config) == originals
    planner.assert_snapshot(plan, config)


def test_installed_candidate_is_effective_and_second_plan_is_noop(planner, config):
    plan = planner.build_plan(config, contexts=CONTEXTS)
    for relative, item in plan["files"].items():
        (config / relative).write_bytes(base64.b64decode(item["after"]["data_b64"]))
    planner.assert_effective(plan, config, phase="after")
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


@pytest.fixture
def packaged_config(config):
    main = config / "sshd_config"
    main.write_bytes(main.read_bytes() + PACKAGED_MAIN_DEFAULTS)
    return config


def test_packaged_main_is_normalized_only_when_every_publish_boundary_preserves_policy(planner, packaged_config):
    originals = configuration_records(packaged_config)
    plan = planner.build_plan(packaged_config, contexts=CONTEXTS)
    assert plan["schema_version"] == 2
    assert tuple(plan["files"]) == OWNERSHIP_FILES
    expected = originals["sshd_config"][0].replace(
        b"KbdInteractiveAuthentication no\nX11Forwarding yes\n",
        b"# normalized-shadowed KbdInteractiveAuthentication no\n"
        b"# normalized-shadowed X11Forwarding yes\n",
    )
    main = plan["files"]["sshd_config"]
    assert base64.b64decode(main["after"]["data_b64"]) == expected
    assert {key: main["after"][key] for key in ("mode", "uid", "gid")} == {
        key: main["before"][key] for key in ("mode", "uid", "gid")}
    assert PACKAGED_SFTP in base64.b64decode(main["after"]["data_b64"])
    assert all(entry["before_sha256"] == entry["after_sha256"] for entry in plan["effective"])
    assert configuration_records(packaged_config) == originals

    # The core publishes this exact tuple and rolls it back in reverse. Every
    # prefix is therefore both an apply boundary and a reverse rollback suffix.
    planner.assert_effective(plan, packaged_config, phase="before")
    for relative in OWNERSHIP_FILES:
        pair = plan["files"][relative]
        (packaged_config / relative).write_bytes(base64.b64decode(pair["after"]["data_b64"]))
        (packaged_config / relative).chmod(pair["after"]["mode"])
        planner.assert_effective(plan, packaged_config, phase="before")


@pytest.mark.parametrize("fault", ["kbd-value", "x11-value", "owned-main", "duplicate", "unshadowed"])
def test_packaged_main_unknown_or_unshadowed_ownership_refuses_without_writes(planner, packaged_config, fault):
    main = packaged_config / "sshd_config"
    if fault == "kbd-value":
        main.write_bytes(main.read_bytes().replace(b"KbdInteractiveAuthentication no", b"KbdInteractiveAuthentication yes"))
    elif fault == "x11-value":
        main.write_bytes(main.read_bytes().replace(b"X11Forwarding yes", b"X11Forwarding no"))
    elif fault == "owned-main":
        main.write_bytes(main.read_bytes() + b"PasswordAuthentication no\n")
    elif fault == "duplicate":
        main.write_bytes(main.read_bytes() + b"X11Forwarding yes\n")
    else:
        include = f"Include {packaged_config}/sshd_config.d/*.conf\n".encode()
        main.write_bytes(main.read_bytes().replace(include, b"").replace(PACKAGED_MAIN_DEFAULTS, PACKAGED_MAIN_DEFAULTS + include))
    originals = configuration_records(packaged_config)
    with pytest.raises(planner.OwnershipError):
        planner.build_plan(packaged_config, contexts=CONTEXTS)
    assert configuration_records(packaged_config) == originals


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
        planner.assert_effective(plan, config, phase="after")


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
            operation(plan, config, **({"phase": "after"} if operation is planner.assert_effective else {}))


@pytest.mark.parametrize("fault", ["bool-version", "legacy-version", "missing-read-set"])
def test_even_rehashed_malformed_plan_is_categorical(planner, config, fault):
    plan = planner.build_plan(config, contexts=CONTEXTS)
    if fault == "bool-version":
        plan["schema_version"] = True
    elif fault == "legacy-version":
        plan["schema_version"] = 1
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


@pytest.fixture
def baseline_config(config):
    boot = config / BOOT
    boot.write_bytes(boot.read_bytes().replace(b"X11Forwarding no\n", b""))
    (config / MANAGED).write_bytes(b"# first-boot runtime owner\nX11Forwarding no\n")
    (config / CLOUD).write_bytes(b"# generated authentication normalized at bootstrap\n")
    main = config / "sshd_config"
    main.write_bytes(main.read_bytes() + PACKAGED_SFTP)
    return config


def configuration_records(config):
    paths = [config / "sshd_config", *(config / "sshd_config.d").iterdir()]
    return {str(path.relative_to(config)): (path.read_bytes(), path.stat().st_mode,
            path.stat().st_uid, path.stat().st_gid) for path in paths}


@pytest.mark.parametrize("missing_managed", [False, True], ids=["seeded20", "absent20"])
def test_baseline_plan_preserves_bootstrap_and_stages_complete_sftp_handoff(planner, baseline_config, missing_managed):
    config = baseline_config
    if missing_managed:
        (config / MANAGED).unlink()
    originals = configuration_records(config)
    plan = planner.build_baseline_plan(config, contexts=CONTEXTS, hardening=BASELINE_HARDENING)
    assert configuration_records(config) == originals
    assert plan["operation"] == "sshd-baseline"
    assert plan["schema_version"] == 2
    assert set(plan["files"]) == {"sshd_config", MANAGED}
    assert plan["changed"] is True
    assert plan["files"][MANAGED]["before"]["exists"] is not missing_managed
    assert base64.b64decode(plan["files"][MANAGED]["after"]["data_b64"]) == BASELINE_HARDENING
    assert base64.b64decode(plan["files"]["sshd_config"]["after"]["data_b64"]) == originals["sshd_config"][0].replace(PACKAGED_SFTP, b"# " + PACKAGED_SFTP)
    if missing_managed:
        assert plan["files"][MANAGED]["before"] == {"exists": False, "data_b64": None,
            "sha256": None, "mode": None, "uid": None, "gid": None}
        assert {key: plan["files"][MANAGED]["after"][key] for key in ("mode", "uid", "gid")} == {"mode": 0o644, "uid": os.geteuid(), "gid": 0}
    assert any(entry["before_sha256"] != entry["after_sha256"] for entry in plan["effective"])
    planner.assert_snapshot(plan, config)
    planner.assert_effective(plan, config, phase="before")
    with pytest.raises(planner.OwnershipError, match="effective-policy-changed"):
        planner.assert_effective(plan, config, phase="after")
    # Fixture installation exercises the real parser; it is not transaction proof.
    for relative, pair in plan["files"].items():
        (config / relative).write_bytes(base64.b64decode(pair["after"]["data_b64"]))
        (config / relative).chmod(pair["after"]["mode"])
    planner.assert_effective(plan, config, phase="after")
    with pytest.raises(planner.OwnershipError, match="effective-policy-changed"):
        planner.assert_effective(plan, config, phase="before")
    repeated = planner.build_baseline_plan(config, contexts=CONTEXTS, hardening=BASELINE_HARDENING)
    assert repeated["changed"] is False
    for relative in (BOOT, CLOUD):
        assert configuration_records(config)[relative] == originals[relative]


def test_baseline_without_internal_sftp_preserves_packaged_owner(planner, baseline_config):
    original = (baseline_config / "sshd_config").read_bytes()
    hardening = BASELINE_HARDENING.split(b"Subsystem sftp", 1)[0]
    plan = planner.build_baseline_plan(baseline_config, contexts=CONTEXTS, hardening=hardening)
    assert base64.b64decode(plan["files"]["sshd_config"]["after"]["data_b64"]) == original


@pytest.mark.parametrize("relative, extra", [
    (BOOT, b"X11Forwarding no\n"), (CLOUD, b"PasswordAuthentication no\n"),
    (MANAGED, b"PasswordAuthentication no\n"),
    ("sshd_config.d/90-unrelated.conf", b"AllowTcpForwarding no\n"),
    ("sshd_config", b"Subsystem sftp /usr/lib/openssh/sftp-server\n"),
])
def test_baseline_refuses_legacy_or_duplicate_owners_without_writes(planner, baseline_config, relative, extra):
    path = baseline_config / relative
    path.write_bytes(path.read_bytes() + extra)
    originals = configuration_records(baseline_config)
    with pytest.raises(planner.OwnershipError):
        planner.build_baseline_plan(baseline_config, contexts=CONTEXTS, hardening=BASELINE_HARDENING)
    assert configuration_records(baseline_config) == originals


@pytest.mark.parametrize("extra", [
    b"Include /etc/ssh/other.conf\n", b"Match User deploy\n", b"PasswordAuthentication no\n",
    b"Port 2222\n", b"AuthorizedKeysCommand /bin/true\n", b"X11Forwarding no\n",
    b"Subsystem other /bin/true\n",
])
def test_baseline_candidate_cannot_take_unauthorized_ownership(planner, baseline_config, extra):
    originals = configuration_records(baseline_config)
    with pytest.raises(planner.OwnershipError):
        planner.build_baseline_plan(baseline_config, contexts=CONTEXTS, hardening=BASELINE_HARDENING + extra)
    assert configuration_records(baseline_config) == originals


@pytest.mark.parametrize("subsystem", [b"sftp /bin/true", b"sftp internal-sftp -d /tmp", b"sftp internal-sftp -p read"])
def test_baseline_rejects_noncanonical_subsystem_commands(planner, baseline_config, subsystem):
    hardening = BASELINE_HARDENING.split(b"Subsystem sftp", 1)[0] + b"Subsystem " + subsystem + b"\n"
    with pytest.raises(planner.OwnershipError):
        planner.build_baseline_plan(baseline_config, contexts=CONTEXTS, hardening=hardening)


def test_baseline_never_removes_the_only_sftp_owner(planner, baseline_config):
    main = baseline_config / "sshd_config"
    main.write_bytes(main.read_bytes().replace(PACKAGED_SFTP, b""))
    with pytest.raises(planner.OwnershipError):
        planner.build_baseline_plan(baseline_config, contexts=CONTEXTS,
                                    hardening=BASELINE_HARDENING.split(b"Subsystem sftp", 1)[0])


@pytest.mark.parametrize("old_pin", [True, False], ids=["remove-existing-pin", "add-new-pin"])
def test_baseline_cannot_change_effective_algorithms(planner, baseline_config, old_pin):
    pin = b"Ciphers aes256-gcm@openssh.com\n"
    if old_pin:
        managed = baseline_config / MANAGED
        managed.write_bytes(managed.read_bytes() + pin)
    originals = configuration_records(baseline_config)
    hardening = BASELINE_HARDENING if old_pin else BASELINE_HARDENING + pin
    with pytest.raises(planner.OwnershipError, match="algorithm-policy-changed"):
        planner.build_baseline_plan(baseline_config, contexts=CONTEXTS, hardening=hardening)
    assert configuration_records(baseline_config) == originals


@pytest.mark.parametrize("hardening", [
    b"", None, "X11Forwarding no\n", bytearray(BASELINE_HARDENING),
    BASELINE_HARDENING + b"#" + b"x" * (8193 - len(BASELINE_HARDENING) - 2) + b"\n",
    BASELINE_HARDENING + b"# non-ascii \xff\n", BASELINE_HARDENING + b"# nul \x00\n",
], ids=["empty", "none", "text", "bytearray", "oversize", "non-ascii", "nul"])
def test_baseline_hardening_input_is_bounded_ascii_bytes(planner, baseline_config, hardening):
    originals = configuration_records(baseline_config)
    with pytest.raises(planner.OwnershipError):
        planner.build_baseline_plan(baseline_config, contexts=CONTEXTS, hardening=hardening)
    assert configuration_records(baseline_config) == originals


def test_baseline_accepts_canonical_candidate_at_exact_input_limit(planner, baseline_config):
    hardening = BASELINE_HARDENING + b"#" + b"x" * (8192 - len(BASELINE_HARDENING) - 2) + b"\n"
    plan = planner.build_baseline_plan(baseline_config, contexts=CONTEXTS, hardening=hardening)
    assert base64.b64decode(plan["files"][MANAGED]["after"]["data_b64"]) == hardening


def test_effective_phase_is_required_and_not_coerced(planner, config):
    plan = planner.build_plan(config, contexts=CONTEXTS)
    with pytest.raises(TypeError):
        planner.assert_effective(plan, config)
    for phase in (None, "mixed", "BEFORE"):
        with pytest.raises(planner.OwnershipError, match="invalid-phase"):
            planner.assert_effective(plan, config, phase=phase)
