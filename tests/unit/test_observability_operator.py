"""Bounded operator surface for the centralized observability roles."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "observability-operator.py"


def _write(path: Path, content: str, mode: int = 0o600) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)
    return path


@pytest.fixture
def operator(tmp_path: Path) -> dict[str, object]:
    key = _write(tmp_path / "id_ed25519", "fixture-key\n")
    known_hosts = _write(
        tmp_path / "known_hosts", "fixture.invalid ssh-ed25519 AAAA\n", 0o644
    )
    inventory = _write(
        tmp_path / "inventory.ini",
        """[vpn]
node-agent ansible_host=agent.fixture.invalid ansible_user=deploy ansible_port=22 env=staging observability_host_class=vpn

[vpn-observability-control]
node-a ansible_host=fixture.invalid ansible_user=deploy ansible_port=22 env=staging observability_host_class=control-plane

[vpn-observability-deadman]
node-deadman ansible_host=deadman.fixture.invalid ansible_user=deploy ansible_port=22 env=staging observability_host_class=deadman

[observability:children]
vpn
vpn-observability-control
vpn-observability-deadman

[vpn:vars]
ansible_ssh_private_key_file={key}
ansible_python_interpreter=/usr/bin/python3

[observability:vars]
ansible_ssh_private_key_file={key}
ansible_python_interpreter=/usr/bin/python3
observability_topology_b64=eyJzY2hlbWFfdmVyc2lvbiI6MX0=
""".format(key=key),
        0o644,
    )
    secrets = _write(tmp_path / "secrets.yml", "observability_secrets: {{}}\n")
    variables = _write(
        tmp_path / "vars.yml",
        "observability_control_plane:\n  enabled: true\n  config_root: /etc/observability-control-plane\n",
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "calls.jsonl"
    recorder = f"""#!{sys.executable}
import json, os, pathlib, sys
log = pathlib.Path({str(log)!r})
entry = {{'program': pathlib.Path(sys.argv[0]).name, 'argv': sys.argv[1:]}}
if entry['program'] == 'ansible-playbook':
    for value in sys.argv[1:]:
        candidate = pathlib.Path(value)
        if candidate.suffix in ('.yml', '.yaml') and candidate.exists():
            entry['playbook'] = candidate.read_text()
            break
    if '-i' in entry['argv']:
        entry['inventory'] = pathlib.Path(entry['argv'][entry['argv'].index('-i') + 1]).read_text()
    entry['environment'] = {{key: os.environ.get(key) for key in (
        'ANSIBLE_ACTION_PLUGINS', 'ANSIBLE_CALLBACK_PLUGINS',
        'ANSIBLE_FILTER_PLUGINS', 'ANSIBLE_LOOKUP_PLUGINS',
        'ANSIBLE_VARS_ENABLED', 'ANSIBLE_HOME',
    )}}
    print('secret-path=' + os.environ.get('VPN_SECRETS_FILE', 'missing'))
    print('token=fixture-secret-value', file=sys.stderr)
with log.open('a') as stream:
    stream.write(json.dumps(entry) + '\\n')
if entry['program'] == 'ssh':
    payload = sys.stdin.read()
    entry = {{'program': 'ssh-payload', 'payload': payload}}
    with log.open('a') as stream:
        stream.write(json.dumps(entry) + '\\n')
    if 'previous =' in payload:
        print(json.dumps({{'schema_version': 1, 'component': 'control-plane', 'state': 'retained', 'generation': 'a' * 64}}))
    elif '/v1/silences' in payload:
        print(json.dumps({{'schema_version': 1, 'component': 'control-plane', 'state': 'deleted' if 'DELETE' in payload else 'created', 'silence_id': '12345678-1234-4234-8234-1234567890ab'}}))
    elif '/api/v2/alerts' in payload:
        print(json.dumps({{'schema_version': 1, 'component': 'control-plane', 'receiver': 'telegram-primary', 'state': 'submitted'}}))
    else:
        print(json.dumps({{'schema_version': 1, 'component': 'control-plane', 'state': 'healthy', 'units': {{'nginx.service': 'active', 'observability-prometheus.service': 'active', 'observability-alertmanager.service': 'active', 'observability-telegram-relay.service': 'active', 'observability-silence-gateway.service': 'active', 'observability-control-plane-adapter.timer': 'active', 'observability-protocol-liveness-adapter.timer': 'active', 'observability-deadman-pipeline.service': 'active', 'observability-deadman-pulse.timer': 'active', 'observability-primary-canary.timer': 'active'}}}}))
"""
    for name in ("ansible-playbook", "ssh"):
        _write(binary / name, recorder, 0o700)
    git = f"""#!{sys.executable}
import os, sys
args = sys.argv[1:]
if 'rev-parse' in args:
    print('0' * 40)
elif 'ls-tree' in args:
    pass
elif 'diff' in args:
    raise SystemExit(1 if os.environ.get('FIXTURE_GIT_DIRTY') == '1' else 0)
elif 'status' in args:
    pass
else:
    raise SystemExit(2)
"""
    _write(binary / "git", git, 0o700)
    environment = {
        **os.environ,
        "PATH": str(binary) + os.pathsep + os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    common = [
        "--inventory",
        str(inventory),
        "--host",
        "node-a",
        "--environment",
        "staging",
        "--component",
        "control-plane",
        "--known-hosts",
        str(known_hosts),
    ]
    return {
        "tmp": tmp_path,
        "log": log,
        "env": environment,
        "common": common,
        "secrets": secrets,
        "vars": variables,
        "git": binary / "git",
    }


def _run(
    operator: dict[str, object], command: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), command, *operator["common"], *arguments],
        cwd=ROOT,
        env=operator["env"],
        text=True,
        capture_output=True,
        timeout=20,
    )


def _operator_module() -> object:
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec = importlib.util.spec_from_file_location("observability_operator", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def _calls(operator: dict[str, object]) -> list[dict[str, object]]:
    path = operator["log"]
    assert isinstance(path, Path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize(
    "command", ["render", "validate", "deploy", "rotate", "rollback"]
)
def test_secret_consuming_commands_fail_before_execution_without_private_secrets(
    operator: dict[str, object], command: str
) -> None:
    extra = ("--confirm",) if command in {"deploy", "rotate"} else ()
    result = _run(operator, command, "--vars", str(operator["vars"]), *extra)

    assert result.returncode == 2
    assert result.stderr == "observability-operator: private secrets required\n"
    assert _calls(operator) == []


def test_render_is_one_role_check_mode_for_one_exact_host(
    operator: dict[str, object],
) -> None:
    result = _run(
        operator,
        "render",
        "--secrets",
        str(operator["secrets"]),
        "--vars",
        str(operator["vars"]),
    )

    assert result.returncode == 0, result.stderr
    call = _calls(operator)[0]
    assert call["program"] == "ansible-playbook"
    assert "--check" in call["argv"]
    assert call["argv"][call["argv"].index("--limit") + 1] == "node-a"
    assert "site.yml" not in " ".join(call["argv"])
    assert "hosts: node-a" in call["playbook"]
    assert "observability_control_plane" in call["playbook"]
    assert "observability_agent" not in call["playbook"]
    assert (
        str(operator["tmp"])
        not in call["inventory"].split("ansible_ssh_private_key_file=")[0]
    )
    assert "ControlMaster=no" in call["inventory"]
    assert "ProxyCommand=none" in call["inventory"]
    assert "UserKnownHostsFile=" in call["inventory"]
    assert call["environment"] == {
        "ANSIBLE_ACTION_PLUGINS": os.devnull,
        "ANSIBLE_CALLBACK_PLUGINS": os.devnull,
        "ANSIBLE_FILTER_PLUGINS": os.devnull,
        "ANSIBLE_LOOKUP_PLUGINS": os.devnull,
        "ANSIBLE_VARS_ENABLED": "",
        "ANSIBLE_HOME": call["environment"]["ANSIBLE_HOME"],
    }
    assert call["environment"]["ANSIBLE_HOME"].endswith("/ansible-home")
    assert str(operator["secrets"]) not in result.stdout + result.stderr
    assert "fixture-secret-value" not in result.stdout + result.stderr


def test_isolated_child_environment_supports_builtin_lookup_and_selected_role(
    tmp_path: Path,
) -> None:
    module = _operator_module()
    child = tmp_path / "operator-child"
    child.mkdir(mode=0o700)
    secrets = _write(child / "secrets.yml", "observability_secrets: {}\n")
    inventory = _write(
        child / "inventory.ini",
        "[vpn]\nnode-a ansible_host=127.0.0.1 ansible_user=deploy ansible_port=22\n",
    )
    playbook = _write(
        child / "playbook.yml",
        module._playbook("control-plane", "node-a"),
    )
    environment = module._environment(secrets)
    environment["ANSIBLE_HOME"] = str(child / "ansible-home")
    executable = shutil.which("ansible-playbook")
    assert executable is not None

    result = subprocess.run(
        [
            executable,
            str(playbook),
            "-i",
            str(inventory),
            "--limit",
            "node-a",
            "--syntax-check",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert stat.S_IMODE(inventory.stat().st_mode) == 0o600
    assert "VPN_SECRETS_FILE" in playbook.read_text(encoding="utf-8")
    assert "role: observability_control_plane" in playbook.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert f"playbook: {playbook}" in result.stdout


def test_validate_uses_syntax_check_without_contacting_the_host(
    operator: dict[str, object],
) -> None:
    result = _run(
        operator,
        "validate",
        "--secrets",
        str(operator["secrets"]),
        "--vars",
        str(operator["vars"]),
    )

    assert result.returncode == 0, result.stderr
    call = _calls(operator)[0]
    assert call["program"] == "ansible-playbook"
    assert "--syntax-check" in call["argv"]
    assert "--check" not in call["argv"]


def test_status_is_secretless_read_only_and_redacted(
    operator: dict[str, object],
) -> None:
    result = _run(operator, "status")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    source_revision = report.pop("controller_source_revision")
    deployable_digest = report.pop("controller_deployable_digest")
    assert len(source_revision) == 40
    assert len(deployable_digest) == 64
    assert report == {
        "component": "control-plane",
        "host": "node-a",
        "schema_version": 1,
        "state": "healthy",
        "units": {
            "nginx.service": "active",
            "observability-prometheus.service": "active",
            "observability-alertmanager.service": "active",
            "observability-telegram-relay.service": "active",
            "observability-silence-gateway.service": "active",
            "observability-control-plane-adapter.timer": "active",
            "observability-protocol-liveness-adapter.timer": "active",
            "observability-deadman-pipeline.service": "active",
            "observability-deadman-pulse.timer": "active",
            "observability-primary-canary.timer": "active",
        },
    }
    observed = _calls(operator)
    assert [entry["program"] for entry in observed] == ["ssh", "ssh-payload"]
    payload = observed[1]["payload"]
    assert "journalctl" not in payload
    assert "Environment" not in payload
    assert "systemctl" in payload
    assert "observability-deadman-pulse.service" not in payload
    assert "observability-primary-canary.service" not in payload


def test_drill_is_staging_only_and_needs_explicit_notification_confirmation(
    operator: dict[str, object],
) -> None:
    result = _run(operator, "drill")
    assert result.returncode == 2
    assert result.stderr == "observability-operator: --confirm-notification required\n"
    assert _calls(operator) == []

    common = operator["common"]
    assert isinstance(common, list)
    common[common.index("staging")] = "prod"
    result = _run(operator, "drill", "--confirm-notification")
    assert result.returncode == 2
    assert result.stderr == "observability-operator: drills require staging\n"
    assert _calls(operator) == []


def test_drill_requires_named_gateway_owner_before_transport(operator):
    result = _run(operator, "drill", "--confirm-notification")
    assert result.returncode == 2
    assert result.stderr == "observability-operator: valid --silence-owner required\n"
    assert _calls(operator) == []


@pytest.mark.parametrize("owner", ["../owner", "owner/other", "Owner", "a" * 65])
def test_drill_rejects_unsafe_gateway_owner_before_transport(operator, owner):
    result = _run(operator, "drill", "--confirm-notification", "--silence-owner", owner)
    assert result.returncode == 2
    assert result.stderr == "observability-operator: valid --silence-owner required\n"
    assert _calls(operator) == []


def test_rotate_is_explicit_exact_host_role_convergence(
    operator: dict[str, object],
) -> None:
    result = _run(
        operator,
        "rotate",
        "--secrets",
        str(operator["secrets"]),
        "--vars",
        str(operator["vars"]),
        "--confirm",
    )

    assert result.returncode == 0, result.stderr
    call = _calls(operator)[0]
    assert "--check" not in call["argv"]
    assert call["argv"][call["argv"].index("--limit") + 1] == "node-a"
    assert "site.yml" not in " ".join(call["argv"])
    assert (
        "Refuse replacing an existing observability deployment" not in call["playbook"]
    )


def test_deploy_requires_confirmation_before_transport(
    operator: dict[str, object],
) -> None:
    result = _run(
        operator,
        "deploy",
        "--secrets",
        str(operator["secrets"]),
        "--vars",
        str(operator["vars"]),
    )

    assert result.returncode == 2
    assert result.stderr == "observability-operator: --confirm required\n"
    assert _calls(operator) == []


def test_deploy_is_initial_only_exact_host_role_convergence(
    operator: dict[str, object],
) -> None:
    result = _run(
        operator,
        "deploy",
        "--secrets",
        str(operator["secrets"]),
        "--vars",
        str(operator["vars"]),
        "--confirm",
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["state"] == "deployed"
    call = _calls(operator)[0]
    assert "--check" not in call["argv"]
    assert call["argv"][call["argv"].index("--limit") + 1] == "node-a"
    assert "site.yml" not in " ".join(call["argv"])
    assert "Refuse replacing an existing observability deployment" in call["playbook"]
    assert "/etc/systemd/system/observability-prometheus.service" in call["playbook"]


@pytest.mark.parametrize(
    ("component", "marker"),
    [
        ("agent", "/etc/systemd/system/observability-agent.service"),
        (
            "control-plane",
            "/etc/systemd/system/observability-prometheus.service",
        ),
        ("deadman", "/etc/systemd/system/observability-deadman.service"),
    ],
)
def test_initial_playbook_refuses_existing_component_marker(
    component: str, marker: str
) -> None:
    module = _operator_module()
    payload = yaml.safe_load(module._playbook(component, "node-a", initial=True))[0]

    assert payload["pre_tasks"][0]["ansible.builtin.stat"] == {
        "path": marker,
        "follow": False,
    }
    refusal = payload["pre_tasks"][1]["ansible.builtin.assert"]
    assert refusal["that"] == ["not observability_install_marker.stat.exists"]
    assert "observability-rotate" in refusal["fail_msg"]
    assert "observability-remove" in refusal["fail_msg"]


def test_rollback_reconverges_one_role_from_private_last_known_good_inputs(
    operator: dict[str, object],
) -> None:
    result = _run(
        operator,
        "rollback",
        "--secrets",
        str(operator["secrets"]),
        "--vars",
        str(operator["vars"]),
        "--confirm",
    )
    assert result.returncode == 2
    assert result.stderr == "observability-operator: rollback manifest required\n"
    assert _calls(operator) == []

    generation = "a" * 64
    secrets = operator["secrets"]
    variables = operator["vars"]
    assert isinstance(secrets, Path) and isinstance(variables, Path)
    manifest = _write(
        operator["tmp"] / "rollback.json",
        json.dumps(
            {
                "schema_version": 1,
                "host": "node-a",
                "component": "control-plane",
                "previous_generation": generation,
                "vars_sha256": __import__("hashlib")
                .sha256(variables.read_bytes())
                .hexdigest(),
                "secrets_sha256": __import__("hashlib")
                .sha256(secrets.read_bytes())
                .hexdigest(),
            }
        ),
    )

    result = _run(
        operator,
        "rollback",
        "--secrets",
        str(operator["secrets"]),
        "--vars",
        str(operator["vars"]),
        "--rollback-manifest",
        str(manifest),
        "--confirm",
    )
    assert result.returncode == 0, result.stderr
    calls = _calls(operator)
    assert [entry["program"] for entry in calls] == [
        "ssh",
        "ssh-payload",
        "ansible-playbook",
    ]
    call = calls[-1]
    assert call["program"] == "ansible-playbook"
    assert call["argv"][call["argv"].index("--limit") + 1] == "node-a"
    assert "observability_control_plane" in call["playbook"]
    assert "site.yml" not in " ".join(call["argv"])


def test_remove_converges_only_selected_role_with_enabled_false(
    operator: dict[str, object],
) -> None:
    result = _run(operator, "remove", "--confirm")
    assert result.returncode == 2
    assert (
        result.stderr
        == "observability-operator: private deployment snapshot required\n"
    )

    variables = operator["vars"]
    assert isinstance(variables, Path)
    variables.write_text(
        "observability_control_plane:\n  enabled: true\n  config_root: /owner/custom-observability\n",
        encoding="utf-8",
    )
    result = _run(operator, "remove", "--vars", str(variables), "--confirm")

    assert result.returncode == 0, result.stderr
    call = _calls(operator)[0]
    assert call["argv"][call["argv"].index("--limit") + 1] == "node-a"
    assert "observability_control_plane" in call["playbook"]
    assert "enabled: false" in call["playbook"]
    assert "/owner/custom-observability" in call["playbook"]
    assert "site.yml" not in " ".join(call["argv"])


def test_debug_diff_and_unsafe_files_fail_closed(operator: dict[str, object]) -> None:
    environment = operator["env"]
    assert isinstance(environment, dict)
    environment["ANSIBLE_DEBUG"] = "true"
    result = _run(operator, "status")
    assert result.returncode == 2
    assert (
        result.stderr == "observability-operator: Ansible debug or diff is forbidden\n"
    )
    assert _calls(operator) == []

    environment.pop("ANSIBLE_DEBUG")
    secrets = operator["secrets"]
    assert isinstance(secrets, Path)
    secrets.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
    result = _run(
        operator, "render", "--secrets", str(secrets), "--vars", str(operator["vars"])
    )
    assert result.returncode == 2
    assert result.stderr == "observability-operator: private secrets required\n"
    assert _calls(operator) == []


def test_dirty_deployable_source_refuses_before_inventory_or_transport(
    operator: dict[str, object],
) -> None:
    git = operator["git"]
    assert isinstance(git, Path)
    git.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *rev-parse*) printf '%040d\\n' 0 ;;\n"
        "  *ls-tree*) exit 0 ;;\n"
        "  *diff*) exit 1 ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    git.chmod(0o700)
    result = _run(operator, "status")
    assert result.returncode == 2
    assert result.stderr.startswith("observability-operator: source dirty revision=")
    assert _calls(operator) == []


def test_untracked_discovery_path_refuses_before_ansible(
    operator: dict[str, object],
) -> None:
    git = operator["git"]
    assert isinstance(git, Path)
    git.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *rev-parse*) printf '%040d\\n' 0 ;;\n"
        "  *ls-tree*|*diff*) exit 0 ;;\n"
        "  *status*) printf '?? ansible/roles/observability_control_plane/lookup_plugins/unsafe.py\\0' ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    git.chmod(0o700)
    result = _run(
        operator,
        "render",
        "--secrets",
        str(operator["secrets"]),
        "--vars",
        str(operator["vars"]),
    )
    assert result.returncode == 2
    assert (
        result.stderr == "observability-operator: unsupported Ansible discovery path\n"
    )
    assert _calls(operator) == []


def test_component_commands_reject_disabled_or_wrong_role_variables(
    operator: dict[str, object],
) -> None:
    variables = operator["vars"]
    assert isinstance(variables, Path)
    for content, expected in (
        (
            "observability_control_plane:\n  enabled: false\n",
            "enabled component variables required",
        ),
        ("observability_agent:\n  enabled: true\n", "private variables rejected"),
    ):
        variables.write_text(content, encoding="utf-8")
        result = _run(
            operator,
            "render",
            "--secrets",
            str(operator["secrets"]),
            "--vars",
            str(variables),
        )
        assert result.returncode == 2
        assert result.stderr == f"observability-operator: {expected}\n"
        assert _calls(operator) == []


def test_host_must_match_explicit_environment_and_component_class(
    operator: dict[str, object],
) -> None:
    common = operator["common"]
    assert isinstance(common, list)
    common[common.index("staging")] = "prod"
    result = _run(operator, "status")
    assert result.returncode == 2
    assert result.stderr == "observability-operator: inventory scope rejected\n"
    assert _calls(operator) == []

    common[common.index("prod")] = "staging"
    common[common.index("control-plane")] = "deadman"
    result = _run(operator, "status")
    assert result.returncode == 2
    assert result.stderr == "observability-operator: exact inventory host rejected\n"
    assert _calls(operator) == []


@pytest.mark.parametrize(
    ("component", "host", "expected_address"),
    [
        ("agent", "node-agent", "agent.fixture.invalid"),
        ("control-plane", "node-a", "fixture.invalid"),
        ("deadman", "node-deadman", "deadman.fixture.invalid"),
    ],
)
def test_generated_style_inventory_selects_the_exact_component_section(
    operator: dict[str, object], component: str, host: str, expected_address: str
) -> None:
    module = _operator_module()
    common = operator["common"]
    assert isinstance(common, list)
    arguments = list(common)
    arguments[arguments.index("node-a")] = host
    arguments[arguments.index("control-plane")] = component
    args = module._parser().parse_args(["status", *arguments])

    selected = module._selected_host(args)
    module._require_inventory_scope(args, selected)

    assert selected["name"] == host
    assert selected["address"] == expected_address
    assert selected["variables"]["observability_host_class"] == (
        "vpn" if component == "agent" else component
    )
    assert "ControlMaster=no" in module.fleet_inspection.ssh_command(
        selected, Path(arguments[arguments.index("--known-hosts") + 1])
    )


@pytest.mark.parametrize(
    "mutation",
    [
        (
            "[vpn-observability-control]\\n"
            "node-a ansible_host=duplicate.fixture.invalid ansible_user=deploy ansible_port=22 env=staging observability_host_class=control-plane"
        ),
        "ansible_ssh_common_args='-o ProxyCommand=unsafe'",
        "env=staging observability_host_class=deadman",
    ],
)
def test_component_inventory_rejects_duplicate_unsafe_or_wrong_class(
    operator: dict[str, object], mutation: str
) -> None:
    module = _operator_module()
    common = operator["common"]
    assert isinstance(common, list)
    inventory = Path(common[common.index("--inventory") + 1])
    source = inventory.read_text(encoding="utf-8")
    if mutation.startswith("["):
        source += "\\n" + mutation + "\\n"
    else:
        source = source.replace(
            "node-a ansible_host=fixture.invalid ansible_user=deploy ansible_port=22 env=staging observability_host_class=control-plane",
            "node-a ansible_host=fixture.invalid ansible_user=deploy ansible_port=22 "
            + mutation,
        )
    inventory.write_text(source, encoding="utf-8")
    args = module._parser().parse_args(["status", *common])

    with pytest.raises(module.OperatorError):
        selected = module._selected_host(args)
        module._require_inventory_scope(args, selected)


def test_makefile_exposes_only_narrow_observability_controller_targets() -> None:
    source = (ROOT / "Makefile").read_text(encoding="utf-8")
    for command in (
        "render",
        "validate",
        "status",
        "drill",
        "deploy",
        "rotate",
        "rollback",
        "remove",
    ):
        assert f"observability-{command}:" in source
    block = source[
        source.index("observability-render:") : source.index("observability-remove:")
        + 400
    ]
    assert "scripts/observability-operator.py" in block
    assert "site.yml" not in block
    assert "OBSERVABILITY_ENVIRONMENT ?= $(ENV)" not in source
    assert "require OBSERVABILITY_ENVIRONMENT explicitly" in source
    assert "--rollback-manifest" in block
    assert "observability-operator.py deploy" in block
    assert "--confirm" in block


def test_make_status_forwards_literal_exact_scope(operator: dict[str, object]) -> None:
    common = operator["common"]
    assert isinstance(common, list)
    values = dict(zip(common[::2], common[1::2]))
    result = subprocess.run(
        [
            "make",
            "observability-status",
            f"OBSERVABILITY_INVENTORY={values['--inventory']}",
            f"OBSERVABILITY_HOST={values['--host']}",
            f"OBSERVABILITY_ENVIRONMENT={values['--environment']}",
            f"OBSERVABILITY_COMPONENT={values['--component']}",
            f"OBSERVABILITY_KNOWN_HOSTS={values['--known-hosts']}",
        ],
        cwd=ROOT,
        env=operator["env"],
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["host"] == "node-a"
    assert [entry["program"] for entry in _calls(operator)] == [
        "ssh",
        "ssh-payload",
    ]


def test_make_deploy_forwards_exact_scope_and_private_inputs(
    operator: dict[str, object],
) -> None:
    common = operator["common"]
    assert isinstance(common, list)
    values = dict(zip(common[::2], common[1::2]))
    result = subprocess.run(
        [
            "make",
            "observability-deploy",
            f"OBSERVABILITY_INVENTORY={values['--inventory']}",
            f"OBSERVABILITY_HOST={values['--host']}",
            f"OBSERVABILITY_ENVIRONMENT={values['--environment']}",
            f"OBSERVABILITY_COMPONENT={values['--component']}",
            f"OBSERVABILITY_KNOWN_HOSTS={values['--known-hosts']}",
            f"OBSERVABILITY_SECRETS_FILE={operator['secrets']}",
            f"OBSERVABILITY_VARS={operator['vars']}",
        ],
        cwd=ROOT,
        env=operator["env"],
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "deployed"
    call = _calls(operator)[0]
    assert call["program"] == "ansible-playbook"
    assert "Refuse replacing an existing observability deployment" in call["playbook"]


def test_make_never_inherits_prod_environment_for_operator_targets(
    operator: dict[str, object],
) -> None:
    environment = operator["env"]
    assert isinstance(environment, dict)
    environment["ENV"] = "prod"
    result = subprocess.run(
        ["make", "observability-status"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "OBSERVABILITY_ENVIRONMENT explicitly" in result.stderr
    assert _calls(operator) == []


class _DrillResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_DrillResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, *_: object) -> bytes:
        return self._payload


def _run_drill_program(
    monkeypatch: pytest.MonkeyPatch, alerts: list[dict[str, object]]
) -> list[object]:
    import time
    import urllib.request

    calls: list[object] = []
    monotonic = iter((0.0, 31.0))

    def urlopen(request: object, *, timeout: int) -> _DrillResponse:
        assert timeout == 5
        calls.append(request)
        assert isinstance(request, urllib.request.Request)
        assert request.full_url == "http://127.0.0.1:19094/api/v2/alerts"
        assert request.get_header("Authorization") == "Bearer " + "a" * 64
        if request.get_method() == "POST":
            return _DrillResponse(202, {})
        return _DrillResponse(200, alerts)

    from types import SimpleNamespace

    def build_opener(handler, redirect):
        assert isinstance(redirect, urllib.request.HTTPRedirectHandler)
        assert isinstance(handler, urllib.request.ProxyHandler)
        assert handler.proxies == {}
        return SimpleNamespace(open=urlopen)

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    monkeypatch.setattr(time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(time, "sleep", lambda _: pytest.fail("unexpected drill sleep"))
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index("def _drill_program")
    end = source.index("def _remote", start)
    gateway_start = source.index("def _gateway_program")
    gateway_end = source.index("def _status_program", gateway_start)
    namespace: dict[str, object] = {}
    exec(compile(source[gateway_start:gateway_end], str(SCRIPT), "exec"), namespace)
    gateway = namespace["_gateway_program"]("operator")
    # Credential reader has separate filesystem tests; keep this routing test hermetic.
    gateway = (
        gateway[: gateway.index("gateway_token =")]
        + "gateway_token = '"
        + "a" * 64
        + "'\n"
        + gateway[gateway.index("gateway_opener =") :]
    )
    namespace["_gateway_program"] = lambda owner: gateway
    exec(compile(source[start:end], str(SCRIPT), "exec"), namespace)
    program = namespace["_drill_program"]("operator")
    exec(compile(program, "drill-program", "exec"), {})
    return calls


def test_drill_waits_past_group_wait_and_proves_receiver_before_resolve(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    labels = {
        "alertname": "ObservabilitySyntheticDrill",
        "component": "control-plane",
        "environment": "staging",
        "severity": "warning",
    }
    calls = _run_drill_program(
        monkeypatch,
        [
            {
                "labels": labels,
                "status": {"state": "active"},
                "receivers": [{"name": "telegram-primary"}],
            }
        ],
    )

    result = json.loads(capsys.readouterr().out)
    assert result == {
        "component": "control-plane",
        "receiver": "telegram-primary",
        "schema_version": 1,
        "state": "submitted",
    }
    assert len(calls) == 3
    assert isinstance(calls[0], __import__("urllib.request").request.Request)
    assert calls[1].get_method() == "GET"
    assert isinstance(calls[2], __import__("urllib.request").request.Request)


def test_drill_refuses_active_alert_without_expected_receiver_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = {
        "alertname": "ObservabilitySyntheticDrill",
        "component": "control-plane",
        "environment": "staging",
        "severity": "warning",
    }
    with pytest.raises(RuntimeError, match="receiver routing evidence missing"):
        _run_drill_program(
            monkeypatch,
            [
                {
                    "labels": labels,
                    "status": {"state": "active"},
                    "receivers": [{"name": "wrong-receiver"}],
                }
            ],
        )
    # The resolve POST is unreachable when routing evidence is absent.
    # The helper raises before returning its local call list.


def test_rollback_program_refuses_same_basename_outside_expected_generation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "observability"
    generations = root / "generations"
    generations.mkdir(parents=True)
    root.chmod(0o755)
    generations.chmod(0o755)
    generation = "a" * 64
    expected = generations / f"{generation}.yml"
    expected.write_text("expected\n", encoding="utf-8")
    expected.chmod(0o644)
    previous = root / "previous.yml"
    previous.symlink_to(expected)

    source = SCRIPT.read_text(encoding="utf-8")
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        namespace: dict[str, object] = {"__file__": str(SCRIPT)}
        exec(compile(source, str(SCRIPT), "exec"), namespace)
    finally:
        sys.path.pop(0)
    program = namespace["_rollback_program"](str(root), generation)
    accepted = subprocess.run(
        [sys.executable, "-c", program.decode("utf-8")],
        text=True,
        capture_output=True,
        check=False,
    )
    assert accepted.returncode == 0
    assert json.loads(accepted.stdout)["generation"] == generation

    previous.unlink()
    foreign = tmp_path / "foreign" / expected.name
    foreign.parent.mkdir()
    foreign.write_text("foreign\n", encoding="utf-8")
    foreign.chmod(0o644)
    previous.symlink_to(foreign)
    rejected = subprocess.run(
        [sys.executable, "-c", program.decode("utf-8")],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert rejected.stdout == ""


def _gateway_token_reader():
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index("def _gateway_program")
    end = source.index("def _status_program", start)
    namespace = {}
    exec(compile(source[start:end], str(SCRIPT), "exec"), namespace)
    program = namespace["_gateway_program"]("operator")
    exec(
        compile(program[: program.index("gateway_token =")], "gateway-reader", "exec"),
        namespace,
    )
    return namespace["read_gateway_token"]


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "symlink",
        "hardlink",
        "mode",
        "oversize",
        "bad-token",
        "directory",
        "ancestor-symlink",
        "ancestor-writable",
        "root-writable",
    ],
)
def test_gateway_token_reader_requires_private_regular_anchored_file(
    tmp_path, monkeypatch, mutation
):
    import os
    import stat
    from types import SimpleNamespace

    root = tmp_path / "credentials"
    root.mkdir(mode=0o700)
    token = root / "silence-owner-operator-token"
    token.write_text("a" * 64 + "\n")
    token.chmod(0o600)
    actual_fstat = os.fstat

    def fixture_fstat(fd):
        value = actual_fstat(fd)
        # This test exercises no-follow/mode/type checks on a user-owned fixture.
        # Root identity is tested separately; no production UID guard is changed.
        return SimpleNamespace(
            st_uid=0,
            st_mode=value.st_mode,
            st_nlink=value.st_nlink,
            st_size=value.st_size,
        )

    monkeypatch.setattr(os, "fstat", fixture_fstat)
    # macOS pytest ancestors may be writable; anchor at fixture root for traversal.
    actual_open = os.open

    def fixture_open(path, flags, *args, **kwargs):
        return actual_open(tmp_path if path == "/" else path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", fixture_open)
    if mutation == "symlink":
        token.rename(root / "other")
        token.symlink_to("other")
    elif mutation == "hardlink":
        os.link(token, root / "other")
    elif mutation == "mode":
        token.chmod(0o644)
    elif mutation == "oversize":
        token.write_text("a" * 66)
    elif mutation == "bad-token":
        token.write_text("Z" * 64)
    elif mutation == "directory":
        token.unlink()
        token.mkdir()
    elif mutation == "ancestor-symlink":
        root.rename(tmp_path / "other")
        root.symlink_to("other")
    elif mutation == "ancestor-writable":
        root.chmod(0o777)
    elif mutation == "root-writable":
        tmp_path.chmod(0o777)
    reader = _gateway_token_reader()
    if mutation == "none":
        assert reader("/credentials", token.name) == "a" * 64
    else:
        with pytest.raises((OSError, RuntimeError)):
            reader("/credentials", token.name)


def test_gateway_token_reader_rejects_wrong_owner_before_read(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace

    actual_fstat = os.fstat

    def wrong_owner(fd):
        value = actual_fstat(fd)
        return SimpleNamespace(st_uid=12345, st_mode=value.st_mode)

    monkeypatch.setattr(os, "fstat", wrong_owner)
    with pytest.raises(RuntimeError, match="gateway credential unavailable"):
        _gateway_token_reader()(str(tmp_path), "token")


@pytest.mark.parametrize("command", ["drill", "silence-create", "silence-delete"])
@pytest.mark.parametrize("owner", ["operator", "$(shell touch MON_UNSAFE_MARKER)"])
def test_make_gateway_commands_forward_owner_literally(operator, owner, command):
    common = operator["common"]
    values = dict(zip(common[::2], common[1::2]))
    marker = operator["tmp"] / "MON_UNSAFE_MARKER"
    if owner != "operator":
        owner = "$(shell touch " + str(marker) + ")"
    assert not marker.exists()
    request = operator["tmp"] / "silence.json"
    request.write_text("{}")
    request.chmod(0o600)
    result = subprocess.run(
        [
            "make",
            "observability-" + command,
            f"OBSERVABILITY_INVENTORY={values['--inventory']}",
            f"OBSERVABILITY_HOST={values['--host']}",
            f"OBSERVABILITY_ENVIRONMENT={values['--environment']}",
            f"OBSERVABILITY_COMPONENT={values['--component']}",
            f"OBSERVABILITY_KNOWN_HOSTS={values['--known-hosts']}",
            f"OBSERVABILITY_SILENCE_OWNER={owner}",
            f"OBSERVABILITY_SILENCE_REQUEST={request}",
            "OBSERVABILITY_SILENCE_ID=12345678-1234-4234-8234-1234567890ab",
        ],
        cwd=ROOT,
        env=operator["env"],
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert not marker.exists()
    if owner == "operator":
        assert result.returncode == 0, result.stderr
        payload = _calls(operator)[1]["payload"]
        assert "silence-owner-operator-token" in payload
        assert "http://127.0.0.1:9093" not in payload
    else:
        assert result.returncode != 0
        assert "valid --silence-owner required" in result.stderr
        assert _calls(operator) == []


def test_gateway_client_never_redirects_authorization():
    source = SCRIPT.read_text()
    start = source.index("def _gateway_program")
    end = source.index("def _status_program", start)
    namespace = {}
    exec(compile(source[start:end], str(SCRIPT), "exec"), namespace)
    program = namespace["_gateway_program"]("operator")
    exec(
        compile(program[: program.index("gateway_token =")], "gateway-reader", "exec"),
        namespace,
    )
    handler = namespace["_NoGatewayRedirect"]()
    with pytest.raises(RuntimeError, match="gateway redirect rejected"):
        handler.redirect_request(
            None, None, 302, "redirect", {}, "https://untrusted.invalid/"
        )


@pytest.mark.parametrize("command", ["silence-create", "silence-delete"])
def test_silence_commands_require_confirmation_and_private_owner(operator, command):
    result = _run(operator, command)
    assert result.returncode == 2
    assert result.stderr == "observability-operator: --confirm required\n"
    assert _calls(operator) == []


@pytest.mark.parametrize("command", ["silence-create", "silence-delete"])
def test_silence_commands_use_exact_gateway_without_secrets_in_argv(operator, command):
    extra = ["--confirm", "--silence-owner", "operator"]
    if command == "silence-create":
        request = operator["tmp"] / "silence.json"
        request.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "reason": "planned-maintenance",
                    "starts_at": "2026-09-04T16:00:00Z",
                    "ends_at": "2026-09-04T17:00:00Z",
                    "matchers": {"environment": "staging", "node": "node-a"},
                }
            )
        )
        request.chmod(0o600)
        extra.extend(["--request", str(request)])
    else:
        extra.extend(["--silence-id", "12345678-1234-4234-8234-1234567890ab"])
    result = _run(operator, command, *extra)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["state"] == ("created" if command == "silence-create" else "deleted")
    assert report["silence_id"] == "12345678-1234-4234-8234-1234567890ab"
    calls = _calls(operator)
    assert [call["program"] for call in calls] == ["ssh", "ssh-payload"]
    assert "silence-owner-operator-token" in calls[1]["payload"]
    assert (
        "planned-maintenance"
        not in json.dumps(calls[0]) + result.stdout + result.stderr
    )


def test_silence_delete_rejects_non_uuid_before_transport(operator):
    result = _run(
        operator,
        "silence-delete",
        "--confirm",
        "--silence-owner",
        "operator",
        "--silence-id",
        "../other",
    )
    assert result.returncode == 2
    assert result.stderr == "observability-operator: silence ID rejected\n"
    assert _calls(operator) == []


def test_silence_create_rejects_public_request_before_transport(operator):
    request = operator["tmp"] / "silence.json"
    request.write_text("{}")
    request.chmod(0o644)
    result = _run(
        operator,
        "silence-create",
        "--confirm",
        "--silence-owner",
        "operator",
        "--request",
        str(request),
    )
    assert result.returncode == 2
    assert result.stderr == "observability-operator: private silence request required\n"
    assert _calls(operator) == []


@pytest.mark.parametrize("deleting", [False, True])
@pytest.mark.parametrize("mutation", ["none", "bad-id", "extra", "oversize"])
def test_silence_remote_program_validates_response_without_echoing_request(
    deleting, mutation, capsys
):
    identifier = "12345678-1234-4234-8234-1234567890ab"
    payload = {"silence_id": identifier}
    if deleting:
        payload["deleted"] = True
    if mutation == "bad-id":
        payload["silence_id"] = "unsafe"
    elif mutation == "extra":
        payload["unexpected"] = "private-evidence"
    elif mutation == "oversize":
        payload["unexpected"] = "x" * 4096
    calls = []

    def gateway_request(path, data, method):
        calls.append((path, data, method))
        return _DrillResponse(200 if deleting else 201, payload)

    source = SCRIPT.read_text()
    start = source.index("def _silence_program")
    end = source.index("def _silence_request", start)
    namespace = {"_gateway_program": lambda owner: ""}
    exec(compile(source[start:end], str(SCRIPT), "exec"), namespace)
    request = b'{"reason":"planned-maintenance"}'
    program = namespace["_silence_program"](
        "operator",
        request=None if deleting else request,
        silence_id=identifier if deleting else None,
    )
    if mutation != "none":
        with pytest.raises((RuntimeError, ValueError)):
            exec(
                compile(program, "silence-program", "exec"),
                {"gateway_request": gateway_request},
            )
        assert capsys.readouterr().out == ""
    else:
        exec(
            compile(program, "silence-program", "exec"),
            {"gateway_request": gateway_request},
        )
        report = json.loads(capsys.readouterr().out)
        assert report == {
            "schema_version": 1,
            "component": "control-plane",
            "state": "deleted" if deleting else "created",
            "silence_id": identifier,
        }
    assert calls == [
        (
            "/v1/silences/" + identifier if deleting else "/v1/silences",
            None if deleting else request,
            "DELETE" if deleting else "POST",
        )
    ]
