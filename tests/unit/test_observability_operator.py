"""Bounded operator surface for the centralized observability roles."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

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
node-a ansible_host=fixture.invalid ansible_user=deploy ansible_port=22 ansible_ssh_private_key_file={key} env=staging observability_host_class=control-plane

[vpn-observability-control]
node-a
""".format(key=key),
        0o644,
    )
    secrets = _write(tmp_path / "secrets.yml", "observability_secrets: {{}}\n")
    variables = _write(
        tmp_path / "vars.yml",
        "observability_control_plane:\n  enabled: true\n",
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
    print('secret-path=' + os.environ.get('VPN_SECRETS_FILE', 'missing'))
    print('token=fixture-secret-value', file=sys.stderr)
with log.open('a') as stream:
    stream.write(json.dumps(entry) + '\\n')
if entry['program'] == 'ssh':
    payload = sys.stdin.read()
    entry = {{'program': 'ssh-payload', 'payload': payload}}
    with log.open('a') as stream:
        stream.write(json.dumps(entry) + '\\n')
    if 'LINKS =' in payload:
        print(json.dumps({{'schema_version': 1, 'component': 'control-plane', 'state': 'rolled-back'}}))
    elif '/api/v2/alerts' in payload:
        print(json.dumps({{'schema_version': 1, 'component': 'control-plane', 'state': 'submitted'}}))
    else:
        print(json.dumps({{'schema_version': 1, 'component': 'control-plane', 'state': 'healthy', 'units': {{'observability-prometheus.service': 'active', 'observability-alertmanager.service': 'active', 'observability-control-plane-adapter.timer': 'active'}}}}))
"""
    for name in ("ansible-playbook", "ssh"):
        _write(binary / name, recorder, 0o700)
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


def _calls(operator: dict[str, object]) -> list[dict[str, object]]:
    path = operator["log"]
    assert isinstance(path, Path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize("command", ["render", "validate", "rotate", "rollback"])
def test_secret_consuming_commands_fail_before_execution_without_private_secrets(
    operator: dict[str, object], command: str
) -> None:
    extra = ("--confirm",) if command == "rotate" else ()
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
    assert str(operator["secrets"]) not in result.stdout + result.stderr
    assert "fixture-secret-value" not in result.stdout + result.stderr


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
            "observability-prometheus.service": "active",
            "observability-alertmanager.service": "active",
            "observability-control-plane-adapter.timer": "active",
        },
    }
    observed = _calls(operator)
    assert [entry["program"] for entry in observed] == ["ssh", "ssh-payload"]
    payload = observed[1]["payload"]
    assert "journalctl" not in payload
    assert "Environment" not in payload
    assert "systemctl" in payload


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
    )
    assert result.returncode == 2
    assert result.stderr == "observability-operator: --confirm required\n"
    assert _calls(operator) == []

    result = _run(
        operator,
        "rollback",
        "--secrets",
        str(operator["secrets"]),
        "--vars",
        str(operator["vars"]),
        "--confirm",
    )
    assert result.returncode == 0, result.stderr
    call = _calls(operator)[0]
    assert call["program"] == "ansible-playbook"
    assert call["argv"][call["argv"].index("--limit") + 1] == "node-a"
    assert "observability_control_plane" in call["playbook"]
    assert "site.yml" not in " ".join(call["argv"])


def test_remove_converges_only_selected_role_with_enabled_false(
    operator: dict[str, object],
) -> None:
    result = _run(operator, "remove", "--confirm")

    assert result.returncode == 0, result.stderr
    call = _calls(operator)[0]
    assert call["argv"][call["argv"].index("--limit") + 1] == "node-a"
    assert "observability_control_plane" in call["playbook"]
    assert "enabled: false" in call["playbook"]
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
    assert result.stderr == "observability-operator: inventory scope rejected\n"
    assert _calls(operator) == []


def test_makefile_exposes_only_narrow_observability_controller_targets() -> None:
    source = (ROOT / "Makefile").read_text(encoding="utf-8")
    for command in (
        "render",
        "validate",
        "status",
        "drill",
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
