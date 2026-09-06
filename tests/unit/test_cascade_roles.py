"""Structural contracts for inert cascade roles and their deploy guards."""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"


def test_roles_have_required_scaffold_and_distinct_namespaces() -> None:
    for role in ("cascade-ingress", "cascade-egress"):
        root = ANSIBLE / "roles" / role
        for relative in (
            "CLAUDE.md",
            "tasks/main.yml",
            "defaults/main.yml",
            "handlers/main.yml",
        ):
            assert (root / relative).is_file()
        assert list((root / "templates").glob("*.j2"))

    ingress_policy = (
        ANSIBLE / "roles/cascade-ingress/templates/cascade-ingress.nft.j2"
    ).read_text()
    egress_policy = (
        ANSIBLE / "roles/cascade-egress/templates/cascade-egress.nft.j2"
    ).read_text()
    assert "cascade_ingress" in ingress_policy
    assert "cascade_egress" in egress_policy
    assert "split_hop" not in ingress_policy + egress_policy


def test_ingress_preflights_dataset_before_serving_configuration() -> None:
    tasks = (ANSIBLE / "roles/cascade-ingress/tasks/main.yml").read_text()

    assert tasks.index("Preflight classifier dataset") < tasks.index(
        "Render disabled classifier integration contract"
    )
    assert tasks.index("Preflight classifier dataset") < tasks.index(
        "Render cascade ingress tunnel"
    )
    assert "--check-dataset" in tasks
    assert "systemd_service" not in tasks


@pytest.mark.parametrize(
    "historical_state",
    ["service", "interface", "rule", "route", "nft", "probe-error"],
)
@pytest.mark.parametrize("check_mode", [False, True])
def test_installed_ansible_refuses_historical_cascade_state_before_writes(
    tmp_path: Path, historical_state: str, check_mode: bool
) -> None:
    """The live read-only preflight must gate every later role write."""
    executable = shutil.which("ansible-playbook")
    assert executable, "ansible-playbook is required for cascade preflight proof"

    tasks = yaml.safe_load(
        (ANSIBLE / "roles/cascade-ingress/tasks/main.yml").read_text(encoding="utf-8")
    )
    names = [task["name"] for task in tasks]
    selected = copy.deepcopy(
        tasks[
            names.index(
                "Inspect historical cascade WireGuard service state"
            ) : names.index("Install cascade ingress packages")
        ]
    )
    marker = tmp_path / "unexpected-role-write"
    selected.append(
        {
            "name": "Fixture later role write",
            "ansible.builtin.command": {"argv": ["cascade-write-marker"]},
            "check_mode": False,
        }
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    scripts = {
        "systemctl": """#!/bin/sh
if [ \"$CASCADE_STATE\" = service ]; then exit 0; fi
exit 3
""",
        "ip": """#!/bin/sh
case \"$1\" in
  link) [ \"$CASCADE_STATE\" = interface ] && exit 0; exit 1 ;;
  rule)
    [ \"$CASCADE_STATE\" = probe-error ] && exit 77
    [ \"$CASCADE_STATE\" = rule ] && printf '1000: from all lookup 203\\n'
    exit 0 ;;
  route)
    [ \"$CASCADE_STATE\" = route ] && printf 'default dev csi0\\n'
    exit 0 ;;
  *) exit 64 ;;
esac
""",
        "nft": """#!/bin/sh
[ \"$1 $2 $3\" = \"list tables \" ] || exit 64
[ \"$CASCADE_STATE\" = nft ] && printf 'table inet cascade_ingress\\n'
exit 0
""",
        "cascade-write-marker": """#!/bin/sh
: > \"$CASCADE_MARKER\"
""",
    }
    for name, content in scripts.items():
        path = bin_dir / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o700)

    playbook = tmp_path / "cascade-preflight.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "become": False,
                    "vars": {
                        "ansible_python_interpreter": sys.executable,
                        "cascade_ingress": {
                            "wg_interface": "csi0",
                            "routing_table": 203,
                        },
                    },
                    "tasks": selected,
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n", encoding="utf-8")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANSIBLE_")
    }
    environment.update(
        {
            "ANSIBLE_CONFIG": str(config),
            "PATH": f"{bin_dir}{os.pathsep}{environment['PATH']}",
            "CASCADE_STATE": historical_state,
            "CASCADE_MARKER": str(marker),
        }
    )
    command = [executable, "-i", "localhost,", "-c", "local", str(playbook)]
    if check_mode:
        command.append("--check")
    result = subprocess.run(
        command, capture_output=True, text=True, env=environment, timeout=15
    )

    assert result.returncode != 0
    assert not marker.exists()
    if historical_state == "probe-error":
        assert "Inspect historical cascade policy-routing state" in result.stdout
    else:
        assert "Refusing cascade-ingress because historical" in result.stdout


@pytest.mark.parametrize("check_mode", [False, True])
def test_installed_ansible_allows_clean_cascade_preflight_before_later_write(
    tmp_path: Path, check_mode: bool
) -> None:
    """A clean host proceeds through the same real task slice, including --check."""
    # Reuse the parametrized regression's fixture implementation with its
    # deterministic command stubs; its clean-state assertion is intentionally
    # separate so both success and every refusal case remain visible.
    executable = shutil.which("ansible-playbook")
    assert executable, "ansible-playbook is required for cascade preflight proof"

    tasks = yaml.safe_load(
        (ANSIBLE / "roles/cascade-ingress/tasks/main.yml").read_text(encoding="utf-8")
    )
    names = [task["name"] for task in tasks]
    selected = copy.deepcopy(
        tasks[
            names.index(
                "Inspect historical cascade WireGuard service state"
            ) : names.index("Install cascade ingress packages")
        ]
    )
    marker = tmp_path / "later-role-write"
    selected.append(
        {
            "name": "Fixture later role write",
            "ansible.builtin.command": {"argv": ["cascade-write-marker"]},
            "check_mode": False,
        }
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, content in {
        "systemctl": "#!/bin/sh\nexit 3\n",
        "ip": '#!/bin/sh\n[ "$1" = link ] && exit 1\nexit 0\n',
        "nft": "#!/bin/sh\nexit 0\n",
        "cascade-write-marker": '#!/bin/sh\n: > "$CASCADE_MARKER"\n',
    }.items():
        path = bin_dir / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o700)
    playbook = tmp_path / "cascade-clean-preflight.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "become": False,
                    "vars": {
                        "ansible_python_interpreter": sys.executable,
                        "cascade_ingress": {
                            "wg_interface": "csi0",
                            "routing_table": 203,
                        },
                    },
                    "tasks": selected,
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n", encoding="utf-8")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANSIBLE_")
    }
    environment.update(
        {
            "ANSIBLE_CONFIG": str(config),
            "PATH": f"{bin_dir}{os.pathsep}{environment['PATH']}",
            "CASCADE_MARKER": str(marker),
        }
    )
    command = [executable, "-i", "localhost,", "-c", "local", str(playbook)]
    if check_mode:
        command.append("--check")
    result = subprocess.run(
        command, capture_output=True, text=True, env=environment, timeout=15
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.is_file()


def test_ingress_default_route_is_inert_and_documents_scoped_mark_routing() -> None:
    role = ANSIBLE / "roles/cascade-ingress"
    config = (role / "templates/cascade-ingress.conf.j2").read_text()
    policy = (role / "templates/cascade-ingress.nft.j2").read_text()

    assert "AllowedIPs = {{ cascade_ingress.egress_allowed_ips }}" in config
    assert "Table = off" in config
    assert "fwmark {{ cascade_ingress.fwmark }}" in config
    assert "table {{ cascade_ingress.routing_table }}" in config
    assert "main routing table" in config
    assert "Egress forwarding/NAT is a separate activation contract" in config
    assert "ip route replace default" not in config
    assert "ip rule add" not in config
    assert "masquerade" not in policy
    assert "forward" not in policy

    contract = str(yaml.safe_load((role / "tasks/main.yml").read_text())[1])
    assert "cascade_ingress.routing_table | int > 0" in contract
    assert "cascade_ingress.fwmark | int > 0" in contract


def test_ingress_installs_concrete_proxy_but_unit_is_repository_disabled() -> None:
    role = ANSIBLE / "roles/cascade-ingress"
    tasks = (role / "tasks/main.yml").read_text()
    unit = (role / "templates/cascade-classifier-proxy.service.j2").read_text()

    assert "cascade-classifier-proxy.py" in tasks
    assert "cascade_classifier_lib.py" in tasks
    assert "classifier_proxy_password" in tasks
    assert "ExecCondition=/usr/bin/false" in unit
    assert "cascade-classifier-proxy.py" in unit
    assert "systemd_service" not in tasks


def test_ingress_installs_probe_machinery_but_cannot_schedule_it() -> None:
    role = ANSIBLE / "roles/cascade-ingress"
    tasks = (role / "tasks/main.yml").read_text()
    service = (role / "templates/cascade-leg-probe.service.j2").read_text()
    timer = (role / "templates/cascade-leg-probe.timer.j2").read_text()

    assert "cascade-leg-probe.py" in tasks
    assert "cascade-leg-probe-config.schema.json" in tasks
    assert "python3-jsonschema" in tasks
    assert "ExecCondition=/usr/bin/false" in service
    assert "OnUnitActiveSec=5min" in timer
    assert "systemd_service" not in tasks


def test_neither_role_has_an_operator_service_activation_switch() -> None:
    for role in ("cascade-ingress", "cascade-egress"):
        root = ANSIBLE / "roles" / role
        content = "\n".join(path.read_text() for path in root.rglob("*.yml"))

        assert "manage_service" not in content
        assert "systemd_service" not in (root / "tasks/main.yml").read_text()


def test_each_role_starts_with_direct_execution_colocation_guard() -> None:
    for role in ("cascade-ingress", "cascade-egress"):
        tasks = yaml.safe_load(
            (ANSIBLE / "roles" / role / "tasks/main.yml").read_text()
        )
        assert (
            tasks[0]["name"]
            == "Assert cascade and split-hop role families are not co-located"
        )
        assert tasks[0]["tags"] == ["always"]


@pytest.mark.parametrize(
    ("cascade_role", "split_toggle"),
    [
        ("cascade-ingress", "enable_split_hop_ingress"),
        ("cascade-ingress", "enable_split_hop_egress"),
        ("cascade-egress", "enable_split_hop_ingress"),
        ("cascade-egress", "enable_split_hop_egress"),
    ],
)
def test_direct_role_guard_covers_every_cross_family_pairing(
    cascade_role: str, split_toggle: str
) -> None:
    first = yaml.safe_load(
        (ANSIBLE / "roles" / cascade_role / "tasks/main.yml").read_text()
    )[0]
    guard = str(first)

    assert split_toggle in guard
    assert "not split_hop_role_family_enabled" in guard
    assert "cascade_role_family_enabled" not in guard


def test_egress_has_no_classifier_or_geodata_knowledge() -> None:
    role = ANSIBLE / "roles/cascade-egress"
    egress = "\n".join(
        path.read_text()
        for subtree in ("tasks", "defaults", "handlers", "templates")
        for path in (role / subtree).rglob("*")
        if path.is_file()
    )

    assert "classifier" not in egress.lower()
    assert "geoip" not in egress.lower()
    assert "geodata" not in egress.lower()


def test_cascade_roles_are_declared_disabled_and_exception_tier() -> None:
    manifest = yaml.safe_load((ANSIBLE / "role-tiers.yml").read_text())
    assert manifest["tiers"]["cascade-ingress"] == "exception"
    assert manifest["tiers"]["cascade-egress"] == "exception"
    assert manifest["cascade_governance_status"] == "implementation-only"

    defaults = yaml.safe_load((ANSIBLE / "group_vars/all.yml").read_text())["vpn"]
    assert defaults["enable_cascade_ingress"] is False
    assert defaults["enable_cascade_egress"] is False
    for relative in manifest["family_profiles"]:
        profile = yaml.safe_load((ANSIBLE / relative).read_text())
        for toggle in ("enable_cascade_ingress", "enable_cascade_egress"):
            assert profile.get("vpn", {}).get(toggle, False) is False
        assert "allow_exception_roles" not in profile


def test_site_has_attestation_and_colocation_guards_before_roles() -> None:
    site = (ANSIBLE / "playbooks/site.yml").read_text()
    first_role = site.index("  roles:")

    assert site.index("verify cascade ASN attestation") < first_role
    assert site.index("verify fresh cascade per-leg protocol completion") < first_role
    assert site.index("implementation-only governance") < first_role
    assert "lookup('file', playbook_dir ~ '/../role-tiers.yml')" in site
    assert ".cascade_governance_status == 'live-authorized'" in site
    assert site.index("mutually exclusive") < first_role
    assert site.index("classifier owns every egress decision") < first_role
    assert (
        "enable_cascade_ingress"
        in site[
            site.index("classifier owns every egress decision") : site.index(
                "verify cascade ASN attestation"
            )
        ]
    )
    assert (
        "enable_warp_outbound"
        in site[
            site.index("classifier owns every egress decision") : site.index(
                "verify cascade ASN attestation"
            )
        ]
    )
    assert site.index("role: cascade-ingress") > first_role
    assert site.index("role: cascade-egress") > first_role
