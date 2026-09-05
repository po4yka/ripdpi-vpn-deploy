"""Contracts for roles that delegate pinned binary publication to runtime-release."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def _tasks(role: str) -> list[dict]:
    return yaml.safe_load(
        (ROOT / "ansible" / "roles" / role / "tasks" / "main.yml").read_text(
            encoding="utf-8"
        )
    )


def _runtime_task(role: str) -> dict:
    matches = [
        task
        for task in _tasks(role)
        if task.get("ansible.builtin.include_role", {}).get("name")
        == "runtime-release"
        and "tasks_from" not in task["ansible.builtin.include_role"]
    ]
    assert len(matches) == 1, role
    return matches[0]


def _task(role: str, name: str) -> dict:
    matches = [task for task in _tasks(role) if task.get("name") == name]
    assert len(matches) == 1, (role, name)
    return matches[0]


@pytest.mark.parametrize(
    ("role", "install_root", "binary_name", "public_link", "artifact_type"),
    [
        (
            "hysteria-realm",
            "{{ hysteria_realm.install_root }}",
            "sing-box",
            "/usr/local/bin/sing-box-realm",
            "archive",
        ),
        (
            "snell",
            "{{ snell.install_root }}",
            "sing-box",
            "/usr/local/bin/sing-box-snell",
            "archive",
        ),
        (
            "probe-matrix-target",
            "/opt/probe-matrix/mtg",
            "mtg",
            "/usr/local/bin/probe-matrix-mtg",
            "binary",
        ),
        (
            "dns-morph-bridge",
            "{{ dns_morph_bridge.install_root }}",
            "dns-morph-bridge",
            "{{ dns_morph_bridge.bin_path }}",
            "binary",
        ),
    ],
)
def test_binary_consumers_delegate_publication_to_runtime_release(
    role: str,
    install_root: str,
    binary_name: str,
    public_link: str,
    artifact_type: str,
) -> None:
    task = _runtime_task(role)
    contract = task["vars"]

    assert contract["runtime_release_install_root"] == install_root
    assert contract["runtime_release_binary_name"] == binary_name
    assert contract["runtime_release_public_link"] == public_link
    assert contract["runtime_release_artifact_type"] == artifact_type
    assert set(contract["runtime_release_urls"]) == {"amd64", "arm64"}
    assert set(contract["runtime_release_sha256"]) == {"amd64", "arm64"}
    assert set(contract["runtime_release_arch_slugs"]) == {"amd64", "arm64"}

    source = (
        ROOT / "ansible" / "roles" / role / "tasks" / "main.yml"
    ).read_text(encoding="utf-8")
    assert "ansible.builtin.get_url:" not in source
    assert "ansible.builtin.unarchive:" not in source


@pytest.mark.parametrize(
    ("role", "name", "handler"),
    [
        (
            "hysteria-realm",
            "Notify hysteria-realm restart after runtime release activation",
            "Restart hysteria-realm",
        ),
        (
            "snell",
            "Notify Snell restart after runtime release activation",
            "Restart snell",
        ),
        (
            "probe-matrix-target",
            "Notify probe matrix mtg restart after runtime release activation",
            "Restart probe matrix mtg",
        ),
        (
            "dns-morph-bridge",
            "Notify DNS-Morph bridge restart after runtime release activation",
            "Restart dns-morph-bridge",
        ),
    ],
)
def test_consumers_propagate_real_activation_without_check_mode_handlers(
    role: str, name: str, handler: str
) -> None:
    task = _task(role, name)
    assert task["changed_when"] == "runtime_release_changed | bool"
    assert task["when"] == "not ansible_check_mode"
    assert task["notify"] == handler


def test_archive_consumers_pin_one_exact_member_for_each_architecture() -> None:
    realm = _runtime_task("hysteria-realm")["vars"]
    snell = _runtime_task("snell")["vars"]

    for contract, version in (
        (realm, "hysteria_realm.version"),
        (snell, "snell.version"),
    ):
        assert contract["runtime_release_archive_strip_components"] == 1
        assert contract["runtime_release_archive_members"] == {
            "amd64": (
                "sing-box-{{ "
                + version
                + " | regex_replace('^v', '') }}-linux-amd64/sing-box"
            ),
            "arm64": (
                "sing-box-{{ "
                + version
                + " | regex_replace('^v', '') }}-linux-arm64/sing-box"
            ),
        }


def test_xray_prebuilt_path_delegates_archive_activation_only() -> None:
    task = _runtime_task("xray-runtime")
    contract = task["vars"]

    assert task["when"] == "not xray_runtime_build_from_source | bool"
    assert contract["runtime_release_version"] == "{{ xray.version }}"
    assert contract["runtime_release_install_root"] == "{{ xray_install_dir }}"
    assert contract["runtime_release_binary_name"] == "xray"
    assert contract["runtime_release_public_link"] == "/usr/local/bin/xray"
    assert contract["runtime_release_artifact_type"] == "archive"
    assert contract["runtime_release_archive_members"] == {
        "amd64": "xray",
        "arm64": "xray",
    }
    assert contract["runtime_release_archive_strip_components"] == 0

    source = (
        ROOT / "ansible" / "roles" / "xray-runtime" / "tasks" / "main.yml"
    ).read_text(encoding="utf-8")
    assert "ansible.builtin.get_url:" not in source
    assert "ansible.builtin.unarchive:" not in source


def test_xray_source_publication_remains_separate_and_idempotent() -> None:
    current = _task("xray-runtime", "Point current Xray runtime at pinned release")
    public = _task("xray-runtime", "Expose pinned Xray runtime")
    publish = _task("xray-runtime", "Publish Xray runtime change state")
    expression = publish["ansible.builtin.set_fact"]["xray_runtime_changed"]

    assert current["when"] == "xray_runtime_build_from_source | bool"
    assert public["when"] == "xray_runtime_build_from_source | bool"
    assert "runtime_release_changed | default(false)" in expression
    assert "runtime_build_results | default({})" in expression
    assert "xray_runtime_build_from_source" in expression


def test_direct_binary_consumers_bind_version_to_immutable_identity() -> None:
    mtg = _runtime_task("probe-matrix-target")["vars"]
    bridge = _runtime_task("dns-morph-bridge")["vars"]

    assert mtg["runtime_release_version"] == (
        "{{ probe_matrix_target_secrets.mtg_version }}"
    )
    assert bridge["runtime_release_version"] == (
        "sha256-{{ dns_morph_bridge_secrets.binary_sha256 | lower }}"
    )
