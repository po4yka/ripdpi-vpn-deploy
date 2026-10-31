"""Execute the resolver tasks across migration, retirement and refusal states."""
from __future__ import annotations

import copy
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml
from test_runtime_audit_regressions import relocate, tasks


@pytest.fixture
def resolver_host():
    # Short paths keep the bounded production receipt meaningful on macOS.
    with tempfile.TemporaryDirectory(prefix="resolver-cycle-", dir="/tmp") as temporary:
        root = Path(temporary).resolve()
        etc, run = root / "etc", root / "run"
        (etc / "systemd/resolved.conf.d").mkdir(parents=True)
        run.mkdir()
        stub = run / "stub-resolv.conf"
        stub.write_text("nameserver 127.0.0.53\n")
        upstream = run / "resolv.conf"
        upstream.write_text("nameserver 192.0.2.53\n")
        (etc / "resolv.conf").symlink_to(stub)
        # The encrypted-resolver proof is a stub that records calls and fails on demand.
        proofs, proof_failure = root / "proofs", root / "fail-proof"
        resolvectl = root / "resolvectl"
        resolvectl.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> " + str(proofs) + "\n"
                              "[ -e " + str(proof_failure) + " ] && exit 1\nexit 0\n")
        resolvectl.chmod(0o755)
        selected = relocate(tasks("roles/baseline/tasks/resolver.yml"), {
            "/etc/": str(etc) + "/",
            "/run/systemd/resolve/": str(run) + "/",
            "resolvectl": str(resolvectl),
            "baseline_stub_receipt.stat.uid == 0": f"baseline_stub_receipt.stat.uid == {os.getuid()}",
            "baseline_stub_pending.stat.uid == 0": f"baseline_stub_pending.stat.uid == {os.getuid()}",
        })
        restarts = root / "restarts"
        for restart in [row for row in selected if "ansible.builtin.systemd_service" in row] + [
                row for block in selected for section in ("block", "rescue") for row in block.get(section, [])
                if "ansible.builtin.systemd_service" in row]:
            restart.pop("ansible.builtin.systemd_service")
            restart["ansible.builtin.command"] = {"argv": [sys.executable, "-c",
                "from pathlib import Path; p=Path(" + repr(str(restarts)) + "); "
                "p.write_text(p.read_text()+'restart\\n' if p.exists() else 'restart\\n')"]}
            restart["changed_when"] = True

        def execute(enabled, *, deferred=False, check=False, interrupt_before_restart=False):
            selected_tasks = copy.deepcopy(selected)
            if interrupt_before_restart:
                boundary = next(i for i, row in enumerate(selected_tasks)
                                if row.get("name") == "Apply the resolver transition before dependent roles run")
                selected_tasks = selected_tasks[:boundary] + [{"ansible.builtin.fail": {"msg": "owned interruption boundary"}}]
            play = root / "play.yml"
            play.write_text(yaml.safe_dump([{
                "hosts": "localhost", "gather_facts": False, "become": False,
                "vars": {"ansible_python_interpreter": sys.executable,
                         "vpn": {"enable_dns_morph_bridge": enabled},
                         "baseline_defer_resolver_restore": deferred},
                "tasks": selected_tasks,
            }]))
            return subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local",
                                   *(["--check"] if check else []), str(play)],
                                  check=False, capture_output=True, text=True, timeout=60)

        yield root, etc / "resolv.conf", stub, upstream, restarts, execute


def test_managed_stub_roundtrip_defers_restore_until_listener_retirement(resolver_host):
    root, resolver, stub, upstream, restarts, execute = resolver_host
    receipt = root / "etc/systemd/resolved.conf.d/vpn-dns-morph-stub.path"
    for _ in range(2):
        result = execute(True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert resolver.resolve() == upstream
        assert receipt.read_text().strip() == str(stub)
    assert restarts.read_text().splitlines() == ["restart"]
    result = execute(False, deferred=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert resolver.resolve() == upstream and receipt.exists()
    assert restarts.read_text().splitlines() == ["restart"]
    result = execute(False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert resolver.resolve() == stub and not receipt.exists()
    assert restarts.read_text().splitlines() == ["restart", "restart"]
    result = execute(False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert restarts.read_text().splitlines() == ["restart", "restart"]


def test_existing_custom_upstream_is_never_adopted(resolver_host):
    root, resolver, _stub, upstream, _restarts, execute = resolver_host
    resolver.unlink()
    resolver.symlink_to(upstream)
    for enabled in (True, False):
        result = execute(enabled)
        assert result.returncode == 0, result.stdout + result.stderr
        assert resolver.resolve() == upstream
    assert not (root / "etc/systemd/resolved.conf.d/vpn-dns-morph-stub.path").exists()


def test_replaced_resolver_refuses_restore_without_overwrite(resolver_host):
    root, resolver, _stub, _upstream, _restarts, execute = resolver_host
    result = execute(True)
    assert result.returncode == 0, result.stdout + result.stderr
    resolver.unlink()
    resolver.write_text("nameserver 198.51.100.53\n")
    result = execute(False)
    assert result.returncode != 0
    assert resolver.read_text() == "nameserver 198.51.100.53\n"
    assert (root / "etc/systemd/resolved.conf.d/vpn-dns-morph-stub.path").exists()


def test_check_mode_keeps_resolver_and_receipt_intact(resolver_host):
    root, resolver, stub, _upstream, restarts, execute = resolver_host
    result = execute(True, check=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert resolver.resolve() == stub and not restarts.exists()
    assert not (root / "etc/systemd/resolved.conf.d/vpn-dns-morph-stub.path").exists()


@pytest.mark.parametrize("content", ["", " \n", "/unexpected/resolver\n"])
def test_invalid_migration_receipt_refuses_before_resolver_mutation(resolver_host, content):
    root, resolver, stub, _upstream, restarts, execute = resolver_host
    receipt = root / "etc/systemd/resolved.conf.d/vpn-dns-morph-stub.path"
    receipt.write_text(content)
    receipt.chmod(0o600)
    result = execute(True)
    assert result.returncode != 0
    assert resolver.resolve() == stub and not restarts.exists()
    assert receipt.read_text() == content
    assert not (receipt.parent / "no-stub.conf").exists()


def test_stub_restore_follows_owned_bridge_retirement():
    disable = tasks("roles/dns-morph-bridge/tasks/disable.yml")
    assert disable[-1]["ansible.builtin.include_role"] == {"name": "baseline", "tasks_from": "resolver"}
    assert disable[-1]["vars"] == {"baseline_dns_morph_active": False, "baseline_defer_resolver_restore": False}
    assert any(row.get("ansible.builtin.include_role", {}).get("tasks_from") == "retire" for row in disable[:-1])
    site = tasks("playbooks/site.yml")[0]
    baseline = next(row for row in site["roles"] if row.get("role") == "baseline")
    assert baseline["vars"]["baseline_defer_resolver_restore"] is True


def test_interrupted_enable_replays_apply_then_returns_to_idempotence(resolver_host):
    root, resolver, _stub, upstream, restarts, execute = resolver_host
    result = execute(True, interrupt_before_restart=True)
    assert result.returncode != 0
    assert resolver.resolve() == upstream and not restarts.exists()
    pending = root / "etc/systemd/resolved.conf.d/vpn-dns-morph-apply.pending"
    assert pending.exists()
    for _ in range(2):
        result = execute(True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not pending.exists()
    assert restarts.read_text().splitlines() == ["restart"]


def test_encrypted_host_resolver_is_installed_once_and_proven_after_restart(resolver_host):
    root, resolver, stub, _upstream, restarts, execute = resolver_host
    dropin = root / "etc/systemd/resolved.conf.d/vpn-dns-over-tls.conf"
    result = execute(False, deferred=True)
    assert result.returncode == 0, result.stdout + result.stderr
    content = dropin.read_text()
    assert "DNSOverTLS=yes" in content and "Domains=~." in content and "LLMNR=no" in content
    assert "DNS=1.1.1.1#cloudflare-dns.com 8.8.8.8#dns.google" in content
    assert resolver.resolve() == stub and restarts.read_text().splitlines() == ["restart"]
    assert (root / "proofs").read_text().splitlines() == ["query --type=A cloudflare-dns.com"]
    result = execute(False, deferred=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert restarts.read_text().splitlines() == ["restart"]
    assert (root / "proofs").read_text().splitlines() == ["query --type=A cloudflare-dns.com"]


def test_failed_encrypted_resolver_proof_withdraws_the_drop_in_and_refuses(resolver_host):
    root, resolver, stub, _upstream, restarts, execute = resolver_host
    (root / "fail-proof").touch()
    result = execute(False, deferred=True)
    assert result.returncode != 0
    assert "encrypted-resolver-unavailable" in result.stdout
    assert not (root / "etc/systemd/resolved.conf.d/vpn-dns-over-tls.conf").exists()
    assert resolver.resolve() == stub and restarts.read_text().splitlines() == ["restart", "restart"]
