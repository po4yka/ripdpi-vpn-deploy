"""Provisioning contract for the local real-VPS AWG/NAT sentinel."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/real-vps-awg-nat"
PLAYBOOK = ROOT / "ansible/playbooks/provision-real-vps-awg-nat.yml"
SERVER = ROOT / "scripts/real-vps-awg-nat-server.py"
ECHO = ROOT / "scripts/real-vps-awg-nat-echo.py"
ROTATION = ROOT / "scripts/real-vps-awg-nat-rotation.py"
TOOLCHAIN = ROOT / "scripts/install-real-vps-awg-client-tools.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("awg_evidence_server", SERVER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_echo():
    spec = importlib.util.spec_from_file_location("awg_evidence_echo", ECHO)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_rotation():
    spec = importlib.util.spec_from_file_location("awg_evidence_rotation", ROTATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_toolchain():
    spec = importlib.util.spec_from_file_location("awg_toolchain_installer", TOOLCHAIN)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_playbook_provisions_three_separate_trust_boundaries() -> None:
    source = PLAYBOOK.read_text()

    assert "hosts: awg_evidence_echo" in source
    assert "hosts: awg_evidence_server" in source
    assert "hosts: awg_evidence_sentinel" in source
    assert source.count("serial: 1") == 3
    assert source.count("role: real-vps-awg-nat") == 3
    assert source.count("vars_files:") == 3
    assert source.count('- "{{ vpn_secrets_file }}"') == 3
    assert source.count("lookup('env', 'VPN_SECRETS_FILE') | length > 0") == 3
    assert source.count("terraform_public_listeners_b64 | b64decode | from_json") == 2
    for mode in ("echo", "server", "sentinel"):
        assert f'real_vps_awg_nat_mode: "{mode}"' in source


def test_role_is_a_documented_standalone_research_exception() -> None:
    site = (ROOT / "ansible/playbooks/site.yml").read_text()
    role_notes = (ROLE / "CLAUDE.md").read_text()
    tiers = (ROOT / "ansible/role-tiers.yml").read_text()
    runbook = (ROOT / "docs/REAL-VPS-AWG-NAT.md").read_text()
    liveness = (ROOT / "docs/PROTOCOL-LIVENESS.md").read_text()

    assert "real-vps-awg-nat" not in site
    assert "Standalone research-role exception" in role_notes
    assert "intentionally has no" in role_notes
    assert "`vpn.enable_*` toggle" in role_notes
    assert "real-vps-awg-nat: research" in tiers
    assert "sentinel to the Raspberry Pi" not in runbook
    assert "physical Linux sentinel" not in runbook
    assert "off-fleet physical sentinel" not in role_notes
    normalized_runbook = " ".join(runbook.split())
    normalized_role_notes = " ".join(role_notes.split())
    for source in (normalized_runbook, normalized_role_notes):
        assert "disposable systemd-capable Linux VM" in source
        assert "consumer uplink" in source
    assert "must not invoke `awg-evidence-provision`" in normalized_runbook
    assert "three required source gates" in normalized_runbook
    assert "does not itself authorize a VM start" in normalized_runbook
    assert "de-onboarding" in normalized_runbook
    assert "executor binding" in normalized_runbook
    assert "fail-closed VM preflight" in normalized_runbook
    assert "make install-liveness-sentinel" in liveness
    assert "will not prove independent physical hardware" in normalized_runbook
    assert "must not invoke this role" in normalized_role_notes
    assert "not operationally enabled" in normalized_role_notes


def test_role_fails_closed_and_never_embeds_private_material() -> None:
    defaults = (ROLE / "defaults/main.yml").read_text()
    tasks = (ROLE / "tasks/main.yml").read_text()
    server_tasks = (ROLE / "tasks/server.yml").read_text()
    sentinel_tasks = (ROLE / "tasks/sentinel.yml").read_text()

    assert "real_vps_awg_nat_mode: fail_closed" in defaults
    assert "requires Linux with systemd and mode echo, server, or" in tasks
    assert "ansible_facts['system'] == 'Linux'" in tasks
    assert "ansible_facts['service_mgr'] == 'systemd'" in tasks
    assert "ansible_system == 'Linux'" not in tasks
    assert "ansible_service_mgr == 'systemd'" not in tasks
    assert "assert:" in server_tasks and "no_log: true" in server_tasks
    assert "assert:" in sentinel_tasks and "no_log: true" in sentinel_tasks
    for secret_name in (
        "server_private_key",
        "current_client_public_key",
        "current_preshared_key",
        "sentinel_ssh_private_key",
        "current_client_config",
        "rotated_client_config",
    ):
        assert f'{secret_name}: ""' in defaults
    text_suffixes = {".conf", ".j2", ".md", ".py", ".yml"}
    rendered = "\n".join(
        path.read_text()
        for path in ROLE.rglob("*")
        if path.is_file() and path.suffix in text_suffixes
    )
    assert "BEGIN OPENSSH PRIVATE KEY" not in rendered
    assert "PrivateKey = AAAAAAAAA" not in rendered


@pytest.mark.parametrize(
    ("case", "inventory", "extra_args"),
    (
        (
            "swapped-host",
            "[awg_evidence_echo]\n"
            "vpn-p2-vultr-ams ansible_connection=local provider=vultr\n"
            "[vpn-p2-udp]\n"
            "vpn-p2-vultr-ams\n",
            (),
        ),
        (
            "missing-provider",
            "[awg_evidence_echo]\n"
            "vpn-p1-scaleway-pl-waw-1 ansible_connection=local\n"
            "[vpn-p1-web]\n"
            "vpn-p1-scaleway-pl-waw-1\n",
            (),
        ),
        (
            "missing-cohort",
            "[awg_evidence_echo]\n"
            "vpn-p1-scaleway-pl-waw-1 ansible_connection=local provider=scaleway\n",
            (),
        ),
        (
            "redirected-address",
            "[awg_evidence_echo]\n"
            "vpn-p1-scaleway-pl-waw-1 ansible_connection=local "
            "ansible_host=203.0.113.11 provider=scaleway\n"
            "[vpn-p1-web]\n"
            "vpn-p1-scaleway-pl-waw-1\n",
            (),
        ),
        (
            "skip-placement-tag",
            "[awg_evidence_echo]\n"
            "vpn-p1-scaleway-pl-waw-1 ansible_connection=local "
            "ansible_host=203.0.113.11 provider=scaleway\n"
            "[vpn-p1-web]\n"
            "vpn-p1-scaleway-pl-waw-1\n",
            ("--skip-tags", "placement"),
        ),
    ),
)
def test_protected_placement_rejects_wrong_inventory_before_mutation(
    tmp_path: Path, case: str, inventory: str, extra_args: tuple[str, ...]
) -> None:
    inventory_path = tmp_path / f"{case}.ini"
    inventory_path.write_text(inventory)
    playbook = tmp_path / f"{case}.yml"
    playbook.write_text("""---
- name: Exercise placement preflight
  hosts: awg_evidence_echo
  gather_facts: false
  become: false
  vars:
    ansible_facts:
      system: Linux
      service_mgr: systemd
    real_vps_awg_nat_mode: echo
    real_vps_awg_nat_expected_placement:
      echo:
        inventory_hostname: vpn-p1-scaleway-pl-waw-1
        ansible_host: 203.0.113.10
        provider: scaleway
        cohort_group: vpn-p1-web
  roles:
    - role: real-vps-awg-nat
""")

    result = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            str(inventory_path),
            str(playbook),
            *extra_args,
        ],
        cwd=ROOT / "ansible",
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Refusing AWG evidence credentials" in output
    assert "Create persistent firewall policy directories" not in output


def test_protected_placement_accepts_exact_provider_state_address(
    tmp_path: Path,
) -> None:
    inventory = tmp_path / "valid-placement.ini"
    inventory.write_text(
        "[awg_evidence_echo]\n"
        "vpn-p1-scaleway-pl-waw-1 ansible_connection=local "
        "ansible_host=203.0.113.10 provider=scaleway\n"
        "[vpn-p1-web]\n"
        "vpn-p1-scaleway-pl-waw-1\n"
    )
    playbook = tmp_path / "valid-placement.yml"
    playbook.write_text("""---
- name: Exercise valid placement preflight
  hosts: awg_evidence_echo
  gather_facts: false
  become: false
  vars:
    ansible_facts:
      system: Linux
      service_mgr: systemd
    real_vps_awg_nat_mode: echo
    real_vps_awg_nat_expected_placement:
      echo:
        inventory_hostname: vpn-p1-scaleway-pl-waw-1
        ansible_host: 203.0.113.10
        provider: scaleway
        cohort_group: vpn-p1-web
  roles:
    - role: real-vps-awg-nat
""")

    result = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            str(inventory),
            str(playbook),
            "--tags",
            "always",
        ],
        cwd=ROOT / "ansible",
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Bind placement to the provider-state address" in output
    assert "Create persistent firewall policy directories" not in output


def test_sentinel_source_checkout_is_fixed_and_rejects_symlink_ancestors() -> None:
    defaults = (ROLE / "defaults/main.yml").read_text()
    tasks = (ROLE / "tasks/sentinel.yml").read_text()

    approved = "/opt/ripdpi-real-vps-awg-nat/repository"
    assert f"real_vps_awg_nat_repo_path: {approved}" in defaults
    assert f"real_vps_awg_nat_repo_path == '{approved}'" in tasks
    assert "Inspect fixed sentinel source path ancestors" in tasks
    assert "follow: false" in tasks
    assert "not (item.stat.islnk | default(false))" in tasks
    assert "refusing symlinked source path component" in tasks


def test_client_toolchain_is_source_pinned_without_remote_shell_pipe() -> None:
    tasks = (ROLE / "tasks/sentinel.yml").read_text()
    defaults = (ROLE / "defaults/main.yml").read_text()

    assert (
        'real_vps_awg_nat_awg_go_commit: "2e3f7d122ca8ef61e403fddc48a9db8fccd95dbf"'
        in defaults
    )
    assert (
        'real_vps_awg_nat_awg_tools_commit: "c0b400c6dfc046f5cae8f3051b14cb61686fcf55"'
        in defaults
    )
    assert "install-real-vps-awg-client-tools" in tasks
    assert "real_vps_awg_nat_awg_go_source_bundle_sha256" in tasks
    assert "real_vps_awg_nat_awg_tools_source_bundle_sha256" in tasks
    assert "real_vps_awg_nat_awg_go_vendor_archive_sha256" in tasks
    assert "binaries['awg-quick']" in tasks
    assert "/run/lock/ripdpi-real-vps-awg-nat" in tasks
    assert "/opt/src/amneziawg-go" in tasks
    assert "/opt/src/amneziawg-tools" in tasks
    assert "github.com" not in tasks
    assert "amneziawg-go.bundle" in tasks
    assert "amneziawg-tools.bundle" in tasks
    assert "sha256sum" in tasks
    assert "curl" not in tasks
    assert "wget" not in tasks
    assert "| sh" not in tasks
    assert "build-essential" in tasks
    assert "pkg-config" in tasks


def test_server_requires_existing_p2_awg_and_forwarding_before_mutation() -> None:
    tasks = (ROLE / "tasks/server.yml").read_text()

    assert tasks.index("Inspect existing P2 AWG server toolchain") < tasks.index(
        "Install exact-source server apply prerequisites"
    )
    assert "/usr/bin/awg" in tasks
    assert "/usr/bin/awg-quick" in tasks
    assert "net.ipv4.ip_forward" in tasks
    assert "_real_vps_awg_nat_ipv4_forwarding.stdout | trim == '1'" in tasks


def test_inventory_binds_evidence_mode_to_each_provider_contract_host() -> None:
    renderer = (ROOT / "scripts/render-inventory.sh").read_text()

    assert "AWG_EVIDENCE_MODES count" in renderer
    assert "fail_closed|echo|server" in renderer
    assert 'vpn_line+=" real_vps_awg_nat_mode=${awg_evidence_mode}"' in renderer


def test_vendor_archive_rejects_traversal_links_duplicates_and_non_vendor(
    tmp_path: Path,
) -> None:
    module = _load_toolchain()

    def archive_with(entries: list[tuple[str, bytes | None, str]]) -> io.BytesIO:
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name, payload, kind in entries:
                member = tarfile.TarInfo(name)
                if kind == "symlink":
                    member.type = tarfile.SYMTYPE
                    member.linkname = "../../escape"
                    archive.addfile(member)
                else:
                    raw = payload or b""
                    member.size = len(raw)
                    archive.addfile(member, io.BytesIO(raw))
        stream.seek(0)
        return stream

    malicious = (
        [("../escape", b"x", "file")],
        [("vendor/link", None, "symlink")],
        [("outside/file", b"x", "file")],
        [("vendor/file", b"one", "file"), ("vendor/file", b"two", "file")],
    )
    for entries in malicious:
        with tarfile.open(fileobj=archive_with(entries), mode="r:") as archive:
            with pytest.raises(ValueError, match="unsafe|only vendor"):
                module.extract_vendor(archive, tmp_path / "source")
        assert not (tmp_path / "escape").exists()


def test_existing_toolchain_reuse_rejects_content_and_mode_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_toolchain()
    monkeypatch.setattr(module, "ROOT_UID", os.geteuid())
    monkeypatch.setattr(module, "ROOT_GID", os.getegid())
    target = tmp_path / "toolchain"
    (target / "bin").mkdir(parents=True)
    (target / "bin/amneziawg-go").write_bytes(b"go")
    (target / "bin/awg").write_bytes(b"tools")
    (target / "bin/awg-quick").write_bytes(b"quick")
    (target / "source").write_bytes(b"source")
    (target / "manifest.json").write_bytes(b"{}\n")
    for binary in (target / "bin").iterdir():
        binary.chmod(0o755)
    module.freeze_tree(target)
    inputs = {
        "goBundleSha256": "a" * 64,
        "goCommit": "b" * 40,
        "toolsBundleSha256": "c" * 64,
        "toolsCommit": "d" * 40,
        "vendorSha256": "e" * 64,
    }
    binaries = {
        name: module.digest(target / "bin" / name) for name in module.BINARY_NAMES
    }
    manifest = {
        "schemaVersion": module.MANIFEST_SCHEMA,
        "inputs": inputs,
        "binaries": binaries,
        "treeSha256": module.tree_digest(target),
    }
    (target / "manifest.json").chmod(0o600)
    (target / "manifest.json").write_bytes(module.canonical(manifest))
    (target / "manifest.json").chmod(0o400)
    assert module.validate_existing(target, inputs) == binaries

    original_manifest = (target / "manifest.json").read_bytes()
    manifest["treeSha256"] = "f" * 64
    (target / "manifest.json").chmod(0o600)
    (target / "manifest.json").write_bytes(module.canonical(manifest))
    (target / "manifest.json").chmod(0o400)
    with pytest.raises(ValueError, match="modified"):
        module.validate_existing(target, inputs)
    (target / "manifest.json").chmod(0o600)
    (target / "manifest.json").write_bytes(original_manifest)
    (target / "manifest.json").chmod(0o400)

    (target / "bin/awg").chmod(0o600)
    with pytest.raises(ValueError, match="metadata"):
        module.validate_existing(target, inputs)
    (target / "bin/awg").chmod(0o700)
    (target / "bin/awg").write_bytes(b"tampered")
    (target / "bin/awg").chmod(0o500)
    with pytest.raises(ValueError, match="modified"):
        module.validate_existing(target, inputs)


def test_existing_legacy_toolchain_permissions_are_hardened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_toolchain()
    monkeypatch.setattr(module, "ROOT_UID", os.geteuid())
    monkeypatch.setattr(module, "ROOT_GID", os.getegid())
    target = tmp_path / "toolchain"
    (target / "bin").mkdir(parents=True)
    for name in module.BINARY_NAMES:
        binary = target / "bin" / name
        binary.write_bytes(name.encode())
        binary.chmod(0o755)
    (target / "source").write_bytes(b"source")
    (target / "manifest.json").write_bytes(b"{}\n")
    for path in [*target.rglob("*"), target]:
        mode = 0o555 if path.is_dir() or path.stat().st_mode & 0o111 else 0o444
        path.chmod(mode)
    inputs = {
        "goBundleSha256": "a" * 64,
        "goCommit": "b" * 40,
        "toolsBundleSha256": "c" * 64,
        "toolsCommit": "d" * 40,
        "vendorSha256": "e" * 64,
    }
    binaries = {
        name: module.digest(target / "bin" / name) for name in module.BINARY_NAMES
    }
    manifest = {
        "schemaVersion": module.MANIFEST_SCHEMA,
        "inputs": inputs,
        "binaries": binaries,
        "treeSha256": module.tree_digest(target),
    }
    (target / "manifest.json").chmod(0o644)
    (target / "manifest.json").write_bytes(module.canonical(manifest))
    (target / "manifest.json").chmod(0o444)

    assert module.harden_legacy_tree(target, inputs) == binaries
    assert stat.S_IMODE(target.stat().st_mode) == 0o500
    assert stat.S_IMODE((target / "bin").stat().st_mode) == 0o500
    assert stat.S_IMODE((target / "source").stat().st_mode) == 0o400
    assert stat.S_IMODE((target / "manifest.json").stat().st_mode) == 0o400
    for name in module.BINARY_NAMES:
        assert stat.S_IMODE((target / "bin" / name).stat().st_mode) == 0o500


@pytest.fixture(params=[0o022, 0o077], ids=["umask022", "umask077"])
def toolchain_umask(request):
    previous = os.umask(request.param)
    try:
        yield
    finally:
        os.umask(previous)


def test_digest_keyed_build_activates_complete_clean_host_command_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, toolchain_umask
) -> None:
    module = _load_toolchain()
    monkeypatch.setattr(module, "ROOT_UID", os.geteuid())
    monkeypatch.setattr(module, "ROOT_GID", os.getegid())
    monkeypatch.setattr(module, "BASE", tmp_path / "toolchains")
    monkeypatch.setattr(module, "ACTIVE_LINK", tmp_path / "active-bin")
    monkeypatch.setattr(module, "COMMAND_DIR", tmp_path / "bin")
    monkeypatch.setattr(module, "LOCK_DIR", tmp_path / "lock")
    monkeypatch.setattr(module, "LOCK_FILE", tmp_path / "lock/lane.lock")

    def bundle(name: str, files: dict[str, bytes]) -> tuple[Path, str]:
        repo = tmp_path / name
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "test"], check=True
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        for relative, payload in files.items():
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
        commit = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        output = tmp_path / f"{name}.bundle"
        subprocess.run(
            ["git", "-C", str(repo), "bundle", "create", str(output), "HEAD"],
            check=True,
        )
        output.chmod(0o600)
        return output, commit

    go_bundle, go_commit = bundle("go", {"Makefile": b"all:\n\t@true\n"})
    tools_bundle, tools_commit = bundle(
        "tools",
        {
            "src/Makefile": b"all:\n\t@true\n",
            "src/awg-quick/linux.bash": b"#!/usr/bin/env bash\nexit 0\n",
        },
    )
    vendor = tmp_path / "vendor.tar"
    with tarfile.open(vendor, mode="w") as archive:
        payload = b"fixture\n"
        member = tarfile.TarInfo("vendor/modules.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    vendor.chmod(0o600)

    def fake_make(path: Path) -> None:
        output = path / ("awg" if path.name == "src" else "amneziawg-go")
        output.write_bytes(path.name.encode())
        output.chmod(0o755)

    monkeypatch.setattr(module, "run_offline_make", fake_make)
    args = SimpleNamespace(
        go_bundle=go_bundle,
        go_bundle_sha256=module.digest(go_bundle),
        go_commit=go_commit,
        tools_bundle=tools_bundle,
        tools_bundle_sha256=module.digest(tools_bundle),
        tools_commit=tools_commit,
        vendor_archive=vendor,
        vendor_sha256=module.digest(vendor),
    )

    first = module.build(args)
    assert first["changed"] is True
    target = module.BASE / first["toolchainId"]
    assert target.is_dir()
    assert stat.S_IMODE(target.stat().st_mode) == 0o500
    assert set(first["binaries"]) == set(module.BINARY_NAMES)
    assert module.ACTIVE_LINK.is_symlink()
    for name in module.BINARY_NAMES:
        command = module.COMMAND_DIR / name
        assert command.is_symlink()
        assert os.readlink(command) == str(module.ACTIVE_LINK / name)
        assert module.digest(command) == first["binaries"][name]
    second = module.build(args)
    assert second == {**first, "changed": False}

    command = module.COMMAND_DIR / "awg"
    command.unlink()
    command.symlink_to(tmp_path / "attacker-awg")
    repaired = module.build(args)
    assert repaired["changed"] is True
    assert os.readlink(command) == str(module.ACTIVE_LINK / "awg")


def test_activation_failure_preserves_previous_complete_toolchain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, toolchain_umask
) -> None:
    module = _load_toolchain()
    monkeypatch.setattr(module, "ROOT_UID", os.geteuid())
    monkeypatch.setattr(module, "ROOT_GID", os.getegid())
    monkeypatch.setattr(module, "ACTIVE_LINK", tmp_path / "active-bin")
    monkeypatch.setattr(module, "COMMAND_DIR", tmp_path / "bin")
    target_one = tmp_path / "toolchains/one"
    target_two = tmp_path / "toolchains/two"
    binaries: dict[str, str] = {}
    for target, marker in ((target_one, b"one"), (target_two, b"two")):
        (target / "bin").mkdir(parents=True)
        for name in module.BINARY_NAMES:
            path = target / "bin" / name
            path.write_bytes(marker + name.encode())
            path.chmod(0o500)
            if target == target_one:
                binaries[name] = module.digest(path)
    module.activate_toolchain(target_one, binaries)
    old_destination = os.readlink(module.ACTIVE_LINK)
    second_binaries = {
        name: module.digest(target_two / "bin" / name) for name in module.BINARY_NAMES
    }
    real_replace = module.replace_symlink

    def crash_before_switch(target: str, destination: Path) -> None:
        if destination == module.ACTIVE_LINK:
            raise OSError("simulated activation crash")
        real_replace(target, destination)

    monkeypatch.setattr(module, "replace_symlink", crash_before_switch)
    with pytest.raises(OSError, match="simulated activation crash"):
        module.activate_toolchain(target_two, second_binaries)
    assert os.readlink(module.ACTIVE_LINK) == old_destination
    for name in module.BINARY_NAMES:
        assert module.digest(module.COMMAND_DIR / name) == binaries[name]


@pytest.mark.parametrize("kind", ["private", "writable", "symlink", "foreign_uid", "foreign_gid"])
def test_activation_rejects_unsafe_existing_command_directory_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    module = _load_toolchain()
    monkeypatch.setattr(module, "ROOT_UID", os.geteuid() + (kind == "foreign_uid"))
    monkeypatch.setattr(module, "ROOT_GID", os.getegid() + (kind == "foreign_gid"))
    command_dir = tmp_path / "bin"
    target = tmp_path / "existing-directory"
    target.mkdir()
    target.chmod({"private": 0o700, "writable": 0o777}.get(kind, 0o755))
    (target / "sentinel").write_text("must remain unchanged")
    if kind == "symlink":
        command_dir.symlink_to(target, target_is_directory=True)
    else:
        target.rename(command_dir)
        target = command_dir
    monkeypatch.setattr(module, "COMMAND_DIR", command_dir)
    before = target.stat()
    with pytest.raises(ValueError, match="AWG command directory is unsafe"):
        module.activate_toolchain(tmp_path / "not-used", {})
    after = target.stat()
    assert (after.st_mode, after.st_uid, after.st_gid, after.st_ino) == (
        before.st_mode, before.st_uid, before.st_gid, before.st_ino
    )
    assert (target / "sentinel").read_text() == "must remain unchanged"
    assert command_dir.is_symlink() == (kind == "symlink")


def test_toolchain_installer_uses_nonblocking_shared_lane_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_toolchain()
    monkeypatch.setattr(module, "ROOT_UID", os.geteuid())
    monkeypatch.setattr(module, "ROOT_GID", os.getegid())
    monkeypatch.setattr(module, "LOCK_DIR", tmp_path / "lock")
    monkeypatch.setattr(module, "LOCK_FILE", tmp_path / "lock/lane.lock")

    with module.lane_lock():
        with pytest.raises(ValueError, match="already running"):
            with module.lane_lock():
                pass


def test_remote_access_is_one_key_one_forced_command() -> None:
    template = (ROLE / "templates/server-authorized-key.j2").read_text()
    hook = (ROLE / "templates/sentinel-hook.j2").read_text()

    for option in (
        "restrict",
        "no-agent-forwarding",
        "no-port-forwarding",
        "no-pty",
        "no-user-rc",
        "no-X11-forwarding",
    ):
        assert option in template
    assert (
        'command="/usr/bin/sudo -n /usr/local/libexec/ripdpi-real-vps-awg-nat-server --forced"'
        in template
    )
    assert "StrictHostKeyChecking=yes" in hook
    assert "IdentitiesOnly=yes" in hook
    assert "BatchMode=yes" in hook
    assert "ConnectTimeout=15" in hook
    assert "real_vps_awg_nat_server_ssh_user ~ '@'" in hook
    assert "| quote" in hook
    assert "eval" not in hook


def test_sentinel_rejects_shell_capable_ssh_user_and_host_values() -> None:
    tasks = (ROLE / "tasks/sentinel.yml").read_text()
    user_pattern = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
    dns_pattern = re.compile(
        r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
        r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$"
    )
    ipv6_pattern = re.compile(r"^[0-9A-Fa-f]*:[0-9A-Fa-f:]+$")

    assert "^[a-z_][a-z0-9_-]{0,31}$" in tasks
    assert "^[0-9A-Fa-f]*:[0-9A-Fa-f:]+$" in tasks
    assert user_pattern.fullmatch("ripdpi-awg-evidence")
    assert dns_pattern.fullmatch("vpn-1.example.test")
    assert ipv6_pattern.fullmatch("2001:db8::1")
    for value in ("root;id", "user name", "-oProxyCommand=id", "user@host", "UPPER"):
        assert user_pattern.fullmatch(value) is None
    for value in (
        "host;id",
        "host $(id)",
        "host\n-oProxyCommand=id",
        "host@attacker",
        "[2001:db8::1]",
    ):
        assert dns_pattern.fullmatch(value) is None
        assert ipv6_pattern.fullmatch(value) is None


def test_sensitive_files_are_root_only_and_installer_is_exact_source() -> None:
    sentinel_tasks = (ROLE / "tasks/sentinel.yml").read_text()
    server_tasks = (ROLE / "tasks/server.yml").read_text()

    for source in (sentinel_tasks, server_tasks):
        assert 'mode: "0600"' in source
        assert "no_log: true" in source
    assert "git rev-parse --verify HEAD^{commit}" in sentinel_tasks
    assert "install-real-vps-awg-nat-local.sh --repo" in sentinel_tasks
    assert "real_vps_awg_nat_expected_source_sha" in sentinel_tasks
    assert "refusing a source SHA mismatch" in sentinel_tasks
    server_vars = (ROLE / "templates/server-private-vars.yml.j2").read_text()
    assert "sentinel_ssh_private_key" not in server_vars
    assert "current_client_config" not in server_vars
    assert "rotated_client_config" not in server_vars


def test_sentinel_provisions_exact_client_identity_before_activation() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    tasks = yaml.safe_load((ROLE / "tasks/sentinel.yml").read_text())
    template = (ROLE / "templates/sentinel-client-identity.json.j2").read_text()

    assert defaults["real_vps_awg_nat_client_source_sha"] == ""
    assert defaults["real_vps_awg_nat_client_artifact_sha256"] == ""
    validation = next(
        task
        for task in tasks
        if task["name"]
        == "Validate private sentinel material and exact source contract"
    )
    assertions = "\n".join(validation["ansible.builtin.assert"]["that"])
    assert (
        "real_vps_awg_nat_client_source_sha is match('^[0-9a-f]{40}$')"
        in assertions
    )
    assert (
        "real_vps_awg_nat_client_artifact_sha256 is match('^[0-9a-f]{64}$')"
        in assertions
    )
    assert assertions.count("'" + "0" * 40 + "'") == 1
    assert assertions.count("'" + "0" * 64 + "'") == 1

    identity_index = next(
        index
        for index, task in enumerate(tasks)
        if task["name"] == "Install exact RIPDPI client identity descriptor"
    )
    install_index = next(
        index
        for index, task in enumerate(tasks)
        if task["name"] == "Install exact-source local runner and timer"
    )
    identity = tasks[identity_index]["ansible.builtin.template"]
    disable_index = next(
        index
        for index, task in enumerate(tasks)
        if task["name"]
        == "Disable recurring AWG evidence before updating its generation"
    )
    wait_index = next(
        index
        for index, task in enumerate(tasks)
        if task["name"] == "Wait for the previous recurring AWG evidence invocation"
    )
    runner_config_index = next(
        index
        for index, task in enumerate(tasks)
        if task["name"] == "Install private runner config"
    )
    assert disable_index < wait_index < runner_config_index < install_index
    assert identity_index < install_index
    assert identity == {
        "src": "sentinel-client-identity.json.j2",
        "dest": "/etc/ripdpi/real-vps-awg-client-identity.json",
        "owner": "root",
        "group": "root",
        "mode": "0600",
    }
    assert tasks[identity_index]["no_log"] is True
    assert tasks[identity_index]["diff"] is False
    disable = tasks[disable_index]["ansible.builtin.systemd_service"]
    assert disable == {
        "name": "ripdpi-real-vps-awg-nat.timer",
        "enabled": False,
        "state": "stopped",
    }
    wait = tasks[wait_index]["ansible.builtin.command"]
    assert wait["argv"] == [
        "flock",
        "--wait",
        "1800",
        "/run/lock/ripdpi-real-vps-awg-nat/lane.lock",
        "/bin/true",
    ]
    assert tasks[wait_index]["changed_when"] is False
    assert not any(
        task.get("ansible.builtin.systemd_service", {}).get("enabled") is True
        for task in tasks[:install_index]
    )
    assert template == (
        '{"artifactSha256":{{ real_vps_awg_nat_client_artifact_sha256 | to_json }},'
        '"ripdpiSourceSha":{{ real_vps_awg_nat_client_source_sha | to_json }},'
        '"version":"ripdpi_awg_client_identity_v1"}\n'
    )
    role_notes = (ROLE / "CLAUDE.md").read_text()
    runbook = (ROOT / "docs/REAL-VPS-AWG-NAT.md").read_text()
    assert "explicit disruptive maintenance" in role_notes
    assert "intentionally disruptive" in runbook
    assert "failed provisioning attempt leaves the timer" in runbook


def test_echo_service_is_dual_protocol_and_firewall_scoped() -> None:
    echo = (ROOT / "scripts/real-vps-awg-nat-echo.py").read_text()
    service = (ROLE / "templates/echo.service.j2").read_text()
    nft = (ROLE / "templates/echo.nft.j2").read_text()
    firewall_service = (ROLE / "templates/firewall.service.j2").read_text()
    nftables_dropin = (ROLE / "templates/nftables-dropin.conf.j2").read_text()

    assert "socket.SOCK_STREAM" in echo
    assert "socket.SOCK_DGRAM" in echo
    assert "hmac" not in echo
    assert "NoNewPrivileges=true" in service
    assert "DynamicUser=true" in service
    assert "tcp dport {{ real_vps_awg_nat_tcp_echo_port }} limit rate 50/second" in nft
    assert "udp dport {{ real_vps_awg_nat_udp_echo_port }} limit rate 50/second" in nft
    assert "real_vps_awg_nat_sentinel_public_ipv4" in nft
    assert "real_vps_awg_nat_sentinel_public_ipv6" in nft
    assert "tcp dport {{ real_vps_awg_nat_tcp_echo_port }} drop" in nft
    assert "udp dport {{ real_vps_awg_nat_udp_echo_port }} drop" in nft
    assert "MAX_MESSAGE = 4096" in echo
    assert "PartOf=nftables.service" in firewall_service
    assert "ExecReload={{ _evidence_firewall_loader }}" in firewall_service
    assert "PropagatesReloadTo={{ _evidence_firewall_service }}" in nftables_dropin
    runner_config = (ROLE / "templates/sentinel-runner.json.j2").read_text()
    assert '"deployTimeoutSeconds": 900' in runner_config

    module = _load_echo()
    allowed = frozenset({"192.0.2.10"})
    assert module.is_allowed("192.0.2.10", allowed)
    assert not module.is_allowed("192.0.2.11", allowed)


def test_server_command_parser_is_closed_and_argument_safe() -> None:
    module = _load_server()

    assert module.parse_forced_command("status") == ("status", [])
    assert module.parse_forced_command("restart") == ("restart", [])
    assert module.parse_forced_command("reload") == ("reload", [])
    assert module.parse_forced_command("rotation prepare") == ("rotation", ["prepare"])
    assert module.parse_forced_command("rotation reconcile") == (
        "rotation",
        ["reconcile"],
    )
    assert module.parse_forced_command("deploy " + "a" * 40 + " " + "b" * 64) == (
        "deploy",
        ["a" * 40, "b" * 64],
    )
    for unsafe in (
        "",
        "status extra",
        "restart; id",
        "deploy ../../x " + "b" * 64,
        "rotation prepare extra",
        "shell",
    ):
        with pytest.raises(ValueError):
            module.parse_forced_command(unsafe)


def test_rotation_payload_and_receipt_are_secret_free() -> None:
    module = _load_server()
    payload = {
        "clientPublicKey": "A" * 43 + "=",
        "presharedKey": "B" * 43 + "=",
        "allowedIps": "10.66.77.2/32",
        "rotatedClientConfigSha256": "c" * 64,
    }

    validated = module.validate_rotation_payload(payload, "10.66.77.2/32")
    receipt = module.rotation_receipt(
        previous_config=b"old",
        next_config=b"new",
        previous_psk=b"C" * 43 + b"=",
        next_psk=validated["presharedKey"].encode(),
        rotated_client_sha=validated["rotatedClientConfigSha256"],
    )

    encoded = json.dumps(receipt, sort_keys=True)
    assert payload["clientPublicKey"] not in encoded
    assert payload["presharedKey"] not in encoded
    assert set(receipt) == {
        "previousConfigGenerationSha256",
        "nextConfigGenerationSha256",
        "previousPeerConfigSha256",
        "nextPeerConfigSha256",
        "rotatedClientConfigSha256",
    }


def test_rotation_payload_uses_configured_client_host_address() -> None:
    module = _load_server()
    payload = {
        "clientPublicKey": "A" * 43 + "=",
        "presharedKey": "B" * 43 + "=",
        "allowedIps": "192.0.2.42/32",
        "rotatedClientConfigSha256": "c" * 64,
    }

    assert module.validate_rotation_payload(payload, "192.0.2.42/32") == payload
    with pytest.raises(ValueError, match="invalid evidence peer address"):
        module.validate_rotation_payload(payload, "10.66.77.2/32")


@pytest.mark.parametrize(
    "field",
    ("clientPublicKey", "presharedKey", "allowedIps", "rotatedClientConfigSha256"),
)
def test_rotation_payload_rejects_non_string_fields(field: str) -> None:
    module = _load_server()
    payload = {
        "clientPublicKey": "A" * 43 + "=",
        "presharedKey": "B" * 43 + "=",
        "allowedIps": "10.66.77.2/32",
        "rotatedClientConfigSha256": "c" * 64,
    }
    payload[field] = 1

    with pytest.raises(ValueError, match="invalid rotation payload fields"):
        module.validate_rotation_payload(payload, "10.66.77.2/32")


def test_rotation_receipt_rejects_non_string_digest() -> None:
    module = _load_server()
    receipt = {
        "previousConfigGenerationSha256": "a" * 64,
        "nextConfigGenerationSha256": "b" * 64,
        "previousPeerConfigSha256": "c" * 64,
        "nextPeerConfigSha256": "d" * 64,
        "rotatedClientConfigSha256": 1,
    }

    with pytest.raises(ValueError, match="invalid rotation receipt"):
        module.validate_rotation_receipt(receipt)


@pytest.mark.parametrize(
    "loader,writer", ((_load_server, "atomic_write"), (_load_rotation, "atomic"))
)
def test_rotation_atomic_writes_fsync_file_and_parent_directory(
    loader, writer: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = loader()
    real_fsync = module.os.fsync
    fsynced: list[int] = []

    def record_fsync(fd: int) -> None:
        fsynced.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", record_fsync)
    getattr(module, writer)(tmp_path / "state.json", b"{}\n")

    assert len(fsynced) == 2


def test_server_rotation_cleanup_fsyncs_parent_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_server()
    paths = (tmp_path / "pending", tmp_path / "previous")
    for path in paths:
        path.write_bytes(b"state")
    synced: list[Path] = []
    monkeypatch.setattr(module, "sync_parent", synced.append)

    module.remove_rotation_files(*paths)

    assert not any(path.exists() for path in paths)
    assert synced == [paths[0]]


def test_archive_members_reject_traversal_links_and_devices() -> None:
    module = _load_server()

    class Member:
        def __init__(self, name: str, *, file: bool = True, linkname: str = ""):
            self.name = name
            self._file = file
            self.linkname = linkname

        def isreg(self) -> bool:
            return self._file

        def isdir(self) -> bool:
            return False

        def issym(self) -> bool:
            return not self._file and bool(self.linkname)

    module.validate_archive_members([Member("scripts/real-vps-awg-nat-server.py")])
    for member in (
        Member("../escape"),
        Member("/root/escape"),
        Member("device", file=False),
        Member("link", file=False, linkname="../../escape"),
    ):
        with pytest.raises(ValueError):
            module.validate_archive_members([member])
    module.validate_archive_members(
        [
            Member("scripts/real-vps-awg-nat-server.py"),
            Member("AGENTS.md", file=False, linkname="CLAUDE.md"),
        ]
    )


def test_real_git_archive_allows_relative_symlink_within_snapshot(
    tmp_path: Path,
) -> None:
    module = _load_server()
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts/real-vps-awg-nat-server.py").write_text("#!/usr/bin/env python3\n")
    (repo / "ansible/group_vars").mkdir(parents=True)
    (repo / "ansible/group_vars/all.yml").write_text("---\n")
    (repo / "ansible/playbooks").mkdir()
    (repo / "ansible/playbooks/group_vars").symlink_to("../group_vars")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
    archived = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()

    with tarfile.open(fileobj=io.BytesIO(archived), mode="r:") as archive:
        members = archive.getmembers()
        module.validate_archive_members(members)
        archive.extractall(snapshot, members=members, filter="data")

    module.validate_snapshot_permissions(snapshot)
    assert (snapshot / "ansible/playbooks/group_vars").resolve() == (
        snapshot / "ansible/group_vars"
    ).resolve()


def test_deploy_receipt_is_written_only_after_exact_source_ansible_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_server()
    module.STATE = tmp_path / "state"
    module.RECORD = module.STATE / "deployment.json"
    module.SOURCE_ROOT = tmp_path / "sources"
    module.SOURCE_ROOT.mkdir()
    module.PRIVATE_VARS = tmp_path / "private.yml"
    module.PRIVATE_VARS.write_text("private: true\n")
    module.PRIVATE_VARS.chmod(0o600)
    # Build the tiny tar with stdlib so the test is portable.
    import io
    import tarfile

    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        info = tarfile.TarInfo("scripts/real-vps-awg-nat-server.py")
        raw = b"#!/usr/bin/env python3\n"
        info.size = len(raw)
        tar.addfile(info, io.BytesIO(raw))
        playbook = tarfile.TarInfo(
            "ansible/playbooks/provision-real-vps-awg-nat-server-local.yml"
        )
        playbook_raw = b"---\n"
        playbook.size = len(playbook_raw)
        tar.addfile(playbook, io.BytesIO(playbook_raw))
    raw_archive = stream.getvalue()
    module.SOURCE_POLICY = tmp_path / "policy.json"
    module.SOURCE_POLICY.write_text(
        json.dumps(
            {
                "clientAllowedIps": "10.66.77.2/32",
                "sourceSha": "a" * 40,
                "sourceArchiveSha256": module.digest(raw_archive),
            }
        )
    )
    module.SOURCE_POLICY.chmod(0o600)
    calls: list[tuple[str, ...]] = []

    def fail_apply(*command: str, **_kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(module, "run", fail_apply)
    with pytest.raises(module.ProductFailure):
        module.deploy("a" * 40, module.digest(raw_archive), raw_archive)
    assert any("ansible-playbook" in call[0] for call in calls)
    assert not module.RECORD.exists()


def test_successful_deploy_publishes_receipt_after_exact_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io
    import tarfile

    module = _load_server()
    module.STATE = tmp_path / "state"
    module.RECORD = module.STATE / "deployment.json"
    module.SOURCE_ROOT = tmp_path / "sources"
    module.SOURCE_ROOT.mkdir()
    module.PRIVATE_VARS = tmp_path / "private.yml"
    module.PRIVATE_VARS.write_text("private: true\n")
    module.PRIVATE_VARS.chmod(0o600)
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        for name, raw in (
            ("scripts/real-vps-awg-nat-server.py", b"#!/usr/bin/env python3\n"),
            ("ansible/playbooks/provision-real-vps-awg-nat-server-local.yml", b"---\n"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mode = 0o700 if name.endswith(".py") else 0o600
            tar.addfile(info, io.BytesIO(raw))
    archive = stream.getvalue()
    module.SOURCE_POLICY = tmp_path / "policy.json"
    module.SOURCE_POLICY.write_text(
        json.dumps(
            {
                "clientAllowedIps": "10.66.77.2/32",
                "sourceSha": "a" * 40,
                "sourceArchiveSha256": module.digest(archive),
            }
        )
    )
    module.SOURCE_POLICY.chmod(0o600)
    calls: list[tuple[tuple[str, ...], dict]] = []

    def successful_apply(*command: str, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(module, "run", successful_apply)
    receipt = module.deploy("a" * 40, module.digest(archive), archive)

    assert json.loads(module.RECORD.read_text()) == receipt
    assert (module.SOURCE_ROOT / "current").is_symlink()
    command, kwargs = calls[0]
    assert command[0] == "ansible-playbook"
    assert kwargs["cwd"].name == "ansible"
    assert kwargs["env"]["ANSIBLE_CONFIG"].endswith("ansible/ansible.cfg")
    assert kwargs["timeout"] == 840


def test_server_refuses_unapproved_source_before_extract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_server()
    module.SOURCE_POLICY = tmp_path / "policy.json"
    module.SOURCE_POLICY.write_text(
        json.dumps(
            {
                "clientAllowedIps": "10.66.77.2/32",
                "sourceSha": "a" * 40,
                "sourceArchiveSha256": "b" * 64,
            }
        )
    )
    module.SOURCE_POLICY.chmod(0o600)
    monkeypatch.setattr(
        module.tarfile,
        "open",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("archive opened")),
    )

    with pytest.raises(module.ProductFailure, match="operator-approved"):
        module.deploy("c" * 40, "d" * 64, b"untrusted")


def test_rollback_without_transaction_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_server()
    module.STATE = tmp_path / "state"
    module.STATE.mkdir()
    module.CONFIG = tmp_path / "awg.conf"
    module.CONFIG.write_bytes(
        b"[Interface]\n# BEGIN RIPDPI AWG EVIDENCE PEER\n[Peer]\n"
        + b"PublicKey = "
        + b"A" * 43
        + b"=\n"
        + b"PresharedKey = "
        + b"B" * 43
        + b"=\n"
        + b"AllowedIPs = 10.66.77.2/32\n# END RIPDPI AWG EVIDENCE PEER\n"
    )

    receipt = module.rotation("rollback", b"")

    assert receipt["action"] == "rollback"
    assert receipt["configGenerationSha256"] == module.digest(
        module.CONFIG.read_bytes()
    )
    assert receipt["peerConfigSha256"] == module.peer_digest(b"B" * 43 + b"=")


@pytest.mark.parametrize("completed_writes", (1, 2))
def test_prepare_recovers_crash_before_transaction_receipt(
    completed_writes: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_server()
    module.STATE = tmp_path / "state"
    module.STATE.mkdir()
    module.CONFIG = tmp_path / "awg.conf"
    module.CONFIG.write_bytes(
        b"[Interface]\n# BEGIN RIPDPI AWG EVIDENCE PEER\n[Peer]\n"
        + b"PublicKey = "
        + b"A" * 43
        + b"=\nPresharedKey = "
        + b"B" * 43
        + b"=\nAllowedIPs = 10.66.77.2/32\n"
        + b"# END RIPDPI AWG EVIDENCE PEER\n"
    )
    monkeypatch.setattr(
        module,
        "source_policy",
        lambda: {"clientAllowedIps": "10.66.77.2/32"},
    )
    payload = module.canonical(
        {
            "clientPublicKey": "C" * 43 + "=",
            "presharedKey": "D" * 43 + "=",
            "allowedIps": "10.66.77.2/32",
            "rotatedClientConfigSha256": "e" * 64,
        }
    )
    real_atomic_write = module.atomic_write
    writes = 0

    def crash_after_write(path: Path, raw: bytes, mode: int = 0o600) -> None:
        nonlocal writes
        real_atomic_write(path, raw, mode)
        writes += 1
        if writes == completed_writes:
            raise OSError("simulated prepare crash")

    monkeypatch.setattr(module, "atomic_write", crash_after_write)
    with pytest.raises(OSError, match="simulated prepare crash"):
        module.rotation("prepare", payload)

    monkeypatch.setattr(module, "atomic_write", real_atomic_write)
    assert not (module.STATE / "transaction.json").exists()
    assert module.rotation("reconcile", b"") == {"state": "idle"}
    assert not (module.STATE / "previous.conf").exists()
    assert not (module.STATE / "pending.conf").exists()

    receipt = module.rotation("prepare", payload)
    assert receipt["rotatedClientConfigSha256"] == "e" * 64
    assert (module.STATE / "previous.conf").is_file()
    assert (module.STATE / "pending.conf").is_file()
    assert (module.STATE / "transaction.json").is_file()


def test_server_reconcile_observes_commit_before_ack_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_server()
    module.STATE = tmp_path / "state"
    module.STATE.mkdir()
    module.CONFIG = tmp_path / "awg.conf"
    previous_config = b"previous"
    next_config = b"next"
    module.CONFIG.write_bytes(next_config)
    receipt = module.rotation_receipt(
        previous_config=previous_config,
        next_config=next_config,
        previous_psk=b"A" * 43 + b"=",
        next_psk=b"B" * 43 + b"=",
        rotated_client_sha="c" * 64,
    )
    (module.STATE / "previous.conf").write_bytes(previous_config)
    (module.STATE / "pending.conf").write_bytes(next_config)
    (module.STATE / "transaction.json").write_bytes(module.canonical(receipt))
    original_unlink = Path.unlink
    crashed = False

    def crash_on_first_cleanup(path: Path, *args, **kwargs) -> None:
        nonlocal crashed
        if path == module.STATE / "pending.conf" and not crashed:
            crashed = True
            raise OSError("simulated crash after tombstone")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", crash_on_first_cleanup)
    with pytest.raises(OSError, match="simulated crash"):
        module.rotation("acknowledge", b"")

    assert (module.STATE / "rotation-outcome.json").is_file()
    assert (module.STATE / "transaction.json").is_file()
    reconciled = module.rotation("reconcile", b"")
    assert reconciled == {"state": "committed", **module.committed_rotation(receipt)}


def test_server_reconcile_distinguishes_prepared_and_idle(tmp_path: Path) -> None:
    module = _load_server()
    module.STATE = tmp_path / "state"
    module.STATE.mkdir()
    module.CONFIG = tmp_path / "awg.conf"
    module.CONFIG.write_bytes(b"current")
    receipt = module.rotation_receipt(
        previous_config=b"current",
        next_config=b"next",
        previous_psk=b"A" * 43 + b"=",
        next_psk=b"B" * 43 + b"=",
        rotated_client_sha="c" * 64,
    )
    (module.STATE / "transaction.json").write_bytes(module.canonical(receipt))

    assert module.rotation("reconcile", b"") == {
        "state": "prepared",
        "currentClientConfigSha256": "c" * 64,
    }
    (module.STATE / "transaction.json").unlink()
    assert module.rotation("reconcile", b"") == {"state": "idle"}


@pytest.mark.parametrize("stale_state", ("committed", "rolled_back"))
def test_server_reconcile_prefers_differing_new_transaction_over_stale_outcome(
    stale_state: str, tmp_path: Path
) -> None:
    module = _load_server()
    module.STATE = tmp_path / "state"
    module.STATE.mkdir()
    module.CONFIG = tmp_path / "awg.conf"
    module.CONFIG.write_bytes(b"current")
    stale = module.rotation_receipt(
        previous_config=b"old-previous",
        next_config=b"old-next",
        previous_psk=b"A" * 43 + b"=",
        next_psk=b"B" * 43 + b"=",
        rotated_client_sha="c" * 64,
    )
    pending = module.rotation_receipt(
        previous_config=b"current",
        next_config=b"new-next",
        previous_psk=b"C" * 43 + b"=",
        next_psk=b"D" * 43 + b"=",
        rotated_client_sha="d" * 64,
    )
    (module.STATE / "rotation-outcome.json").write_bytes(
        module.canonical(module.rotation_outcome(stale_state, stale))
    )
    (module.STATE / "transaction.json").write_bytes(module.canonical(pending))

    assert module.rotation("reconcile", b"") == {
        "state": "prepared",
        "currentClientConfigSha256": "d" * 64,
    }


@pytest.mark.parametrize(
    "boundary",
    (
        "config_replace",
        "reload",
        "tombstone",
        "unlink_pending",
        "unlink_previous",
        "unlink_transaction",
        "response_loss",
    ),
)
def test_server_rollback_replays_after_every_crash_boundary(
    boundary: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_server()
    module.STATE = tmp_path / "state"
    module.STATE.mkdir()
    module.CONFIG = tmp_path / "awg.conf"
    previous_config = b"previous"
    next_config = b"next"
    module.CONFIG.write_bytes(next_config)
    receipt = module.rotation_receipt(
        previous_config=previous_config,
        next_config=next_config,
        previous_psk=b"A" * 43 + b"=",
        next_psk=b"B" * 43 + b"=",
        rotated_client_sha="c" * 64,
    )
    for name, raw in (
        ("previous.conf", previous_config),
        ("pending.conf", next_config),
        ("transaction.json", module.canonical(receipt)),
    ):
        (module.STATE / name).write_bytes(raw)
    monkeypatch.setattr(
        module,
        "run",
        lambda *command, **_kwargs: subprocess.CompletedProcess(command, 0, b"", b""),
    )
    original_atomic = module.atomic_write
    original_unlink = Path.unlink
    crashed = False

    if boundary in {"config_replace", "tombstone"}:
        crash_path = (
            module.CONFIG
            if boundary == "config_replace"
            else module.STATE / "rotation-outcome.json"
        )

        def crash_after_atomic(path: Path, raw: bytes, mode: int = 0o600) -> None:
            nonlocal crashed
            original_atomic(path, raw, mode)
            if path == crash_path and not crashed:
                crashed = True
                raise OSError(f"crash after {boundary}")

        monkeypatch.setattr(module, "atomic_write", crash_after_atomic)
    elif boundary == "reload":

        def crash_after_reload(*command: str, **_kwargs):
            nonlocal crashed
            if command[:2] == ("systemctl", "reload") and not crashed:
                crashed = True
                raise OSError("crash after reload")
            return subprocess.CompletedProcess(command, 0, b"", b"")

        monkeypatch.setattr(module, "run", crash_after_reload)
    elif boundary.startswith("unlink_"):
        crash_path = (
            module.STATE
            / {
                "unlink_pending": "pending.conf",
                "unlink_previous": "previous.conf",
                "unlink_transaction": "transaction.json",
            }[boundary]
        )

        def crash_after_unlink(path: Path, *args, **kwargs) -> None:
            nonlocal crashed
            original_unlink(path, *args, **kwargs)
            if path == crash_path and not crashed:
                crashed = True
                raise OSError(f"crash after {boundary}")

        monkeypatch.setattr(Path, "unlink", crash_after_unlink)

    if boundary == "response_loss":
        assert module.rotation("rollback", b"") == module.rolled_back_rotation(receipt)
    else:
        with pytest.raises(OSError, match="crash after"):
            module.rotation("rollback", b"")
    monkeypatch.setattr(module, "atomic_write", original_atomic)
    monkeypatch.setattr(Path, "unlink", original_unlink)
    monkeypatch.setattr(
        module,
        "run",
        lambda *command, **_kwargs: subprocess.CompletedProcess(command, 0, b"", b""),
    )

    assert module.rotation("rollback", b"") == module.rolled_back_rotation(receipt)
    assert module.CONFIG.read_bytes() == previous_config
    assert module.rotation("reconcile", b"") == {
        "state": "rolled_back",
        **module.rolled_back_rotation(receipt),
    }


def test_reconcile_completes_rollback_after_reload_before_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = _load_server()
    server.STATE = tmp_path / "server-state"
    server.STATE.mkdir()
    server.CONFIG = tmp_path / "awg.conf"
    previous_config = b"previous"
    next_config = b"next"
    server.CONFIG.write_bytes(next_config)
    receipt = server.rotation_receipt(
        previous_config=previous_config,
        next_config=next_config,
        previous_psk=b"A" * 43 + b"=",
        next_psk=b"B" * 43 + b"=",
        rotated_client_sha="c" * 64,
    )
    for name, raw in (
        ("previous.conf", previous_config),
        ("pending.conf", next_config),
        ("transaction.json", server.canonical(receipt)),
    ):
        (server.STATE / name).write_bytes(raw)
    reloads: list[tuple[str, ...]] = []

    def reload_service(*command: str, **_kwargs):
        reloads.append(command)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(server, "run", reload_service)
    original_atomic = server.atomic_write
    crashed = False

    def crash_before_outcome(path: Path, raw: bytes, mode: int = 0o600) -> None:
        nonlocal crashed
        if path == server.STATE / "rotation-outcome.json" and not crashed:
            crashed = True
            raise OSError("crash before rollback outcome")
        original_atomic(path, raw, mode)

    monkeypatch.setattr(server, "atomic_write", crash_before_outcome)
    with pytest.raises(OSError, match="crash before rollback outcome"):
        server.rotation("rollback", b"")
    assert server.CONFIG.read_bytes() == previous_config
    assert (server.STATE / "rollback-intent.json").is_file()
    assert not (server.STATE / "rotation-outcome.json").exists()
    monkeypatch.setattr(server, "atomic_write", original_atomic)

    local = _load_rotation()
    current = tmp_path / "current.conf"
    rotated = tmp_path / "rotated.conf"
    current.write_bytes(b"changed-current")
    rotated.write_bytes(b"changed-rotated")
    local.save_state(current, "prepared", b"current", b"rotated")
    monkeypatch.setattr(
        local,
        "run_ssh",
        lambda _ssh, command, _payload=b"": server.rotation(
            command.removeprefix("rotation "), b""
        ),
    )

    local.recover_interrupted(current, rotated, ["ssh"])

    assert current.read_bytes() == b"current"
    assert rotated.read_bytes() == b"rotated"
    assert len(reloads) == 2
    assert server.rotation("reconcile", b"")["state"] == "rolled_back"


def test_local_commit_acknowledges_only_after_atomic_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_rotation()
    current = tmp_path / "current.conf"
    rotated = tmp_path / "rotated.conf"
    current.write_bytes(b"current")
    rotated.write_bytes(b"rotated")
    module.save_state(current, "prepared", b"current", b"rotated")
    receipt = {"currentClientConfigSha256": module.sha(b"rotated")}
    calls: list[str] = []

    def remote(_ssh, command, _payload=b""):
        calls.append(command)
        if command == "rotation commit":
            local = module.load_state(current)
            assert local["phase"] == "committing"
            assert local["expectedPromotedClientConfigSha256"] == module.sha(b"rotated")
            assert module.successor_path(current).read_bytes() == b"successor"
        return dict(receipt)

    monkeypatch.setattr(module, "run_ssh", remote)
    monkeypatch.setattr(module, "generate_successor", lambda _raw: b"successor")

    assert module.finalize("commit", current, rotated, ["ssh"]) == receipt
    assert calls == ["rotation commit", "rotation acknowledge"]
    assert current.read_bytes() == b"rotated"
    assert rotated.read_bytes() == b"successor"
    assert not any(path.exists() for path in module.state_paths(current))


def test_prepare_transport_failure_preserves_recovery_state_when_rollback_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_rotation()
    current = tmp_path / "current.conf"
    rotated = tmp_path / "rotated.conf"
    current.write_bytes(b"current")
    rotated.write_bytes(
        b"[Interface]\nPrivateKey = "
        + b"A" * 43
        + b"=\nAddress = 10.66.77.2/32\n[Peer]\nPresharedKey = "
        + b"B" * 43
        + b"=\n"
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            _args[0], 0, b"C" * 43 + b"=\n", b""
        ),
    )
    calls: list[str] = []

    def unavailable(_ssh, command, _payload=b""):
        calls.append(command)
        raise subprocess.CalledProcessError(75, command)

    monkeypatch.setattr(module, "run_ssh", unavailable)

    with pytest.raises(subprocess.CalledProcessError):
        module.prepare(current, rotated, ["ssh"])

    assert calls == ["rotation prepare", "rotation rollback"]
    assert module.load_state(current) == {"phase": "prepared"}
    assert all(path.is_file() for path in module.state_paths(current))


def test_local_commit_ack_failure_restores_both_halves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_rotation()
    current = tmp_path / "current.conf"
    rotated = tmp_path / "rotated.conf"
    current.write_bytes(b"current")
    rotated.write_bytes(b"rotated")
    module.save_state(current, "prepared", b"current", b"rotated")
    receipt = {"currentClientConfigSha256": module.sha(b"rotated")}
    calls: list[str] = []

    def remote(_ssh, command, _payload=b""):
        calls.append(command)
        if command == "rotation acknowledge":
            raise subprocess.CalledProcessError(75, command)
        return dict(receipt)

    monkeypatch.setattr(module, "run_ssh", remote)
    monkeypatch.setattr(module, "generate_successor", lambda _raw: b"successor")

    with pytest.raises(subprocess.CalledProcessError):
        module.finalize("commit", current, rotated, ["ssh"])
    assert calls == [
        "rotation commit",
        "rotation acknowledge",
        "rotation reconcile",
        "rotation rollback",
    ]
    assert current.read_bytes() == b"current"
    assert rotated.read_bytes() == b"rotated"
    assert not any(path.exists() for path in module.state_paths(current))


def test_local_commit_recovers_when_ack_response_is_lost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_rotation()
    current = tmp_path / "current.conf"
    rotated = tmp_path / "rotated.conf"
    current.write_bytes(b"current")
    rotated.write_bytes(b"rotated")
    module.save_state(current, "prepared", b"current", b"rotated")
    receipt = {"currentClientConfigSha256": module.sha(b"rotated")}
    calls: list[str] = []

    def remote(_ssh, command, _payload=b""):
        calls.append(command)
        if command == "rotation acknowledge":
            raise subprocess.CalledProcessError(75, command)
        if command == "rotation reconcile":
            return {"state": "committed", **receipt}
        return dict(receipt)

    monkeypatch.setattr(module, "run_ssh", remote)
    monkeypatch.setattr(module, "generate_successor", lambda _raw: b"successor")

    assert module.finalize("commit", current, rotated, ["ssh"]) == receipt
    assert calls == ["rotation commit", "rotation acknowledge", "rotation reconcile"]
    assert current.read_bytes() == b"rotated"
    assert rotated.read_bytes() == b"successor"
    assert not any(
        path.exists()
        for path in (*module.state_paths(current), module.successor_path(current))
    )


def test_local_recovery_accepts_lost_rollback_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_rotation()
    current = tmp_path / "current.conf"
    rotated = tmp_path / "rotated.conf"
    current.write_bytes(b"changed-current")
    rotated.write_bytes(b"changed-rotated")
    module.save_state(current, "prepared", b"current", b"rotated")
    rollback = {
        "action": "rollback",
        "configGenerationSha256": "a" * 64,
        "peerConfigSha256": "b" * 64,
        "currentClientConfigSha256": "0" * 64,
    }
    lost = True

    def remote(_ssh, command, _payload=b""):
        nonlocal lost
        if command == "rotation rollback" and lost:
            lost = False
            raise subprocess.CalledProcessError(75, command)
        if command == "rotation reconcile":
            return {"state": "rolled_back", **rollback}
        return dict(rollback)

    monkeypatch.setattr(module, "run_ssh", remote)

    with pytest.raises(subprocess.CalledProcessError):
        module.finalize("rollback", current, rotated, ["ssh"])
    module.recover_interrupted(current, rotated, ["ssh"])

    assert current.read_bytes() == b"current"
    assert rotated.read_bytes() == b"rotated"
    assert not any(path.exists() for path in module.state_paths(current))


def test_recovery_promotes_saved_successor_after_committed_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_rotation()
    current = tmp_path / "current.conf"
    rotated = tmp_path / "rotated.conf"
    current.write_bytes(b"current")
    rotated.write_bytes(b"rotated")
    module.save_state(current, "prepared", b"current", b"rotated")
    successor = b"successor"
    module.atomic(module.successor_path(current), successor)
    state, _, _ = module.state_paths(current)
    module.atomic(
        state,
        (
            json.dumps(
                {
                    "phase": "committing",
                    "expectedPromotedClientConfigSha256": module.sha(b"rotated"),
                    "successorClientConfigSha256": module.sha(successor),
                },
                sort_keys=True,
            )
            + "\n"
        ).encode(),
    )
    monkeypatch.setattr(
        module,
        "run_ssh",
        lambda _ssh, command, _payload=b"": (
            {
                "state": "committed",
                "currentClientConfigSha256": module.sha(b"rotated"),
            }
            if command == "rotation reconcile"
            else (_ for _ in ()).throw(AssertionError(command))
        ),
    )

    module.recover_interrupted(current, rotated, ["ssh"])

    assert current.read_bytes() == b"rotated"
    assert rotated.read_bytes() == successor
    assert not any(
        path.exists()
        for path in (*module.state_paths(current), module.successor_path(current))
    )


def test_remote_exit_codes_preserve_product_vs_infrastructure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_server()
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "status")
    monkeypatch.setattr(
        module,
        "dispatch",
        lambda *_args: (_ for _ in ()).throw(module.ProductFailure("bad")),
    )
    monkeypatch.setattr(module.sys, "argv", [str(module.SERVER_PATH), "--forced"])
    monkeypatch.setattr(
        module.sys, "stdin", type("Input", (), {"buffer": __import__("io").BytesIO()})()
    )
    assert module.main() == 70

    monkeypatch.setattr(
        module,
        "dispatch",
        lambda *_args: (_ for _ in ()).throw(module.InfrastructureUnavailable("down")),
    )
    assert module.main() == 75


def test_malformed_source_policy_and_deployment_record_exit_70(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_server()
    module.SOURCE_POLICY = tmp_path / "policy.json"
    module.SOURCE_POLICY.write_text(
        json.dumps({"sourceSha": 1, "sourceArchiveSha256": "b" * 64})
    )
    module.SOURCE_POLICY.chmod(0o600)
    module.RECORD = tmp_path / "deployment.json"
    module.RECORD.write_text(json.dumps(["not", "an", "object"]))
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "status")
    monkeypatch.setattr(module.sys, "argv", [str(module.SERVER_PATH), "--forced"])

    for invalid_loader in (module.source_policy, module.deployment):
        monkeypatch.setattr(module, "dispatch", lambda *_args: invalid_loader())
        monkeypatch.setattr(
            module.sys,
            "stdin",
            type("Input", (), {"buffer": io.BytesIO()})(),
        )
        assert module.main() == 70


def test_bundle_builder_rejects_symlink_output() -> None:
    source = (ROOT / "scripts/build-real-vps-awg-nat-source-bundle.sh").read_text()
    assert '[[ ! -L "$output" ]]' in source
    assert "git bundle verify" in source


def test_bundle_builder_emits_exact_clean_head_and_rejects_dirty_tree(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    secure = tmp_path / "secure"
    repo.mkdir()
    secure.mkdir(mode=0o700)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    (repo / "source").write_text("one\n")
    subprocess.run(["git", "-C", str(repo), "add", "source"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "test"], check=True)
    expected = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    output = secure / "source.bundle"

    built = subprocess.run(
        [
            str(ROOT / "scripts/build-real-vps-awg-nat-source-bundle.sh"),
            "--repo",
            str(repo),
            "--output",
            str(output),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    metadata = json.loads(built.stdout)
    assert metadata["sourceSha"] == expected
    assert (
        metadata["sourceBundleSha256"]
        == __import__("hashlib").sha256(output.read_bytes()).hexdigest()
    )
    assert len(metadata["sourceArchiveSha256"]) == 64
    subprocess.run(
        ["git", "bundle", "verify", str(output)], check=True, capture_output=True
    )

    (repo / "source").write_text("dirty\n")
    rejected = subprocess.run(
        [
            str(ROOT / "scripts/build-real-vps-awg-nat-source-bundle.sh"),
            "--repo",
            str(repo),
            "--output",
            str(output),
        ],
        text=True,
        capture_output=True,
    )
    assert rejected.returncode != 0
    assert "source changes, including untracked files" in rejected.stderr


def test_operator_runbook_names_only_private_actions_not_values() -> None:
    runbook = (ROOT / "docs/REAL-VPS-AWG-NAT.md").read_text()

    assert "cd ansible" not in runbook
    assert "make deploy ANSIBLE_LIMIT=vpn-p1-web" in runbook
    assert "ANSIBLE_EXTRA_VARS_FILE=/secure/real-vps-awg-nat-forward.yml" in runbook
    assert "make awg-evidence-provision" in runbook
    assert "current_client_config" in runbook
    assert "rotated_client_config" in runbook
    assert "sentinel_ssh_private_key" in runbook
    assert "No private value belongs in inventory" in runbook
    assert "PASS" in runbook and "INFRA_UNAVAILABLE" in runbook


def test_operator_runbook_converges_the_protected_echo_cohort() -> None:
    runbook = (ROOT / "docs/REAL-VPS-AWG-NAT.md").read_text()

    assert 'COHORTS="p1-web,p2-udp"' in runbook
    assert "ANSIBLE_LIMIT=vpn-p1-web" in runbook
    assert 'COHORTS="p3-ts,p2-udp"' not in runbook
    assert "ANSIBLE_LIMIT=vpn-p3-ts" not in runbook


def test_makefile_exposes_sops_gated_awg_evidence_entrypoint() -> None:
    makefile = (ROOT / "Makefile").read_text()
    target = makefile.split("awg-evidence-provision: pre-deploy-check", 1)[1].split(
        "\n\n", 1
    )[0]

    assert 'VPN_SECRETS_FILE="$(SECRETS_FILE)"' in target
    assert "playbooks/provision-real-vps-awg-nat.yml" in target
    assert "AWG_EVIDENCE_INVENTORY=<file> required" in target
    assert "AWG_EVIDENCE_VARS=<mode-0600-file> required" in target
    assert "stat.S_IMODE(s.st_mode) == 0o600" in target
    assert "real_vps_awg_nat_secrets" not in target


def test_makefile_deploy_supports_safe_limit_and_extra_vars() -> None:
    makefile = (ROOT / "Makefile").read_text()
    target = makefile.split("\ndeploy:\n", 1)[1].split("\n\n", 1)[0]
    controller = (ROOT / "scripts/deploy-controller.py").read_text()
    extra_vars_preflight = makefile.split("validate-ansible-extra-vars:", 1)[1].split(
        "\n\n", 1
    )[0]

    assert "scripts/deploy-controller.py deploy" in target
    assert "deploy dry-run: export DEPLOY_LIMIT = $(ANSIBLE_LIMIT)" in makefile
    assert "deploy dry-run: export DEPLOY_EXTRA_VARS_FILE = $(ANSIBLE_EXTRA_VARS_FILE)" in makefile
    assert 'environment["VPN_SECRETS_FILE"] = str(secrets)' in controller
    assert '"--extra-vars", "@" + str(overrides)' in controller
    assert "stat.S_IMODE(s.st_mode) == 0o600" in extra_vars_preflight
    assert "not os.path.islink(p)" in extra_vars_preflight
    assert "ANSIBLE_EXTRA_VARS_FILE requires ANSIBLE_LIMIT" in extra_vars_preflight
    assert "validate-ansible-extra-vars.py" in extra_vars_preflight
