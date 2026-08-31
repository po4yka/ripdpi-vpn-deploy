"""Contract tests for opt-in ordinary OpenSSH over Tailscale."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest
import yaml

from template_render import merge_render_vars, render_template


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "tailnet-management-controller.py"
ROLE = ROOT / "ansible" / "roles" / "tailnet-management"


def _load_controller():
    spec = importlib.util.spec_from_file_location("tailnet_management_controller", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tailnet_role_is_opt_in_tactical_and_wired_after_firewall() -> None:
    defaults = yaml.safe_load((ROOT / "ansible/group_vars/all.yml").read_text())
    tiers = yaml.safe_load((ROOT / "ansible/role-tiers.yml").read_text())
    site = yaml.safe_load((ROOT / "ansible/playbooks/site.yml").read_text())[0]
    roles = [entry["role"] for entry in site["roles"]]

    assert defaults["vpn"]["enable_tailnet_management"] is False
    assert tiers["tiers"]["tailnet-management"] == "tactical"
    assert tiers["toggle_role_map"]["enable_tailnet_management"] == "tailnet-management"
    assert roles.index("tailnet-management") == roles.index("firewall") + 1


def test_tailnet_molecule_uses_the_published_image_architecture() -> None:
    scenario = yaml.safe_load(
        (ROLE / "molecule/default/molecule.yml").read_text()
    )
    assert scenario["platforms"][0]["platform"] == "linux/amd64"


def test_firewall_allows_only_exact_approved_tailnet_sources() -> None:
    variables = merge_render_vars()
    variables["vpn"] = {**variables["vpn"], "enable_tailnet_management": True}
    variables["tailnet_management"] = {
        "approved_sources": ["100.64.10.20", "fd7a:115c:a1e0::1234"],
    }
    variables["firewall_effective_ssh_ports"] = [22022]
    variables["public_listener_contract"] = []
    rendered = render_template(
        ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", variables
    )

    assert 'iifname "tailscale0" tcp dport 22022 ip saddr 100.64.10.20 accept' in rendered
    assert (
        'iifname "tailscale0" tcp dport 22022 '
        'ip6 saddr fd7a:115c:a1e0::1234 accept'
    ) in rendered
    assert 'iifname "tailscale0" accept' not in rendered


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
    assert controller.validate_sources(
        ["100.64.1.2", "fd7a:115c:a1e0::1234"]
    ) == ["100.64.1.2", "fd7a:115c:a1e0::1234"]


class FakeRunner:
    def __init__(
        self,
        root: Path,
        *,
        drift: str | None = None,
        preference_mismatch: bool = False,
        tailscale_firewall: bool = False,
    ) -> None:
        self.root = root
        self.drift = drift
        self.preference_mismatch = preference_mismatch
        self.tailscale_firewall = tailscale_firewall
        self.running = False
        self.calls: list[list[str]] = []
        self.auth_file_mode: int | None = None
        self.auth_file_bytes: bytes | None = None

    def __call__(self, argv: list[str], *, timeout: int):
        self.calls.append(argv)
        command = argv[1:]
        stdout = ""
        if command == ["status", "--json"]:
            stdout = json.dumps({"BackendState": "Running" if self.running else "NeedsLogin"})
        elif command == ["get", "--json", "all"]:
            preferences = {
                    "accept-dns": False,
                    "accept-routes": False,
                    "advertise-exit-node": False,
                    "advertise-routes": "",
                    "exit-node": "",
                    "netfilter-mode": "off",
                    "shields-up": False,
                    "ssh": False,
            }
            if self.preference_mismatch:
                preferences["accept-routes"] = True
            stdout = json.dumps(preferences)
        elif command[:1] == ["login"]:
            auth_arg = next(item for item in command if item.startswith("--auth-key=file:"))
            auth_path = Path(auth_arg.removeprefix("--auth-key=file:"))
            self.auth_file_mode = auth_path.stat().st_mode & 0o777
            self.auth_file_bytes = auth_path.read_bytes()
            self.running = True
        elif command == ["ip", "-4"]:
            stdout = "100.64.1.9\n"
        elif command == ["ip", "-6"]:
            stdout = "fd7a:115c:a1e0::9\n"
        elif argv[0].endswith("sshd") and command == ["-T"]:
            stdout = "port 22022\nhostkey /etc/ssh/ssh_host_ed25519_key\n"
            if self.drift == "sshd" and self.running:
                stdout = "port 22\nhostkey /etc/ssh/ssh_host_ed25519_key\n"
        elif argv[0].endswith("ip") and command == ["-4", "-json", "route", "show", "default"]:
            stdout = '[{"dst":"default","gateway":"192.0.2.1","dev":"eth0"}]\n'
            if self.drift == "route-v4" and self.running:
                stdout = '[{"dst":"default","gateway":"192.0.2.2","dev":"eth0"}]\n'
        elif argv[0].endswith("ip") and command == ["-6", "-json", "route", "show", "default"]:
            stdout = '[{"dst":"default","gateway":"2001:db8::1","dev":"eth0"}]\n'
            if self.drift == "route-v6" and self.running:
                stdout = '[{"dst":"default","gateway":"2001:db8::2","dev":"eth0"}]\n'
        elif argv[0].endswith("nft") and command == ["-j", "list", "ruleset"]:
            stdout = (
                '{"nftables":[{"chain":{"name":"ts-input"}}]}'
                if self.tailscale_firewall
                else '{"nftables":[]}'
            )
        elif command == ["logout"]:
            self.running = False
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
    )


def test_fresh_enrollment_uses_private_auth_file_and_preserves_host_policy(tmp_path) -> None:
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


def test_missing_key_refuses_before_login(tmp_path) -> None:
    controller = _load_controller()
    (tmp_path / "resolv.conf").write_text("nameserver 192.0.2.53\n")
    runner = FakeRunner(tmp_path)

    with pytest.raises(controller.Refusal, match="tailnet-auth-required"):
        controller.configure(
            paths=_paths(controller, tmp_path), runner=runner, auth_key=""
        )

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
    assert "'check' if ansible_check_mode else 'configure'" in tasks
    assert "check_mode: false" in tasks
    assert "Predict first Tailnet enrollment in check mode" in tasks


def test_role_pins_the_official_signed_stable_package_source() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())[
        "tailnet_management"
    ]
    tasks = (ROLE / "tasks/main.yml").read_text()

    assert defaults["package_version"] == "1.102.3"
    assert (
        defaults["repository_gpg_sha256"]
        == "3e03dacf222698c60b8e2f990b809ca1b3e104de127767864284e6c228f1fb39"
    )
    assert "https://pkgs.tailscale.com/stable/" in tasks
    assert "signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg" in tasks
    assert 'Pin-Priority: 1001' in tasks
    assert 'name: "tailscale={{ tailnet_management.package_version }}"' in tasks


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
    assert '"-j list ruleset"' in nft_fixture["content"]
