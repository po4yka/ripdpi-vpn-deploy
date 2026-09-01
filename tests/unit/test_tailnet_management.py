"""Contract tests for opt-in ordinary OpenSSH over Tailscale."""

from __future__ import annotations

import importlib.util
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import subprocess

import pytest
import yaml

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "tailnet_management.py"
ROLE = ROOT / "ansible" / "roles" / "tailnet-management"


def _load_controller():
    spec = importlib.util.spec_from_file_location(
        "tailnet_management_controller", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tailnet_role_is_opt_in_tactical_and_wired_after_geodata() -> None:
    defaults = yaml.safe_load((ROOT / "ansible/group_vars/all.yml").read_text())
    tiers = yaml.safe_load((ROOT / "ansible/role-tiers.yml").read_text())
    site = yaml.safe_load((ROOT / "ansible/playbooks/site.yml").read_text())[0]
    roles = [entry["role"] for entry in site["roles"]]

    assert defaults["vpn"]["enable_tailnet_management"] is False
    assert tiers["tiers"]["tailnet-management"] == "tactical"
    assert tiers["toggle_role_map"]["enable_tailnet_management"] == "tailnet-management"
    assert roles.index("firewall") < roles.index("tailnet-management")
    assert roles.index("tailnet-management") == roles.index("geodata") + 1
    assert roles.index("tailnet-management") < roles.index("xray")


def test_live_fleet_profiles_enable_only_reviewed_tailnet_management_sources() -> None:
    group_vars = ROOT / "ansible" / "group_vars"
    defaults = yaml.safe_load((group_vars / "all.yml").read_text())
    approved_sources = defaults["tailnet_management"]["approved_sources"]
    controller = _load_controller()

    assert controller.validate_sources(approved_sources) == approved_sources
    assert len(approved_sources) == 2

    enabled_profiles = {
        "vpn-p0-self-steal.yml",
        "vpn-p1-web.yml",
        "vpn-p2-udp.yml",
    }
    for path in sorted(group_vars.glob("vpn-*.yml")):
        document = yaml.safe_load(path.read_text()) or {}
        enabled = document.get("vpn", {}).get("enable_tailnet_management", False)
        assert enabled is (path.name in enabled_profiles), path.name


def test_tailnet_operator_scripts_have_one_job_and_install_durable_recovery() -> None:
    scripts = ROOT / "scripts"
    tasks = (ROLE / "tasks/main.yml").read_text()
    service = (ROLE / "templates/vpn-tailnet-recover.service.j2").read_text()
    timer = (ROLE / "templates/vpn-tailnet-recover.timer.j2").read_text()

    for name in (
        "tailnet-configure.py",
        "tailnet-check.py",
        "tailnet-recover.py",
        "tailnet-validate-sources.py",
    ):
        assert (scripts / name).is_file()
        assert name in tasks
    assert "tailnet-management-controller.py" not in tasks
    assert "After=tailscaled.service" in service
    assert (
        "ExecStart=/usr/bin/python3 /usr/local/lib/vpn-tailnet/tailnet-recover.py"
        in service
    )
    assert "Persistent=true" in timer
    assert "RestrictAddressFamilies=AF_UNIX AF_NETLINK" in service
    assert "RuntimeDirectory=vpn-tailnet-management" in service
    assert "RuntimeDirectoryMode=0700" in service
    assert "RuntimeDirectoryPreserve=yes" in service
    assert "Before=ssh.service ssh.socket" in service
    assert "RequiredBy=ssh.service ssh.socket" in service
    assert "ConditionPathExists=" not in service
    assert "SuccessExitStatus=" not in service
    assert (
        "ReadWritePaths=/var/lib/vpn-tailnet-management /run/vpn-tailnet-management"
        in service
    )
    assert 'auth_directory=Path("/run/vpn-tailnet-management")' in SCRIPT.read_text()
    assert "enabled: true" in tasks and "vpn-tailnet-recover.timer" in tasks


def test_tailnet_molecule_uses_the_published_image_architecture() -> None:
    scenario = yaml.safe_load((ROLE / "molecule/default/molecule.yml").read_text())
    assert scenario["platforms"][0]["platform"] == "linux/amd64"


def test_firewall_allows_only_exact_approved_tailnet_sources() -> None:
    variables = merge_render_vars()
    variables["vpn"] = {**variables["vpn"], "enable_tailnet_management": True}
    variables["tailnet_management"] = {
        "approved_sources": ["100.64.10.20", "fd7a:115c:a1e0::1234"],
    }
    variables["firewall_effective_ssh_ports"] = [22022]
    variables["allowed_ssh_cidrs"] = ["0.0.0.0/0", "::/0"]
    variables["public_listener_contract"] = []
    rendered = render_template(
        ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", variables
    )

    assert (
        'iifname "tailscale0" tcp dport 22022 ip saddr '
        "@vpn_tailnet_ssh_v4 accept" in rendered
    )
    assert (
        'iifname "tailscale0" tcp dport 22022 ip6 saddr '
        "@vpn_tailnet_ssh_v6 accept" in rendered
    )
    # Reviewed sources are transaction-owned fragment data. The baseline
    # template must never interpolate them into the main ruleset directly.
    assert "100.64.10.20" not in rendered
    assert "fd7a:115c:a1e0::1234" not in rendered
    assert 'iifname "tailscale0" accept' not in rendered
    tailnet_drop = 'iifname "tailscale0" tcp dport 22022 drop'
    public_v4 = "tcp dport 22022 ip saddr { 0.0.0.0/0 } accept"
    public_v6 = "tcp dport 22022 ip6 saddr { ::/0 } accept"
    assert rendered.index("@vpn_tailnet_ssh_v4 accept") < rendered.index(tailnet_drop)
    assert rendered.index("@vpn_tailnet_ssh_v6 accept") < rendered.index(tailnet_drop)
    assert rendered.index(tailnet_drop) < rendered.index(public_v4)
    assert rendered.index(tailnet_drop) < rendered.index(public_v6)
    assert 'iifname != "tailscale0"' not in rendered

    disabled = merge_render_vars()
    disabled["vpn"] = {**disabled["vpn"], "enable_tailnet_management": False}
    disabled["allowed_ssh_cidrs"] = ["0.0.0.0/0", "::/0"]
    disabled["firewall_effective_ssh_ports"] = [22022]
    disabled["public_listener_contract"] = []
    disabled_rendered = render_template(
        ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", disabled
    )
    assert tailnet_drop in disabled_rendered
    assert 'iifname "tailscale0" tcp dport 22022 ip saddr' not in disabled_rendered

    firewall_tasks = yaml.safe_load(
        (ROOT / "ansible/roles/firewall/tasks/main.yml").read_text()
    )
    validator = next(
        task
        for task in firewall_tasks
        if task["name"] == "Validate Tailnet firewall sources before mutation"
    )
    assert validator["name"] == "Validate Tailnet firewall sources before mutation"
    assert validator["delegate_to"] == "localhost"
    assert "vpn.enable_tailnet_management" in validator["when"]
    assert "tailnet-validate-sources.py" in validator["ansible.builtin.command"]["cmd"]


@pytest.mark.parametrize(
    "sources",
    [
        [],
        ["100.64.1.2/32"],
        ["100.64.1.2", "100.64.1.2"],
        ["192.0.2.10"],
        ["fd00::1"],
        ["not-an-ip"],
    ],
)
def test_source_validation_rejects_non_exact_or_non_tailnet_addresses(sources) -> None:
    controller = _load_controller()
    with pytest.raises(controller.Refusal):
        controller.validate_sources(sources)


def test_source_validation_accepts_exact_v4_and_v6_tailnet_addresses() -> None:
    controller = _load_controller()
    assert controller.validate_sources(["100.64.1.2", "fd7a:115c:a1e0::1234"]) == [
        "100.64.1.2",
        "fd7a:115c:a1e0::1234",
    ]


class FakeRunner:
    def __init__(
        self,
        root: Path,
        *,
        drift: str | None = None,
        preference_mismatch: bool = False,
        tailscale_firewall: bool = False,
        stopped: bool = False,
        volatile_routes: bool = False,
        login_failure_after_enrollment: bool = False,
        recovery_status: int = 0,
        recovery_recheck_status: int | None = None,
    ) -> None:
        self.root = root
        self.drift = drift
        self.preference_mismatch = preference_mismatch
        self.tailscale_firewall = tailscale_firewall
        self.stopped = stopped
        self.volatile_routes = volatile_routes
        self.login_failure_after_enrollment = login_failure_after_enrollment
        self.recovery_status = recovery_status
        self.recovery_recheck_status = recovery_recheck_status
        self.recovery_show_calls = 0
        self.route_reads = 0
        self.running = False
        self.calls: list[list[str]] = []
        self.auth_file_mode: int | None = None
        self.auth_file_bytes: bytes | None = None
        self.transaction_mode: int | None = None
        self.transaction_bytes: bytes | None = None

    def __call__(self, argv: list[str], *, timeout: int):
        self.calls.append(argv)
        command = argv[1:]
        stdout = ""
        if command == ["status", "--json"]:
            backend = (
                "Running"
                if self.running
                else "Stopped" if self.stopped else "NeedsLogin"
            )
            stdout = json.dumps({"BackendState": backend})
        elif command == ["get", "--json", "all"]:
            preferences = {
                "accept-dns": False,
                "accept-routes": False,
                "advertise-exit-node": False,
                "advertise-routes": [],
                "exit-node": "",
                "netfilter-mode": "off",
                "shields-up": False,
                "ssh": False,
            }
            if self.preference_mismatch:
                preferences["accept-routes"] = True
            stdout = json.dumps(preferences)
        elif command[:1] == ["login"]:
            auth_arg = next(
                item for item in command if item.startswith("--auth-key=file:")
            )
            auth_path = Path(auth_arg.removeprefix("--auth-key=file:"))
            self.auth_file_mode = auth_path.stat().st_mode & 0o777
            self.auth_file_bytes = auth_path.read_bytes()
            transaction = self.root / "transaction.json"
            self.transaction_mode = transaction.stat().st_mode & 0o777
            self.transaction_bytes = transaction.read_bytes()
            self.running = True
            if self.login_failure_after_enrollment:
                raise subprocess.TimeoutExpired(argv, timeout)
        elif command == ["ip", "-4"]:
            stdout = "100.64.1.9\n"
        elif command == ["ip", "-6"]:
            stdout = "fd7a:115c:a1e0::9\n"
        elif argv[0].endswith("ip") and command == [
            "-json",
            "address",
            "show",
            "dev",
            "tailscale0",
        ]:
            addresses = [] if self.drift == "tailnet-interface" else [
                {"local": "100.64.1.9"},
                {"local": "fd7a:115c:a1e0::9"},
            ]
            stdout = json.dumps([{"ifname": "tailscale0", "addr_info": addresses}])
        elif argv[0].endswith("sshd") and command == ["-T"]:
            stdout = "port 22022\nhostkey /etc/ssh/ssh_host_ed25519_key\n"
            if self.drift == "sshd" and self.running:
                stdout = "port 22\nhostkey /etc/ssh/ssh_host_ed25519_key\n"
        elif argv[0].endswith("ip") and command == [
            "-4",
            "-json",
            "route",
            "show",
            "default",
        ]:
            self.route_reads += 1
            expires = (
                f',"expires":{100 - self.route_reads}' if self.volatile_routes else ""
            )
            stdout = (
                '[{"dst":"default","gateway":"192.0.2.1","dev":"eth0"'
                + expires
                + "}]\n"
            )
            if self.drift == "route-v4" and self.running:
                stdout = '[{"dst":"default","gateway":"192.0.2.2","dev":"eth0"}]\n'
        elif argv[0].endswith("ip") and command == [
            "-6",
            "-json",
            "route",
            "show",
            "default",
        ]:
            self.route_reads += 1
            expires = (
                f',"expires":{100 - self.route_reads}' if self.volatile_routes else ""
            )
            stdout = (
                '[{"dst":"default","gateway":"2001:db8::1","dev":"eth0"'
                + expires
                + "}]\n"
            )
            if self.drift == "route-v6" and self.running:
                stdout = '[{"dst":"default","gateway":"2001:db8::2","dev":"eth0"}]\n'
        elif argv[0].endswith("nft") and command == ["-j", "list", "chains"]:
            stdout = (
                '{"nftables":[{"chain":{"name":"ts-input"}}]}'
                if self.tailscale_firewall
                else '{"nftables":[]}'
            )
        elif command == ["logout"]:
            self.running = False
        elif argv[0].endswith("systemctl") and command in (
            ["is-enabled", "vpn-tailnet-recover.timer"],
            ["is-active", "vpn-tailnet-recover.timer"],
        ):
            pass
        elif argv[0].endswith("systemctl") and command == [
            "start",
            "vpn-tailnet-recover.service",
        ]:
            pass
        elif argv[0].endswith("systemctl") and command == [
            "show",
            "vpn-tailnet-recover.service",
            "--property=Result",
            "--property=ExecMainCode",
            "--property=ExecMainStatus",
            "--no-pager",
        ]:
            self.recovery_show_calls += 1
            status = (
                self.recovery_recheck_status
                if self.recovery_show_calls > 1
                and self.recovery_recheck_status is not None
                else self.recovery_status
            )
            stdout = (
                "Result=success\nExecMainCode=1\n"
                f"ExecMainStatus={status}\n"
            )
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, 0, stdout, "")


def _paths(controller, root: Path):
    return controller.CommandPaths(
        tailscale="/fixture/tailscale",
        sshd="/fixture/sshd",
        ip="/fixture/ip",
        nft="/fixture/nft",
        resolv_conf=root / "resolv.conf",
        auth_directory=root,
        state_directory=root,
        systemctl="/fixture/systemctl",
    )


def test_fresh_enrollment_uses_private_auth_file_and_preserves_host_policy(
    tmp_path,
) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path)

    result = controller.configure(
        paths=_paths(controller, tmp_path),
        runner=runner,
        auth_key="tskey-auth-fixture_1234",
    )

    assert result == {"status": "configured", "changed": True}
    assert runner.auth_file_mode == 0o600
    assert runner.auth_file_bytes == b"tskey-auth-fixture_1234\n"
    assert runner.transaction_mode == 0o600
    assert b"tskey-auth" not in runner.transaction_bytes
    assert not (tmp_path / "transaction.json").exists()
    assert not list(tmp_path.glob("vpn-tailnet-auth-*"))
    login = next(call for call in runner.calls if call[1:2] == ["login"])
    assert "tskey-auth-fixture_1234" not in " ".join(login)
    assert {
        "--accept-dns=false",
        "--accept-routes=false",
        "--advertise-exit-node=false",
        "--advertise-routes=",
        "--exit-node=",
        "--netfilter-mode=off",
        "--shields-up=false",
        "--ssh=false",
    }.issubset(login)


def test_failed_login_is_treated_as_potentially_enrolled_and_rolled_back(
    tmp_path,
) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path, login_failure_after_enrollment=True)

    with pytest.raises(controller.Refusal, match="tailnet-enrollment-failed"):
        controller.configure(
            paths=_paths(controller, tmp_path),
            runner=runner,
            auth_key="tskey-auth-fixture_1234",
        )

    assert runner.running is False
    assert any(call[1:] == ["logout"] for call in runner.calls)
    assert not (tmp_path / "transaction.json").exists()


def test_stopped_authenticated_state_refuses_before_enrollment_mutation(
    tmp_path,
) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path, stopped=True)

    with pytest.raises(controller.Refusal, match="tailnet-existing-state-unsupported"):
        controller.configure(
            paths=_paths(controller, tmp_path),
            runner=runner,
            auth_key="tskey-auth-fixture_1234",
        )

    assert not any(call[1:2] in (["login"], ["logout"]) for call in runner.calls)
    assert not (tmp_path / "transaction.json").exists()


def test_check_refuses_stopped_authenticated_state_without_mutation(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path, stopped=True)

    with pytest.raises(controller.Refusal, match="tailnet-existing-state-unsupported"):
        controller.check(paths=_paths(controller, tmp_path), runner=runner)

    assert not any(call[1:2] in (["login"], ["logout"]) for call in runner.calls)


def test_volatile_route_lifetimes_do_not_look_like_policy_drift(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path, volatile_routes=True)

    result = controller.configure(
        paths=_paths(controller, tmp_path),
        runner=runner,
        auth_key="tskey-auth-fixture_1234",
    )

    assert result == {"status": "configured", "changed": True}
    assert runner.running is True


class PersistentRunner(FakeRunner):
    @property
    def marker(self) -> Path:
        return self.root / "tailnet-running"

    def __call__(self, argv: list[str], *, timeout: int):
        command = argv[1:]
        self.running = self.marker.exists()
        result = super().__call__(argv, timeout=timeout)
        if command[:1] == ["login"]:
            self.marker.write_text("running")
        elif command == ["logout"]:
            self.marker.unlink(missing_ok=True)
        return result


def _crash_after_login(root: str) -> None:
    controller = _load_controller()

    class CrashRunner(PersistentRunner):
        def __call__(self, argv: list[str], *, timeout: int):
            result = super().__call__(argv, timeout=timeout)
            if argv[1:2] == ["login"]:
                os._exit(86)
            return result

    path = Path(root)
    controller.configure(
        paths=_paths(controller, path),
        runner=CrashRunner(path),
        auth_key="tskey-auth-fixture_1234",
    )


def _crash_after_confirmation(root: str) -> None:
    controller = _load_controller()
    path = Path(root)

    def crash_before_receipt_cleanup(_paths, *, phase: str) -> None:
        assert phase == "confirmed"
        os._exit(87)

    controller._remove_transaction = crash_before_receipt_cleanup
    controller.configure(
        paths=_paths(controller, path),
        runner=PersistentRunner(path),
        auth_key="tskey-auth-fixture_1234",
    )


def test_process_death_after_login_is_recovered_from_durable_state(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    process = multiprocessing.get_context("fork").Process(
        target=_crash_after_login, args=(str(tmp_path),)
    )
    process.start()
    process.join(10)

    assert process.exitcode == 86
    assert (tmp_path / "tailnet-running").exists()
    transaction = tmp_path / "transaction.json"
    assert transaction.exists() and transaction.stat().st_mode & 0o777 == 0o600
    receipt = json.loads(transaction.read_text())
    auth_files = list(tmp_path.glob("vpn-tailnet-auth-*"))
    assert [path.name for path in auth_files] == [receipt["auth_file"]]
    assert auth_files[0].read_bytes() == b"tskey-auth-fixture_1234\n"

    result = controller.recover(
        paths=_paths(controller, tmp_path), runner=PersistentRunner(tmp_path)
    )

    assert result == {"status": "rolled_back", "changed": True}
    assert not transaction.exists()
    assert not (tmp_path / "tailnet-running").exists()
    assert not list(tmp_path.glob("vpn-tailnet-auth-*"))
    assert controller.recover(
        paths=_paths(controller, tmp_path), runner=PersistentRunner(tmp_path)
    ) == {"status": "idle", "changed": False}


def test_process_death_after_confirmation_never_rolls_back_enrollment(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    process = multiprocessing.get_context("fork").Process(
        target=_crash_after_confirmation, args=(str(tmp_path),)
    )
    process.start()
    process.join(10)

    assert process.exitcode == 87
    assert (tmp_path / "tailnet-running").exists()
    assert (
        json.loads((tmp_path / "transaction.json").read_text())["phase"] == "confirmed"
    )

    result = controller.recover(
        paths=_paths(controller, tmp_path), runner=PersistentRunner(tmp_path)
    )

    assert result == {"status": "confirmed", "changed": True}
    assert (tmp_path / "tailnet-running").exists()
    assert not (tmp_path / "transaction.json").exists()


def test_corrupt_recovery_state_refuses_without_tailnet_mutation(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    transaction = tmp_path / "transaction.json"
    transaction.write_text('{"schema_version":999}\n')
    transaction.chmod(0o600)
    runner = PersistentRunner(tmp_path)
    runner.marker.write_text("running")

    with pytest.raises(controller.Refusal, match="tailnet-recovery-state-invalid"):
        controller.recover(paths=_paths(controller, tmp_path), runner=runner)

    assert transaction.exists()
    assert runner.marker.exists()
    assert not any(call[1:] == ["logout"] for call in runner.calls)


def test_recovery_receipt_uses_one_serialized_write_and_read_bound(tmp_path) -> None:
    controller = _load_controller()
    paths = _paths(controller, tmp_path)
    snapshot = controller.SystemSnapshot(
        resolver=b"r" * 100_000,
        routes=b"t" * 100_000,
        sshd=b"s" * 100_000,
        resolver_mode=0o644,
        resolver_uid=os.geteuid(),
        resolver_gid=os.getegid(),
    )

    controller._write_transaction(
        paths,
        backend_state="NeedsLogin",
        snapshot=snapshot,
        auth_file="vpn-tailnet-auth-0123456789abcdef0123456789abcdef",
    )

    _receipt, recovered = controller._read_transaction(paths)
    assert recovered == snapshot
    assert (tmp_path / "transaction.json").stat().st_size > 262_144


def test_oversized_recovery_receipt_refuses_before_publication(tmp_path) -> None:
    controller = _load_controller()
    snapshot = controller.SystemSnapshot(
        resolver=b"r" * 262_144,
        routes=b"t" * 262_144,
        sshd=b"s" * 262_144,
        resolver_mode=0o644,
        resolver_uid=os.geteuid(),
        resolver_gid=os.getegid(),
    )

    with pytest.raises(controller.Refusal, match="tailnet-recovery-state-write-failed"):
        controller._write_transaction(
            _paths(controller, tmp_path),
            backend_state="NeedsLogin",
            snapshot=snapshot,
            auth_file="vpn-tailnet-auth-0123456789abcdef0123456789abcdef",
        )

    assert not (tmp_path / "transaction.json").exists()


def test_recovery_receipt_reserves_confirmed_phase_growth_before_arming(
    tmp_path, monkeypatch
) -> None:
    controller = _load_controller()
    paths = _paths(controller, tmp_path)
    snapshot = controller.SystemSnapshot(
        resolver=b"resolver",
        routes=b"routes",
        sshd=b"sshd",
        resolver_mode=0o644,
        resolver_uid=os.geteuid(),
        resolver_gid=os.getegid(),
    )
    value = {
        "schema_version": 1,
        "generation": controller.RECOVERY_GENERATION,
        "nonce": "0" * 32,
        "phase": "armed",
        "original_backend_state": "NeedsLogin",
        "auth_file": "vpn-tailnet-auth-0123456789abcdef0123456789abcdef",
        "snapshot": controller._snapshot_document(snapshot),
    }
    armed_size = len(controller._canonical_bytes(value))
    confirmed_size = len(controller._canonical_bytes({**value, "phase": "confirmed"}))
    assert confirmed_size > armed_size
    monkeypatch.setattr(controller, "RECOVERY_STATE_MAX_BYTES", armed_size)

    with pytest.raises(controller.Refusal, match="tailnet-recovery-state-write-failed"):
        controller._write_transaction(
            paths,
            backend_state="NeedsLogin",
            snapshot=snapshot,
            auth_file=value["auth_file"],
        )

    assert not (tmp_path / "transaction.json").exists()


def test_confirmation_rechecks_receipt_limit_before_replacement(
    tmp_path, monkeypatch
) -> None:
    controller = _load_controller()
    paths = _paths(controller, tmp_path)
    snapshot = controller.SystemSnapshot(
        resolver=b"resolver",
        routes=b"routes",
        sshd=b"sshd",
        resolver_mode=0o644,
        resolver_uid=os.geteuid(),
        resolver_gid=os.getegid(),
    )
    controller._write_transaction(
        paths,
        backend_state="NeedsLogin",
        snapshot=snapshot,
        auth_file="vpn-tailnet-auth-0123456789abcdef0123456789abcdef",
    )
    receipt = tmp_path / "transaction.json"
    armed = receipt.read_bytes()
    monkeypatch.setattr(controller, "RECOVERY_STATE_MAX_BYTES", len(armed) + 3)

    with pytest.raises(controller.Refusal, match="tailnet-recovery-confirm-uncertain"):
        controller._mark_transaction_confirmed(paths)

    assert receipt.read_bytes() == armed


def test_confirmation_directory_fsync_ambiguity_retains_recovery_evidence(
    tmp_path, monkeypatch
) -> None:
    controller = _load_controller()
    paths = _paths(controller, tmp_path)
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path)
    original_fsync = controller._fsync_directory
    failures = 0

    def fail_confirmation_and_recovery_fsync(path):
        nonlocal failures
        receipt = tmp_path / "transaction.json"
        if failures < 2 and receipt.exists():
            value = json.loads(receipt.read_text())
            if value["phase"] == "confirmed":
                failures += 1
                raise OSError("fixture confirmation directory fsync failure")
        return original_fsync(path)

    monkeypatch.setattr(
        controller, "_fsync_directory", fail_confirmation_and_recovery_fsync
    )
    with pytest.raises(controller.Refusal, match="tailnet-rollback-uncertain"):
        controller.configure(
            paths=paths,
            runner=runner,
            auth_key="tskey-auth-fixture_1234",
        )

    assert failures == 2
    assert runner.running is True
    receipt = tmp_path / "transaction.json"
    assert receipt.exists()
    assert json.loads(receipt.read_text())["phase"] == "confirmed"

    monkeypatch.setattr(controller, "_fsync_directory", original_fsync)
    assert controller.recover(paths=paths, runner=runner) == {
        "status": "confirmed",
        "changed": True,
    }
    assert not receipt.exists()
    assert runner.running is True


def test_interrupted_transaction_link_is_reconciled_before_recovery(tmp_path) -> None:
    controller = _load_controller()
    paths = _paths(controller, tmp_path)
    snapshot = controller.SystemSnapshot(
        resolver=b"resolver",
        routes=b"routes",
        sshd=b"sshd",
        resolver_mode=0o644,
        resolver_uid=os.geteuid(),
        resolver_gid=os.getegid(),
    )
    controller._write_transaction(
        paths,
        backend_state="NeedsLogin",
        snapshot=snapshot,
        auth_file="vpn-tailnet-auth-0123456789abcdef0123456789abcdef",
    )
    receipt = tmp_path / "transaction.json"
    value = json.loads(receipt.read_text())
    interrupted = tmp_path / f".transaction.json.{value['nonce']}"
    os.link(receipt, interrupted)
    assert receipt.stat().st_nlink == 2

    recovered, recovered_snapshot = controller._read_transaction(paths)

    assert recovered == value
    assert recovered_snapshot == snapshot
    assert receipt.stat().st_nlink == 1
    assert not interrupted.exists()


def test_armed_receipt_unlink_fsync_failure_remains_uncertain(
    tmp_path, monkeypatch
) -> None:
    controller = _load_controller()
    paths = _paths(controller, tmp_path)
    snapshot = controller.SystemSnapshot(
        resolver=b"resolver",
        routes=b"routes",
        sshd=b"sshd",
        resolver_mode=0o644,
        resolver_uid=os.geteuid(),
        resolver_gid=os.getegid(),
    )
    controller._write_transaction(
        paths,
        backend_state="NeedsLogin",
        snapshot=snapshot,
        auth_file="vpn-tailnet-auth-0123456789abcdef0123456789abcdef",
    )

    def fail_directory_fsync(_path):
        raise OSError("fixture directory fsync failure")

    monkeypatch.setattr(controller, "_fsync_directory", fail_directory_fsync)
    with pytest.raises(
        controller.Refusal, match="tailnet-recovery-state-cleanup-failed"
    ):
        controller._remove_transaction(paths, phase="armed")

    assert not (tmp_path / "transaction.json").exists()


def test_stopped_state_during_armed_recovery_retains_evidence_without_logout(
    tmp_path,
) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    paths = _paths(controller, tmp_path)
    runner = FakeRunner(tmp_path, stopped=True)
    controller._write_transaction(
        paths,
        backend_state="NeedsLogin",
        snapshot=controller._snapshot(paths, runner),
        auth_file="vpn-tailnet-auth-0123456789abcdef0123456789abcdef",
    )

    with pytest.raises(controller.Refusal, match="tailnet-rollback-uncertain"):
        controller.recover(paths=paths, runner=runner)

    assert (tmp_path / "transaction.json").exists()
    assert not any(call[1:] == ["logout"] for call in runner.calls)


def test_periodic_recovery_defers_while_controller_holds_lock(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    lock = tmp_path / "transaction.lock"
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    fd = os.open(lock, os.O_RDWR)
    runner = PersistentRunner(tmp_path)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(controller.Busy, match="tailnet-recovery-busy"):
            controller.recover(paths=_paths(controller, tmp_path), runner=runner)
    finally:
        os.close(fd)

    assert runner.calls == []


def test_missing_key_refuses_before_login(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path)

    with pytest.raises(controller.Refusal, match="tailnet-auth-required"):
        controller.configure(
            paths=_paths(controller, tmp_path), runner=runner, auth_key=""
        )

    assert not any(call[1:2] == ["login"] for call in runner.calls)


def test_recovery_worker_must_execute_before_arming(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path, recovery_status=75)

    with pytest.raises(controller.Refusal, match="tailnet-recovery-unavailable"):
        controller.configure(
            paths=_paths(controller, tmp_path),
            runner=runner,
            auth_key="tskey-auth-fixture_1234",
        )

    assert not (tmp_path / "transaction.json").exists()
    assert not any(call[1:2] == ["login"] for call in runner.calls)


def test_recovery_worker_proof_is_revalidated_under_transaction_lock(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path, recovery_recheck_status=75)

    with pytest.raises(controller.Refusal, match="tailnet-recovery-unavailable"):
        controller.configure(
            paths=_paths(controller, tmp_path),
            runner=runner,
            auth_key="tskey-auth-fixture_1234",
        )

    assert runner.recovery_show_calls == 2
    assert not (tmp_path / "transaction.json").exists()
    assert not any(call[1:2] == ["login"] for call in runner.calls)


@pytest.mark.parametrize(
    "auth_key",
    ["fixture", "tskey-auth-short", "tskey-auth-fixture_12345678\nextra"],
)
def test_non_auth_key_material_refuses_before_login(tmp_path, auth_key) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path)

    with pytest.raises(controller.Refusal, match="tailnet-auth-required"):
        controller.configure(
            paths=_paths(controller, tmp_path), runner=runner, auth_key=auth_key
        )

    assert not any(call[1:2] == ["login"] for call in runner.calls)


def test_check_mode_predicts_enrollment_without_login(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path)

    assert controller.check(paths=_paths(controller, tmp_path), runner=runner) == {
        "status": "pending",
        "changed": True,
    }
    assert not any(call[1:2] in (["login"], ["logout"]) for call in runner.calls)


def test_check_mode_accepts_existing_exact_configuration_without_key(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path)
    runner.running = True

    assert controller.check(paths=_paths(controller, tmp_path), runner=runner) == {
        "status": "configured",
        "changed": False,
    }
    assert not any(call[1:2] in (["login"], ["logout"]) for call in runner.calls)


@pytest.mark.parametrize("drift", ["route-v4", "route-v6"])
def test_post_enrollment_route_drift_logs_out_and_reports_no_sensitive_state(
    tmp_path, drift
) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path, drift=drift)

    with pytest.raises(controller.Refusal, match="tailnet-routing-drift") as error:
        controller.configure(
            paths=_paths(controller, tmp_path),
            runner=runner,
            auth_key="tskey-auth-fixture_1234",
        )

    assert runner.running is False
    assert "tskey" not in str(error.value)
    assert not list(tmp_path.glob("vpn-tailnet-auth-*"))


def test_tailscale_owned_firewall_state_is_rejected_and_rolled_back(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path, tailscale_firewall=True)

    with pytest.raises(controller.Refusal, match="tailnet-rollback-uncertain"):
        controller.configure(
            paths=_paths(controller, tmp_path),
            runner=runner,
            auth_key="tskey-auth-fixture_1234",
        )

    assert runner.running is False
    assert not list(tmp_path.glob("vpn-tailnet-auth-*"))


def test_existing_mismatched_tailnet_refuses_without_mutation(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path, preference_mismatch=True)
    runner.running = True

    with pytest.raises(controller.Refusal, match="tailnet-preferences-mismatch"):
        controller.configure(
            paths=_paths(controller, tmp_path),
            runner=runner,
            auth_key="tskey-auth-fixture_1234",
        )

    assert not any(call[1:2] in (["login"], ["logout"]) for call in runner.calls)


def test_missing_tailscale0_addresses_rolls_back_enrollment(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path, drift="tailnet-interface")

    with pytest.raises(controller.Refusal, match="tailnet-address-invalid"):
        controller.configure(
            paths=_paths(controller, tmp_path),
            runner=runner,
            auth_key="tskey-auth-fixture_1234",
        )

    assert runner.running is False
    assert not (tmp_path / "transaction.json").exists()


def test_auth_file_cleanup_failure_is_not_hidden(tmp_path, monkeypatch) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path)

    def fail_cleanup(_path):
        raise controller.Refusal("tailnet-auth-file-cleanup-failed")

    monkeypatch.setattr(controller, "_remove_auth_file", fail_cleanup)
    with pytest.raises(controller.Refusal, match="tailnet-auth-file-cleanup-failed"):
        controller.configure(
            paths=_paths(controller, tmp_path),
            runner=runner,
            auth_key="tskey-auth-fixture_1234",
        )


def test_role_never_puts_auth_key_in_command_or_inventory() -> None:
    tasks = (ROLE / "tasks/main.yml").read_text()
    defaults = (ROLE / "defaults/main.yml").read_text()
    site = (ROOT / "ansible/playbooks/site.yml").read_text()

    assert "TAILSCALE_AUTH_KEY" in tasks
    assert "stdin:" in tasks
    assert "no_log: true" in tasks
    assert "--auth-key" not in tasks
    assert "auth_key" not in defaults
    assert "TAILSCALE_AUTH_KEY" not in site
    assert (
        "'tailnet-check.py' if ansible_check_mode else 'tailnet-configure.py'" in tasks
    )
    assert "check_mode: false" in tasks
    assert "Predict first Tailnet enrollment in check mode" in tasks
    assert "_tailnet_enrollment_required" in tasks
    assert "if (not ansible_check_mode and _tailnet_enrollment_required" in tasks


def test_role_pins_the_official_signed_stable_package_source() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    tasks = (ROLE / "tasks/main.yml").read_text()

    assert defaults["tailnet_management_package_version"] == "1.102.3"
    assert (
        defaults["tailnet_management_repository_gpg_sha256"]
        == "3e03dacf222698c60b8e2f990b809ca1b3e104de127767864284e6c228f1fb39"
    )
    assert "https://pkgs.tailscale.com/stable/" in tasks
    assert "signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg" in tasks
    assert "Pin-Priority: 1001" in tasks
    assert 'name: "tailscale={{ tailnet_management_package_version }}"' in tasks
    assert defaults["tailnet_management"] == {"approved_sources": []}
    assert "tailnet_management.install_package" not in tasks


def test_role_preflights_existing_tailnet_before_every_host_write() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    names = [task["name"] for task in tasks]
    status = names.index(
        "Read existing Tailnet state before package or controller writes"
    )
    preferences = names.index(
        "Read existing running Tailnet preferences before host writes"
    )
    first_write = names.index("Install signed-repository prerequisites")

    assert status < preferences < first_write
    for name in (
        "Read existing Tailnet state before package or controller writes",
        "Read existing running Tailnet preferences before host writes",
    ):
        task = next(task for task in tasks if task["name"] == name)
        assert task["changed_when"] is False
        assert task["no_log"] is True
    assert (
        names.index("Refuse unsupported existing Tailnet state before host writes")
        < first_write
    )
    assert (
        names.index("Refuse unmanaged running Tailnet preferences before host writes")
        < first_write
    )
    preferences_guard = next(
        task
        for task in tasks
        if task["name"]
        == "Refuse unmanaged running Tailnet preferences before host writes"
    )
    assert (
        "_tailnet_existing_prefs['advertise-routes'] == []"
        in preferences_guard["ansible.builtin.assert"]["that"]
    )
    assert (
        names.index("Refuse package installation over a local Tailscale command")
        < first_write
    )
    assert (
        names.index(
            "Require one existing Tailscale command when package installation is disabled"
        )
        < first_write
    )
    assert names.index("Require enrollment capability before host writes") < first_write
    daemon = next(
        task
        for task in tasks
        if task["name"] == "Enable and start the Tailscale daemon"
    )
    timer = next(
        task
        for task in tasks
        if task["name"] == "Arm persistent Tailnet recovery before enrollment"
    )
    assert "not ansible_check_mode" in daemon["when"]
    assert timer["when"] == "not ansible_check_mode"
    boot_gate = next(
        task
        for task in tasks
        if task["name"] == "Enable the boot Tailnet recovery gate"
    )
    assert boot_gate["ansible.builtin.systemd_service"]["enabled"] is True
    ownership = next(
        task
        for task in tasks
        if task["name"] == "Refuse ambiguous existing Tailscale command ownership"
    )
    checks = "\n".join(ownership["ansible.builtin.assert"]["that"])
    assert ".stat.isreg" in checks
    assert ".stat.uid == 0" in checks
    assert ".stat.wgrp" in checks and ".stat.woth" in checks


def test_role_does_not_parse_success_json_when_the_controller_refuses() -> None:
    tasks = (ROLE / "tasks/main.yml").read_text()
    assert "_tailnet_management_result.rc == 0 and" in tasks
    assert "(_tailnet_management_result.stdout | from_json).changed" in tasks


def test_molecule_prepares_sshd_policy_inspection_runtime() -> None:
    prepare = yaml.safe_load((ROLE / "molecule/default/prepare.yml").read_text())[0]
    directories = [
        task["ansible.builtin.file"]
        for task in prepare["tasks"]
        if "ansible.builtin.file" in task
    ]
    assert {
        "path": "/run/sshd",
        "state": "directory",
        "owner": "root",
        "group": "root",
        "mode": "0755",
    } in directories
    nft_fixture = next(
        task["ansible.builtin.copy"]
        for task in prepare["tasks"]
        if task.get("ansible.builtin.copy", {}).get("dest") == "/usr/sbin/nft"
    )
    assert nft_fixture["owner"] == "root"
    assert nft_fixture["mode"] == "0755"
    assert (
        '"advertise-routes":[]' in (ROLE / "molecule/default/prepare.yml").read_text()
    )
    assert '"-j list chains"' in nft_fixture["content"]
