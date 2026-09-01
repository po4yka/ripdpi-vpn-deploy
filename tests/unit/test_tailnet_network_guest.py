"""Durable guest nftables transaction and recovery boundaries."""

from __future__ import annotations
import importlib.util, json, os, subprocess, sys, time
from pathlib import Path
from uuid import UUID
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/tailnet-network-guest.py"


def load():
    spec = importlib.util.spec_from_file_location("tailnet_guest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fragment(v4="100.64.10.20/32", v6="fd7a:115c:a1e0::1234/128"):
    return (
        "# vpn-tailnet-ssh-sets schema=1\nset vpn_tailnet_ssh_v4 {\n  type ipv4_addr\n  flags interval\n"
        + (f"  elements = {{ {v4} }}\n" if v4 else "  elements = { }\n")
        + "}\n\nset vpn_tailnet_ssh_v6 {\n"
        "  type ipv6_addr\n  flags interval\n"
        + (f"  elements = {{ {v6} }}\n" if v6 else "  elements = { }\n")
        + "}\n"
    ).encode()


class FakeRuntime:
    def __init__(self, module, paths):
        self.module, self.paths, self.now, self.mono, self.events, self.fail = (
            module,
            paths,
            1000,
            500,
            [],
            None,
        )

    def clock(self):
        return self.now

    def monotonic(self):
        return self.mono

    def boot_id(self):
        return "123e4567-e89b-42d3-a456-426614174000"

    def fences(self):
        return {
            "resolver_sha256": "a" * 64,
            "routes_sha256": "b" * 64,
            "sshd_sha256": "c" * 64,
        }

    def validate(self):
        self.events.append("validate")
        if self.fail == "validate":
            raise self.module.Refusal("runtime-command-failed")

    def reload(self):
        self.events.append("reload")
        if self.fail == "reload":
            raise self.module.Refusal("runtime-command-failed")

    def readback(self, value):
        self.events.append(("readback", value))
        if self.fail == "readback":
            raise self.module.Refusal("runtime-readback-invalid")


@pytest.fixture
def setup(tmp_path):
    module = load()
    paths = module.Paths.for_root(tmp_path)
    for directory in (tmp_path / "etc", paths.fragment.parent, paths.state.parent):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o755)
    paths.fragment.write_bytes(fragment())
    paths.fragment.chmod(0o644)
    paths.main.write_text(
        'table inet filter { include "/etc/nftables.d/vpn-tailnet-ssh-sets.nft" }\n'
    )
    paths.main.chmod(0o644)
    runtime = FakeRuntime(module, paths)
    return module, paths, runtime, module.Transaction(runtime)


def test_prepare_apply_rollback_restores_exact_bytes_and_metadata(setup):
    _, paths, runtime, transaction = setup
    before = (
        paths.fragment.read_bytes(),
        paths.fragment.stat().st_mode & 0o777,
        paths.fragment.stat().st_uid,
        paths.fragment.stat().st_gid,
    )
    prepared = transaction.prepare(fragment("100.64.10.21/32"))
    assert str(UUID(prepared["generation"])) == prepared["generation"]
    assert (
        transaction.apply(
            prepared["generation"],
            prepared["nonce"],
            prepared["snapshot_digest"],
            prepared["deadline"],
        )["status"]
        == "applied"
    )
    assert (
        transaction.rollback(
            prepared["generation"],
            prepared["nonce"],
            prepared["snapshot_digest"],
            prepared["deadline"],
        )["status"]
        == "rolled_back"
    )
    after = (
        paths.fragment.read_bytes(),
        paths.fragment.stat().st_mode & 0o777,
        paths.fragment.stat().st_uid,
        paths.fragment.stat().st_gid,
    )
    assert after == before and runtime.events[-3:] == [
        "validate",
        "reload",
        ("readback", fragment()),
    ]


def test_confirm_revalidates_applied_graph_and_is_terminal(setup):
    module, _, _, transaction = setup
    receipt = transaction.prepare(fragment("100.64.10.22/32"))
    transaction.apply(
        receipt["generation"],
        receipt["nonce"],
        receipt["snapshot_digest"],
        receipt["deadline"],
    )
    confirmed = transaction.confirm(
        receipt["generation"],
        receipt["nonce"],
        receipt["snapshot_digest"],
        receipt["deadline"],
    )
    assert confirmed["status"] == "committed" and transaction.status() == confirmed
    with pytest.raises(module.Refusal, match="already-committed"):
        transaction.rollback(
            receipt["generation"],
            receipt["nonce"],
            receipt["snapshot_digest"],
            receipt["deadline"],
        )


@pytest.mark.parametrize("failure", ["validate", "reload", "readback"])
def test_apply_failure_never_reports_applied(setup, failure):
    module, _, runtime, transaction = setup
    receipt = transaction.prepare(fragment("100.64.10.23/32"))
    runtime.fail = failure
    with pytest.raises(
        module.Refusal, match="activation-failed-rolled-back|recovery-failed"
    ):
        transaction.apply(
            receipt["generation"],
            receipt["nonce"],
            receipt["snapshot_digest"],
            receipt["deadline"],
        )
    assert transaction.status()["status"] in {"rolled_back", "recovery_failed"}


def test_recover_rolls_back_interrupted_applying_state(setup):
    _, paths, _, transaction = setup
    before = paths.fragment.read_bytes()
    receipt = transaction.prepare(fragment("100.64.10.24/32"))
    state = transaction._load()
    state["status"] = "applying"
    transaction._save(state)
    transaction._publish(state["plan"]["after"])
    assert (
        transaction.recover()["status"] == "rolled_back"
        and paths.fragment.read_bytes() == before
    )


def test_expired_and_boot_recovery_are_fail_closed(setup):
    _, _, runtime, transaction = setup
    receipt = transaction.prepare(fragment("100.64.10.25/32"), timeout=60)
    runtime.now += 61
    runtime.mono += 61
    assert transaction.recover()["status"] == "rolled_back"
    receipt = transaction.prepare(fragment("100.64.10.26/32"), timeout=60)
    assert transaction.recover(boot=True)["status"] == "rolled_back"


def test_boot_recovery_does_not_depend_on_pre_network_fences(setup, monkeypatch):
    _, paths, runtime, transaction = setup
    before = paths.fragment.read_bytes()
    receipt = transaction.prepare(fragment("100.64.10.27/32"))
    state = transaction._load()
    state["status"] = "applying"
    transaction._save(state)
    transaction._publish(state["plan"]["after"])
    monkeypatch.setattr(
        runtime, "fences", lambda: (_ for _ in ()).throw(AssertionError("pre-network"))
    )
    assert (
        transaction.recover(boot=True)["status"] == "rolled_back"
        and paths.fragment.read_bytes() == before
    )


def test_preview_is_read_only_and_requires_installed_recovery(setup):
    module, paths, _, transaction = setup
    before = list(paths.state.parent.iterdir())
    with pytest.raises((module.Refusal, FileNotFoundError)):
        transaction.preview(fragment("100.64.10.30/32"))
    assert list(paths.state.parent.iterdir()) == before
    paths.state.mkdir(mode=0o700)
    (paths.state / "transaction.lock").write_bytes(b"")
    (paths.state / "transaction.lock").chmod(0o600)
    assert transaction.preview(fragment("100.64.10.30/32"))["status"] == "would-change"
    assert {p.name for p in paths.state.iterdir()} == {"transaction.lock"}


@pytest.mark.parametrize("kind", ["symlink", "fifo", "hardlink"])
def test_refuses_substituted_fragment_without_receipt(setup, kind, tmp_path):
    module, paths, _, transaction = setup
    original = paths.fragment.read_bytes()
    paths.fragment.unlink()
    foreign = tmp_path / "foreign"
    foreign.write_bytes(original)
    foreign.chmod(0o644)
    if kind == "symlink":
        paths.fragment.symlink_to(foreign)
    elif kind == "fifo":
        os.mkfifo(paths.fragment, 0o644)
    else:
        os.link(foreign, paths.fragment)
    with pytest.raises(module.Refusal, match="file-unavailable|file-unsafe"):
        transaction.prepare(fragment("100.64.10.31/32"))
    assert not paths.state.exists() or not (paths.state / "transaction.json").exists()


def test_tampered_receipt_refuses_without_fragment_write(setup):
    module, paths, _, transaction = setup
    before = paths.fragment.read_bytes()
    transaction.prepare(fragment("100.64.10.32/32"))
    state = paths.state / "transaction.json"
    value = json.loads(state.read_text())
    value["status"] = "applied"
    state.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    state.chmod(0o600)
    with pytest.raises(module.Refusal, match="state-invalid"):
        transaction.status()
    assert paths.fragment.read_bytes() == before


def test_initialized_without_receipt_is_recovery_debt_not_idle(setup):
    module, paths, _, transaction = setup
    paths.state.mkdir(mode=0o700)
    (paths.state / "transaction.lock").write_bytes(b"")
    (paths.state / "transaction.lock").chmod(0o600)
    (paths.state / "initialized").write_bytes(b"1\n")
    (paths.state / "initialized").chmod(0o600)
    with pytest.raises(module.Refusal, match="state-orphaned"):
        transaction.status()


def test_real_nft_json_readback_accepts_only_exact_host_elements(setup):
    module, paths, _, _ = setup

    def command(argv, timeout=15):
        name = argv[-1]
        family = 4 if name.endswith("v4") else 6
        value = "100.64.10.20" if family == 4 else "fd7a:115c:a1e0::1234"
        elem = [{"elem": {"val": value}}] if family == 4 else [value]
        return json.dumps(
            {
                "nftables": [
                    {
                        "set": {
                            "family": "inet",
                            "table": "filter",
                            "name": name,
                            "elem": elem,
                        }
                    }
                ]
            }
        ).encode()

    module.Runtime(paths, command=command).readback(fragment())

    def bad(argv, timeout=15):
        name = argv[-1]
        return json.dumps(
            {
                "nftables": [
                    {
                        "set": {
                            "family": "inet",
                            "table": "filter",
                            "name": name,
                            "elem": [{"prefix": {"addr": "100.64.10.0", "len": 24}}],
                        }
                    }
                ]
            }
        ).encode()

    with pytest.raises(module.Refusal, match="runtime-readback-invalid"):
        module.Runtime(paths, command=bad).readback(fragment())


def test_route_fence_ignores_only_volatile_route_fields(setup):
    module, paths, _, _ = setup
    paths.resolver.write_text("nameserver 192.0.2.53\n")
    paths.resolver.chmod(0o644)

    route_age = 1
    reverse = False

    def command(argv, timeout=15):
        if argv[0] == "ip":
            gateway = "192.0.2.1" if argv[1] == "-4" else "2001:db8::1"
            routes = [
                {
                    "dst": "default",
                    "gateway": gateway,
                    "dev": "tailscale0",
                    "expires": route_age,
                    "cache": {"used": route_age, "stable": "kept"},
                },
                {
                    "dst": "default",
                    "gateway": "192.0.2.2" if argv[1] == "-4" else "2001:db8::2",
                    "dev": "tailscale1",
                    "metric": 50,
                },
            ]
            if reverse:
                routes.reverse()
            return json.dumps(routes).encode()
        if argv[0] == "sshd":
            return b"port 22\n"
        raise AssertionError(argv)

    runtime = module.Runtime(paths, command=command)
    first = runtime.fences()
    route_age = 2
    reverse = True
    assert runtime.fences() == first

    original = command

    def changed(argv, timeout=15):
        output = original(argv, timeout)
        if argv[:2] == ["ip", "-4"]:
            value = json.loads(output)
            value[0]["gateway"] = "192.0.2.254"
            return json.dumps(value).encode()
        return output

    assert (
        module.Runtime(paths, command=changed).fences()["routes_sha256"]
        != first["routes_sha256"]
    )


def test_runtime_timeout_reclaims_descendant_process_group(tmp_path):
    module = load()
    marker = tmp_path / "descendant-survived"
    child = (
        "import pathlib,time;"
        "time.sleep(0.6);"
        f"pathlib.Path({str(marker)!r}).write_text('survived')"
    )
    parent = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',{child!r}]);"
        "time.sleep(5)"
    )

    with pytest.raises(module.Refusal, match="runtime-command-failed"):
        module.Runtime._command([sys.executable, "-c", parent], timeout=0.1)

    time.sleep(0.8)
    assert not marker.exists()


def test_cli_damaged_state_returns_only_categorical_json():
    program = (
        "import runpy,sys;"
        "from unittest.mock import patch;"
        f"sys.argv=[{str(SCRIPT)!r},'status'];"
        "guard=patch('os.open',side_effect=OSError('fixture'));"
        "guard.start();"
        f"runpy.run_path({str(SCRIPT)!r},run_name='__main__')"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        input=b"{}",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout) == {"error": "filesystem-unavailable"}
    assert result.stderr == b""


def test_short_write_loop_never_publishes_partial_receipt(setup, monkeypatch):
    module, paths, _, transaction = setup
    original = module.os.write
    first = True

    def short(fd, value):
        nonlocal first
        if first and len(value) > 1:
            first = False
            return original(fd, value[:-1])
        return original(fd, value)

    monkeypatch.setattr(module.os, "write", short)
    transaction.prepare(fragment("100.64.10.33/32"))
    assert (
        json.loads((paths.state / "transaction.json").read_text())["status"]
        == "prepared"
    )


def test_fragment_drift_refuses_apply_and_preserves_foreign_bytes(setup):
    module, paths, _, transaction = setup
    receipt = transaction.prepare(fragment("100.64.10.34/32"))
    foreign = fragment("100.64.10.99/32")
    paths.fragment.write_bytes(foreign)
    paths.fragment.chmod(0o644)
    with pytest.raises(module.Refusal, match="configuration-drift"):
        transaction.apply(
            receipt["generation"],
            receipt["nonce"],
            receipt["snapshot_digest"],
            receipt["deadline"],
        )
    assert paths.fragment.read_bytes() == foreign


def test_cli_contract_and_safe_error_surface_are_fixed():
    source = SCRIPT.read_text()
    for action in (
        "prepare",
        "preview",
        "apply",
        "status",
        "confirm",
        "rollback",
        "recover",
        "boot-recover",
    ):
        assert f'"{action}"' in source
    assert "stderr=subprocess.DEVNULL" in source and "request-too-large" in source


def test_firewall_role_installs_persistent_fail_closed_recovery_units():
    tasks = (ROOT / "ansible/roles/firewall/tasks/main.yml").read_text()
    assert (
        "tailnet-network-guest.py" in tasks and "/var/lib/vpn-tailnet-network" in tasks
    )
    boot = (
        ROOT / "ansible/roles/firewall/files/vpn-tailnet-network-boot-recover.service"
    ).read_text()
    worker = (
        ROOT / "ansible/roles/firewall/files/vpn-tailnet-network-recover.service"
    ).read_text()
    timer = (
        ROOT / "ansible/roles/firewall/files/vpn-tailnet-network-recover.timer"
    ).read_text()
    assert (
        "Before=nftables.service network-pre.target" in boot
        and "RequiredBy=nftables.service" in boot
        and "boot-recover" in boot
    )
    assert (
        "SuccessExitStatus=75" in worker
        and "ReadWritePaths=/etc/nftables.d /var/lib/vpn-tailnet-network" in worker
    )
    assert "Persistent=true" in timer and "OnUnitActiveSec=30s" in timer
    required = tasks.split("- name: Install exact nftables boot recovery requirement", 1)[1]
    required = required.split("- name:", 1)[0]
    # A rerun after a partial unit upgrade has no copy change to key from: the
    # exact link must still self-heal independently.
    assert "state: link" in required
    assert (
        "dest: /etc/systemd/system/nftables.service.requires/"
        "vpn-tailnet-network-boot-recover.service" in required
    )
    assert "_firewall_tailnet_recovery_units.changed" not in required
    reload = tasks.split("- name: Reload systemd after Tailnet recovery dependency changes", 1)[1]
    reload = reload.split("- name:", 1)[0]
    assert "_firewall_tailnet_boot_required_by.changed" in reload
    assert tasks.index("- name: Install exact nftables boot recovery requirement") < tasks.index(
        "- name: Reload systemd after Tailnet recovery dependency changes"
    ) < tasks.index("- name: Enable persistent Tailnet firewall recovery")
