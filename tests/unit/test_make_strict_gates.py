"""ci-fast and validate must not silently reduce their promised coverage."""

from pathlib import Path
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile

import pytest


def test_validate_checks_every_provider_and_ci_fast_has_no_tool_skips():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    ci = (root / ".github" / "workflows" / "ci.yml").read_text()
    for provider in ("upcloud", "hetzner", "vultr", "scaleway"):
        assert provider in makefile
    assert "skipped: ansible-playbook" not in makefile
    assert "skipped: cargo" not in makefile

    ci_fast = makefile.split("ci-fast:", 1)[1].split("\n\n# Union gate", 1)[0]
    for target in (
        "actionlint-check",
        "zizmor-check",
        "cloud-init-schema",
        "tf-test",
        "tf-policy-verify",
        "yamllint-check",
        "shellcheck",
        "vpnd-deny",
        "vpnd-msrv",
    ):
        assert f"$(MAKE) {target}" in ci_fast
    assert "python3 scripts/render-cloud-init-ci.py" in ci


def test_cloud_init_schema_has_a_pinned_container_fallback():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("cloud-init-schema:", 1)[1].split("\n\ntf-test:", 1)[0]

    assert "CLOUD_INIT_IMAGE ?= ubuntu:24.04@sha256:" in makefile
    assert "command -v cloud-init" in target
    assert "command -v docker" in target
    assert "scripts/cloud-init-schema-container.py" in target
    assert "missing: cloud-init (or docker fallback)" in target
    assert "set -eu" in target


def _run_cloud_init_schema_fallback(
    tmp_path: Path,
    docker_exit: int = 0,
    *,
    make_arguments: tuple[str, ...] = (),
    extra_env: dict[str, str] | None = None,
):
    root = Path(__file__).resolve().parents[2]
    tools = tmp_path / "bin"
    tools.mkdir()
    docker = tools / "docker"
    docker.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "capture = pathlib.Path(os.environ['FAKE_DOCKER_CAPTURE'])\n"
        "capture.write_bytes(sys.stdin.buffer.read())\n"
        "capture.with_suffix('.argv.json').write_text(json.dumps(sys.argv[1:]))\n"
        "raise SystemExit(int(os.environ.get('FAKE_DOCKER_EXIT', '0')))\n"
    )
    docker.chmod(0o755)
    capture = tmp_path / "docker-input.tar"
    for name, source in (
        ("python3", sys.executable),
        ("mktemp", shutil.which("mktemp")),
        ("rm", shutil.which("rm")),
    ):
        assert source is not None
        (tools / name).symlink_to(source)
    make = shutil.which("make")
    assert make is not None
    completed = subprocess.run(
        [make, "--no-print-directory", "cloud-init-schema", *make_arguments],
        cwd=root,
        env={
            **os.environ,
            "PATH": str(tools),
            "TMPDIR": str(tmp_path),
            "FAKE_DOCKER_CAPTURE": str(capture),
            "FAKE_DOCKER_EXIT": str(docker_exit),
            **(extra_env or {}),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    return root, completed, capture


def test_cloud_init_schema_container_receives_exact_yaml_and_strict_https(tmp_path):
    root, completed, capture = _run_cloud_init_schema_fallback(tmp_path)
    assert completed.returncode == 0, completed.stderr

    expected = subprocess.run(
        ["python3", "scripts/render-cloud-init-ci.py"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(capture.read_bytes()), mode="r:") as archive:
        assert archive.getnames() == ["ca.pem", "cloud-config.yaml"]
        ca_info = archive.getmember("ca.pem")
        config_info = archive.getmember("cloud-config.yaml")
        assert ca_info.isfile() and ca_info.mode == 0o600
        assert config_info.isfile() and config_info.mode == 0o600
        assert archive.extractfile(config_info).read() == expected
        assert b"BEGIN CERTIFICATE" in archive.extractfile(ca_info).read()

    argv = json.loads(capture.with_suffix(".argv.json").read_text())
    assert argv[:3] == ["run", "--rm", "-i"]
    assert argv[3] == "--name"
    assert argv[4].startswith("vpn-cloud-init-schema-")
    assert "--network=bridge" in argv
    assert any(arg.startswith("--tmpfs=/run/cloud-init-schema:") for arg in argv)
    command = argv[-1]
    assert "https://ports.ubuntu.com/ubuntu-ports/" in command
    assert "https://archive.ubuntu.com/ubuntu/" in command
    assert "https://security.ubuntu.com/ubuntu/" in command
    assert 'install -d -m 0755 "$ca_dir"' in command
    assert 'install -m 0644 "$work/ca.pem" "$ca"' in command
    assert "Acquire::https::CAInfo=/run/cloud-init-schema-public/ca.pem" in command
    assert "Acquire::https::Verify-Peer=true" in command
    assert "Acquire::https::Verify-Host=true" in command
    assert "APT::Update::Error-Mode=any" in command
    assert 'set -- "$@" "$source"' in command
    assert "grep -qE" in command
    assert "if test \"$status\" -ne 1" in command
    assert "trusted=yes" not in command
    assert "Verify-Peer=false" not in command
    assert "Verify-Host=false" not in command


def test_cloud_init_schema_propagates_container_failure(tmp_path):
    _root, completed, _capture = _run_cloud_init_schema_fallback(
        tmp_path, docker_exit=42
    )
    assert completed.returncode != 0


def test_cloud_init_schema_refuses_an_unpinned_container_image(tmp_path):
    _root, completed, capture = _run_cloud_init_schema_fallback(
        tmp_path, make_arguments=("CLOUD_INIT_IMAGE=ubuntu:24.04",)
    )
    assert completed.returncode != 0
    assert "requires a digest-pinned image" in completed.stderr
    assert not capture.exists()


def test_cloud_init_schema_refuses_a_missing_ca_bundle_before_docker(tmp_path):
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "certifi.py").write_text(
        "def where():\n    return '/definitely/missing/cloud-init-ca.pem'\n"
    )
    _root, completed, capture = _run_cloud_init_schema_fallback(
        tmp_path, extra_env={"PYTHONPATH": str(modules)}
    )
    assert completed.returncode != 0
    assert "refused its input" in completed.stderr
    assert not capture.exists()


def test_cloud_init_schema_reports_the_conditional_certifi_prerequisite(tmp_path):
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "certifi.py").write_text(
        "raise ModuleNotFoundError('synthetic missing certifi')\n"
    )
    _root, completed, capture = _run_cloud_init_schema_fallback(
        tmp_path, extra_env={"PYTHONPATH": str(modules)}
    )
    assert completed.returncode != 0
    assert "requires pinned certifi from requirements.txt" in completed.stderr
    assert not capture.exists()


def test_cloud_init_schema_timeout_removes_the_named_container(tmp_path):
    root = Path(__file__).resolve().parents[2]
    tools = tmp_path / "bin"
    tools.mkdir()
    calls = tmp_path / "calls"
    marker = tmp_path / "container-running"
    docker = tools / "docker"
    docker.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys, time\n"
        "calls = pathlib.Path(os.environ['FAKE_DOCKER_CALLS'])\n"
        "with calls.open('a') as stream: stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "marker = pathlib.Path(os.environ['FAKE_DOCKER_MARKER'])\n"
        "if sys.argv[1] == 'run':\n"
        "    marker.write_text('running')\n"
        "    time.sleep(30)\n"
        "elif sys.argv[1] == 'rm':\n"
        "    marker.unlink(missing_ok=True)\n"
        "else:\n"
        "    raise SystemExit(1)\n"
    )
    docker.chmod(0o755)
    config = tmp_path / "cloud-config.yaml"
    config.write_text("#cloud-config\n")
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/cloud-init-schema-container.py"),
            "--image",
            "ubuntu:24.04@sha256:" + "a" * 64,
            "--config",
            str(config),
            "--timeout",
            "1",
        ],
        env={
            **os.environ,
            "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
            "FAKE_DOCKER_CALLS": str(calls),
            "FAKE_DOCKER_MARKER": str(marker),
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 124
    assert "timed out and was stopped" in completed.stderr
    assert not marker.exists()
    recorded = [json.loads(line) for line in calls.read_text().splitlines()]
    assert recorded[0][:4] == ["run", "--rm", "-i", "--name"]
    container_name = recorded[0][4]
    assert container_name.startswith("vpn-cloud-init-schema-")
    assert recorded[1] == ["rm", "--force", "--volumes", container_name]


def test_inventory_uses_the_local_fleet_profile_when_present():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("inventory:", 1)[1].split("\n\nwait:", 1)[0]

    assert "-include .fleet.mk" in makefile
    assert 'HOSTS="$(HOSTS)"' in target
    assert 'COHORTS="$(COHORTS)"' in target


def test_client_emitters_receive_the_local_fleet_profile():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()

    for target in ("emit-singbox", "emit-bundle"):
        body = makefile.split(f"{target}:", 1)[1].split("\n\n", 1)[0]
        for variable in ("HOSTS", "COHORTS", "SOPS_FILE", "SOPS_FILES"):
            assert f'{variable}="$({variable})"' in body
        assert "\n\t@HOSTS=" in body

    awg = makefile.split("emit-awg:", 1)[1].split("\n\n", 1)[0]
    assert 'SOPS_FILE="$(SOPS_FILE)"' in awg
    assert "\n\t@SOPS_FILE=" in awg


def test_subscription_issuers_honor_the_explicit_sops_file():
    root = Path(__file__).resolve().parents[2]
    for script in ("issue-bootstrap.sh", "issue-sub-token.sh"):
        source = (root / "scripts" / script).read_text()
        assert 'sops_file="${SOPS_FILE:-' in source


def test_yamllint_excludes_git_ignored_local_state():
    root = Path(__file__).resolve().parents[2]
    config = (root / ".yamllint.yml").read_text()

    assert "  secrets/local/\n" in config
    assert "  state-backups/\n" in config


def test_check_prereqs_rejects_terraform_older_than_project_floor():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("check-prereqs:", 1)[1].split("\n\ninit:", 1)[0]

    assert "terraform version -json" in target
    assert "Terraform >= 1.15 required" in target


def test_live_ansible_targets_require_a_nonempty_generated_inventory():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    guard = makefile.split("require-inventory:", 1)[1].split(
        "\n\npre-deploy-check:", 1
    )[0]

    assert 'test -s "$(ANSIBLE_DIR)/inventory/generated.ini"' in guard
    assert 'document.get("vpn", {}).get("hosts", [])' in guard
    for target in (
        "dry-run",
        "deploy",
        "verify",
        "security-verify",
        "xray-diagnostics",
    ):
        declaration = next(
            line for line in makefile.splitlines() if line.startswith(f"{target}:")
        )
        assert "require-inventory" in declaration


def test_xray_diagnostics_rejects_unsafe_extra_vars_files():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("validate-ansible-extra-vars:", 1)[1].split(
        "\n\npre-deploy-check", 1
    )[0]

    assert "follow_symlinks=False" in target
    assert "s.st_uid == os.geteuid()" in target
    assert "stat.S_IMODE(s.st_mode) == 0o600" in target

    for live_target in (
        "dry-run",
        "deploy",
        "verify",
        "security-verify",
        "xray-diagnostics",
    ):
        declaration = next(
            line for line in makefile.splitlines() if line.startswith(f"{live_target}:")
        )
        assert "validate-ansible-extra-vars" in declaration


def test_live_ansible_targets_forward_limit_and_extra_vars():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()

    for target_name, following in (
        ("dry-run", "deploy:"),
        ("deploy", "deploy-canary:"),
        ("verify", "security-verify:"),
        ("security-verify", "security-audit:"),
        ("xray-diagnostics", "awg-evidence-provision:"),
    ):
        target = makefile.split(f"{target_name}:", 1)[1].split(f"\n\n{following}", 1)[0]
        assert "ANSIBLE_LIMIT" in target
        assert "ANSIBLE_EXTRA_VARS_FILE" in target


def test_partial_verify_cannot_create_a_fleet_known_good_tag():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("verify:", 1)[1].split("\n\nsecurity-verify:", 1)[0]

    assert '"$(TAG_ON_SUCCESS)" = "1"' in target
    assert '"$(ANSIBLE_LIMIT)"' in target
    assert "requires an unbounded fleet verification" in target


@pytest.mark.parametrize("shred_succeeds", [True, False])
def test_clean_removes_exact_secret_path_without_logging_it(tmp_path, shred_succeeds):
    root = Path(__file__).resolve().parents[2]
    secrets = tmp_path / "cache directory" / 'vpn-"quoted".secrets.yaml'
    secrets.parent.mkdir()
    secrets.write_text("synthetic test secret\n")
    tool_dir = tmp_path / "bin"
    tool_dir.mkdir()
    shred = tool_dir / "shred"
    shred.write_text("#!/bin/sh\n" + (
        'exec /bin/rm -- "$3"\n' if shred_succeeds else "exit 1\n"
    ))
    shred.chmod(0o755)
    result = subprocess.run(
        ["make", "--no-print-directory", "-f", str(root / "Makefile"),
         "clean", f"SECRETS_FILE={secrets}"],
        cwd=tmp_path, env={**os.environ, "PATH": f"{tool_dir}:{os.environ['PATH']}"},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not secrets.exists()
    assert str(secrets) not in result.stdout + result.stderr


def test_clean_reports_failure_when_secret_cannot_be_removed(tmp_path):
    root = Path(__file__).resolve().parents[2]
    secrets = tmp_path / "vpn-test.secrets.yaml"
    secrets.write_text("synthetic test secret\n")
    tool_dir = tmp_path / "bin"
    tool_dir.mkdir()
    for name in ("shred", "rm"):
        tool = tool_dir / name
        tool.write_text("#!/bin/sh\nexit 1\n")
        tool.chmod(0o755)
    result = subprocess.run(
        ["make", "--no-print-directory", "-f", str(root / "Makefile"),
         "clean", f"SECRETS_FILE={secrets}"],
        cwd=tmp_path, env={**os.environ, "PATH": f"{tool_dir}:{os.environ['PATH']}"},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert secrets.exists()
    assert "shredded" not in result.stdout
    assert "failed to remove decrypted secrets" in result.stderr
    assert str(secrets) not in result.stdout + result.stderr


def test_local_policy_gate_propagates_a_real_policy_failure(tmp_path):
    root = Path(__file__).resolve().parents[2]
    policy = tmp_path / 'terraform/policy'
    policy.mkdir(parents=True)
    (policy / 'failing_test.rego').write_text('package regression\ntest_deliberate_failure { false }\n')
    result = subprocess.run(['make', '--no-print-directory', '-f', str(root / 'Makefile'),
                             'tf-policy-verify'], cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert '1 failure' in result.stdout + result.stderr


@pytest.mark.parametrize('secrets_file,sops_file,accepted', [
    ('/tmp/vpn-prod.secrets.yaml', '/tmp/canary.secrets.sops.yaml', False),
    ('/tmp/vpn-canary.secrets.yaml', '/tmp/prod.secrets.sops.yaml', False),
    ('/tmp/canary/vpn-prod.secrets.yaml', '/tmp/canary.secrets.sops.yaml', False),
    ('/tmp/vpn-canary.secrets.yaml', '/tmp/canary.secrets.sops.yaml', True),
])
def test_canary_scope_guard_precedes_recursive_deploy(tmp_path, secrets_file, sops_file, accepted):
    root = Path(__file__).resolve().parents[2]
    marker = tmp_path / 'deploy-called'
    child_make = tmp_path / 'child-make'
    child_make.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" > {marker}\n')
    child_make.chmod(0o755)
    result = subprocess.run([
        'make', '--no-print-directory', '-f', str(root / 'Makefile'), 'deploy-canary',
        f'MAKE={child_make}', f'SECRETS_FILE={secrets_file}', f'SOPS_FILE={sops_file}',
    ], cwd=tmp_path, capture_output=True, text=True, timeout=10)
    if accepted:
        assert result.returncode == 0, result.stderr
        assert marker.read_text().strip() == 'ENV=canary deploy'
    else:
        assert result.returncode == 2, result.stderr
        assert 'refusing deploy-canary' in result.stderr
        assert not marker.exists()
