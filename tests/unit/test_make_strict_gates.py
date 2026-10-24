"""ci-fast and validate must not silently reduce their promised coverage."""

import importlib.util
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest


def _cloud_init_schema_module():
    path = (
        Path(__file__).resolve().parents[2] / "scripts/cloud-init-schema-container.py"
    )
    spec = importlib.util.spec_from_file_location("cloud_init_schema_container", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cloud_init_schema_stops_client_before_container_removal(tmp_path, monkeypatch):
    module = _cloud_init_schema_module()
    gate, marker = tmp_path / "create", tmp_path / "container"
    client_code = (
        "import pathlib,sys,time; gate,marker=map(pathlib.Path,sys.argv[1:]); "
        "deadline=time.monotonic()+5\n"
        "while not gate.exists():\n"
        " if time.monotonic()>deadline: raise SystemExit(2)\n"
        " time.sleep(.005)\n"
        "marker.write_text('late creation'); time.sleep(30)"
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            client_code,
            str(gate),
            str(marker),
        ],
    )

    def remove(argv, **kwargs):
        assert argv == ["docker", "rm", "--force", "--volumes", "owned-name"]
        marker.unlink(missing_ok=True)
        if process.poll() is None:
            gate.touch()
            deadline = time.monotonic() + 5
            while not marker.exists():
                assert time.monotonic() < deadline, "client did not create its marker"
                time.sleep(0.005)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(module.subprocess, "run", remove)
    try:
        assert module._stop_container("owned-name", process)
        assert process.returncode is not None
        assert not marker.exists(), "client created a container after removal"
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


@pytest.fixture
def schema_processes():
    processes = []

    def start(code, *arguments):
        process = subprocess.Popen(
            [sys.executable, "-c", code, *map(str, arguments)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(process)
        return process

    yield start
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        if process.stdin is not None:
            process.stdin.close()


def test_cloud_init_schema_input_retries_backpressure_and_preserves_short_writes(
    tmp_path, monkeypatch, schema_processes
):
    module = _cloud_init_schema_module()
    output = tmp_path / "received"
    process = schema_processes(
        "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())",
        output,
    )
    original_write = os.write
    writes = 0

    def short_write(fd, data):
        nonlocal writes
        assert not os.get_blocking(fd)
        writes += 1
        if writes % 3 == 1:
            raise BlockingIOError()
        return original_write(fd, data[:7])

    monkeypatch.setattr(module.os, "write", short_write)
    payload = bytes(range(256)) * 16 + b"final byte"
    module._feed_and_wait(process, payload, timeout=5)
    assert process.returncode == 0
    assert output.read_bytes() == payload
    assert writes > 3


def test_cloud_init_schema_blocked_input_has_a_deadline(tmp_path, schema_processes):
    module = _cloud_init_schema_module()
    ready = tmp_path / "ready"
    process = schema_processes(
        "import pathlib,sys,time; pathlib.Path(sys.argv[1]).touch(); time.sleep(30)",
        ready,
    )
    startup_deadline = time.monotonic() + 5
    while not ready.exists():
        assert time.monotonic() < startup_deadline
        time.sleep(0.005)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as error:
        module._feed_and_wait(process, b"x" * (2 * 1024 * 1024), timeout=0.1)
    assert error.value.timeout == 0.1
    assert time.monotonic() - started < 2
    assert process.stdin.closed
    assert process.poll() is None


def test_cloud_init_schema_child_may_close_input_early(schema_processes):
    module = _cloud_init_schema_module()
    process = schema_processes("raise SystemExit(7)")
    process.wait(timeout=5)
    module._feed_and_wait(process, b"ignored input", timeout=1)
    assert process.returncode == 7
    assert process.stdin.closed


def test_cloud_init_schema_child_wait_uses_the_remaining_input_deadline(
    tmp_path, monkeypatch, schema_processes
):
    module = _cloud_init_schema_module()
    ready, received = tmp_path / "ready", tmp_path / "received"
    process = schema_processes(
        "import pathlib,sys,time; pathlib.Path(sys.argv[1]).touch(); "
        "pathlib.Path(sys.argv[2]).write_bytes(sys.stdin.buffer.read()); time.sleep(30)",
        ready,
        received,
    )
    startup_deadline = time.monotonic() + 5
    while not ready.exists():
        assert time.monotonic() < startup_deadline
        time.sleep(0.005)
    original_write, original_wait = os.write, process.wait
    wait_budgets = []

    def delayed_write(fd, data):
        time.sleep(0.05)
        return original_write(fd, data)

    def bounded_wait(*, timeout):
        wait_budgets.append(timeout)
        return original_wait(timeout=timeout)

    monkeypatch.setattr(module.os, "write", delayed_write)
    monkeypatch.setattr(process, "wait", bounded_wait)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            module._feed_and_wait(process, b"exact input", timeout=0.2)
        assert received.read_bytes() == b"exact input"
        assert len(wait_budgets) == 1
        assert 0 < wait_budgets[0] < 0.16
    finally:
        monkeypatch.setattr(process, "wait", original_wait)


def test_cloud_init_schema_repeated_backpressure_keeps_the_deadline(
    monkeypatch, schema_processes
):
    module = _cloud_init_schema_module()
    process = schema_processes("import sys; sys.stdin.buffer.read()")
    attempts = 0

    def blocked_write(fd, data):
        nonlocal attempts
        assert not os.get_blocking(fd)
        attempts += 1
        raise BlockingIOError()

    monkeypatch.setattr(module.os, "write", blocked_write)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        module._feed_and_wait(process, b"pending", timeout=0.1)
    assert time.monotonic() - started < 2
    assert attempts > 1


def test_cloud_init_schema_unexpected_write_error_propagates(
    monkeypatch, schema_processes
):
    module = _cloud_init_schema_module()
    process = schema_processes("import sys; sys.stdin.buffer.read()")
    failure = OSError("synthetic write refusal")

    def refused_write(fd, data):
        raise failure

    monkeypatch.setattr(module.os, "write", refused_write)
    with pytest.raises(OSError) as error:
        module._feed_and_wait(process, b"pending", timeout=1)
    assert error.value is failure
    assert process.stdin.closed


@pytest.mark.parametrize(
    "inspect_result, expected",
    [
        ((1, b"No such container"), False),
        ((0, b"container exists"), False),
        ((1, b"daemon unavailable"), False),
        ("unavailable", False),
        ("timeout", False),
    ],
)
def test_cloud_init_schema_uncertain_removal_requires_confirmed_absence(
    monkeypatch, schema_processes, inspect_result, expected
):
    module = _cloud_init_schema_module()
    process = schema_processes("import time; time.sleep(30)")
    calls = []

    def docker(argv, **kwargs):
        assert process.returncode is not None
        calls.append((argv, kwargs["timeout"]))
        if argv[1] == "rm":
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        assert argv == ["docker", "container", "inspect", "owned-name"]
        if inspect_result == "unavailable":
            raise OSError("unavailable")
        if inspect_result == "timeout":
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return subprocess.CompletedProcess(
            argv, inspect_result[0], stderr=inspect_result[1]
        )

    monkeypatch.setattr(module.subprocess, "run", docker)
    assert module._stop_container("owned-name", process) is expected
    assert [timeout for _argv, timeout in calls] == [15, 10]


def test_cloud_init_schema_removal_still_runs_when_client_reap_is_uncertain(
    monkeypatch, schema_processes
):
    module = _cloud_init_schema_module()
    process = schema_processes("import time; time.sleep(30)")
    original_wait = process.wait
    calls = []

    def uncertain_wait(*, timeout):
        assert timeout == 5
        raise subprocess.TimeoutExpired(process.args, timeout)

    def remove(argv, **kwargs):
        calls.append(argv)
        assert kwargs["timeout"] == 15
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(process, "wait", uncertain_wait)
    monkeypatch.setattr(module.subprocess, "run", remove)
    try:
        assert not module._stop_container("owned-name", process)
        assert calls == [["docker", "rm", "--force", "--volumes", "owned-name"]]
    finally:
        monkeypatch.setattr(process, "wait", original_wait)
        process.wait(timeout=5)


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
        "vpnd-dependency-check",
        "vpnd-lint",
        "vpnd-package-check",
        "vpnd-parity-check",
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
    python = tools / "python3"
    python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    python.chmod(0o755)
    for name, source in (
        ("mktemp", shutil.which("mktemp")),
        ("rm", shutil.which("rm")),
    ):
        assert source is not None
        (tools / name).symlink_to(source)
    make = shutil.which("make")
    assert make is not None
    completed = subprocess.run(
        [make, "--no-print-directory", "cloud-init-schema", *make_arguments],
        check=False,
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


@pytest.fixture
def schema_docker(tmp_path, monkeypatch):
    tools = tmp_path / "bin"
    tools.mkdir()
    calls = tmp_path / "calls"
    marker = tmp_path / "container-running"
    docker = tools / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys, time\n"
        "calls = pathlib.Path(os.environ['FAKE_DOCKER_CALLS'])\n"
        "with calls.open('a') as stream: stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "marker = pathlib.Path(os.environ['FAKE_DOCKER_MARKER'])\n"
        "if sys.argv[1] == 'run':\n"
        "    marker.write_text('running')\n"
        "    time.sleep(30)\n"
        "elif sys.argv[1] == 'rm':\n"
        "    if os.environ.get('FAKE_DOCKER_UNCERTAIN') == '1': raise SystemExit(1)\n"
        "    marker.unlink(missing_ok=True)\n"
        "else:\n"
        "    if os.environ.get('FAKE_DOCKER_NO_SUCH') == '1':\n"
        "        print('No such container', file=sys.stderr); raise SystemExit(1)\n"
        "    print('synthetic daemon refusal', file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
    )
    docker.chmod(0o755)
    config = tmp_path / "cloud-config.yaml"
    config.write_text("#cloud-config\n")
    module = _cloud_init_schema_module()
    original_popen = subprocess.Popen
    processes = []

    def ready_client(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        deadline = time.monotonic() + 5
        while not marker.exists():
            assert process.poll() is None, "fake Docker exited before readiness"
            assert time.monotonic() < deadline, "fake Docker did not become ready"
            time.sleep(0.005)
        return process

    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_DOCKER_CALLS", str(calls))
    monkeypatch.setenv("FAKE_DOCKER_MARKER", str(marker))

    # Only the actual docker-run client waits for readiness, not cleanup commands.
    def popen(*args, **kwargs):
        if args[0][1] == "run":
            return ready_client(*args, **kwargs)
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    try:
        yield module, [
            "--image",
            "ubuntu:24.04@sha256:" + "a" * 64,
            "--config",
            str(config),
            "--timeout",
            "1",
        ], calls, marker, processes
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


def test_cloud_init_schema_timeout_removes_the_named_container(schema_docker, capsys):
    module, arguments, calls, marker, processes = schema_docker
    result = module.main(arguments)
    assert result == 124
    assert "timed out and was stopped" in capsys.readouterr().err
    assert not marker.exists()
    assert processes[0].returncode is not None
    recorded = [json.loads(line) for line in calls.read_text().splitlines()]
    assert recorded[0][:4] == ["run", "--rm", "-i", "--name"]
    container_name = recorded[0][4]
    assert container_name.startswith("vpn-cloud-init-schema-")
    assert recorded[1] == ["rm", "--force", "--volumes", container_name]


@pytest.mark.parametrize("phase", ["nonblocking", "selector", "write"])
@pytest.mark.parametrize("uncertain", [False, True])
def test_cloud_init_schema_io_failure_cleans_up_at_main_boundary(
    schema_docker, monkeypatch, capsys, phase, uncertain
):
    module, arguments, calls, marker, processes = schema_docker
    failure = OSError(f"synthetic {phase} failure")

    def fail(*args, **kwargs):
        raise failure

    if phase == "nonblocking":
        monkeypatch.setattr(module.os, "set_blocking", fail)
    elif phase == "selector":
        monkeypatch.setattr(module.selectors, "DefaultSelector", fail)
    else:
        monkeypatch.setattr(module.os, "write", fail)
    if uncertain:
        monkeypatch.setenv("FAKE_DOCKER_UNCERTAIN", "1")
        assert module.main(arguments) == 125
        diagnostic = capsys.readouterr().err
        assert str(failure) in diagnostic
        assert "cleanup is uncertain" in diagnostic
    else:
        with pytest.raises(OSError) as error:
            module.main(arguments)
        assert error.value is failure
    assert processes[0].returncode is not None
    assert processes[0].stdin.closed
    assert marker.exists() is uncertain
    recorded = [json.loads(line) for line in calls.read_text().splitlines()]
    name = recorded[0][4]
    assert recorded[1] == ["rm", "--force", "--volumes", name]
    if uncertain:
        assert recorded[2] == ["container", "inspect", name]


def test_cloud_init_schema_absence_after_failed_removal_is_uncertain(
    schema_docker, monkeypatch, capsys
):
    module, arguments, calls, _marker, processes = schema_docker
    monkeypatch.setenv("FAKE_DOCKER_UNCERTAIN", "1")
    monkeypatch.setenv("FAKE_DOCKER_NO_SUCH", "1")
    assert module.main(arguments) == 125
    assert "cleanup is uncertain" in capsys.readouterr().err
    assert processes[0].returncode is not None
    recorded = [json.loads(line) for line in calls.read_text().splitlines()]
    assert [call[0] for call in recorded] == ["run", "rm", "container"]
    assert recorded[2] == ["container", "inspect", recorded[0][4]]


def test_cloud_init_schema_signal_refusal_still_attempts_named_removal(
    schema_docker, monkeypatch, capsys
):
    module, arguments, calls, marker, processes = schema_docker
    original_popen = module.subprocess.Popen
    original_methods = []
    wait_budgets = []

    def refusing_client(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        if args[0][1] == "run":
            original_methods.append((process, process.kill, process.wait))
            original_wait = process.wait

            def refuse_signal():
                raise PermissionError("synthetic signal refusal")

            def bounded_wait(*, timeout):
                wait_budgets.append(timeout)
                return original_wait(timeout=timeout)

            monkeypatch.setattr(process, "kill", refuse_signal)
            monkeypatch.setattr(process, "wait", bounded_wait)
        return process

    def fail_setup(*args, **kwargs):
        raise OSError("synthetic setup refusal")

    monkeypatch.setattr(module.subprocess, "Popen", refusing_client)
    monkeypatch.setattr(module.os, "set_blocking", fail_setup)
    try:
        assert module.main(arguments) == 125
        assert "synthetic setup refusal" in capsys.readouterr().err
        assert wait_budgets == [5]
        assert processes[0].poll() is None
        assert processes[0].stdin.closed
        assert not marker.exists()
        recorded = [json.loads(line) for line in calls.read_text().splitlines()]
        assert recorded[1] == ["rm", "--force", "--volumes", recorded[0][4]]
    finally:
        for process, kill, wait in original_methods:
            monkeypatch.setattr(process, "kill", kill)
            monkeypatch.setattr(process, "wait", wait)


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
    bootstrap = (root / "scripts/issue-bootstrap.sh").read_text()
    assert 'sops_file="${SOPS_FILE:-' in bootstrap
    subscription = (root / "scripts/issue_sub_token.py").read_text()
    assert "Path(os.environ.get('SOPS_FILE') or" in subscription


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

    assert 'ANSIBLE_INVENTORY ?= $(ANSIBLE_DIR)/inventory/generated.ini' in makefile
    assert 'export ANSIBLE_INVENTORY' in makefile
    assert 'test -s "$(ANSIBLE_INVENTORY)"' in guard
    assert 'scripts/require-vpn-selection.py' in guard
    assert '--limit "$(ANSIBLE_LIMIT)"' in guard
    for target in (
        "verify",
        "security-verify",
        "xray-diagnostics",
    ):
        declaration = next(
            line for line in makefile.splitlines() if line.startswith(f"{target}:")
        )
        assert "require-inventory" in declaration
    for target in ("dry-run", "deploy"):
        assert f"{target}:\n\t@python3 scripts/deploy-controller.py {target}" in makefile


@pytest.mark.parametrize("custom_inventory", [False, True])
@pytest.mark.parametrize("empty_file", [False, True])
def test_inventory_guard_refuses_missing_or_empty_selected_file(tmp_path, custom_inventory, empty_file):
    root = Path(__file__).resolve().parents[2]
    ansible_dir = tmp_path / "ansible"
    generated = ansible_dir / "inventory/generated.ini"
    generated.parent.mkdir(parents=True)
    selected = tmp_path / "snapshot.ini" if custom_inventory else generated
    if custom_inventory:
        generated.write_text("[vpn]\nunused-default\n")
    if empty_file:
        selected.touch()
    marker = tmp_path / "inventory-reader-called"
    tool_dir = tmp_path / "bin"
    tool_dir.mkdir()
    reader = tool_dir / "ansible-inventory"
    reader.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 99\n')
    reader.chmod(0o755)
    env = {key: value for key, value in os.environ.items()
           if key not in {"MAKEFILES", "MAKEFLAGS", "GNUMAKEFLAGS", "MFLAGS", "ANSIBLE_INVENTORY"}}
    env["PATH"] = f"{tool_dir}:{env['PATH']}"
    result = subprocess.run(
        ["make", "--no-print-directory", "-f", str(root / "Makefile"),
         "require-inventory", f"ANSIBLE_DIR={ansible_dir}",
         *([f"ANSIBLE_INVENTORY={selected}"] if custom_inventory else [])],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode != 0
    assert "missing generated inventory" in result.stdout + result.stderr
    assert not marker.exists()


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
        "verify",
        "security-verify",
        "xray-diagnostics",
    ):
        declaration = next(
            line for line in makefile.splitlines() if line.startswith(f"{live_target}:")
        )
        assert "validate-ansible-extra-vars" in declaration
    controller = (root / "scripts/deploy-controller.py").read_text()
    assert '"scripts/validate-ansible-extra-vars.py"' in controller
    assert "exact_mode=0o600" in controller


def test_live_ansible_targets_forward_limit_and_extra_vars():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()

    for target_name, following in (
        ("verify", "security-verify:"),
        ("security-verify", "security-audit:"),
        ("xray-diagnostics", "awg-evidence-provision:"),
    ):
        target = makefile.split(f"{target_name}:", 1)[1].split(f"\n\n{following}", 1)[0]
        assert "ANSIBLE_LIMIT" in target
        assert "ANSIBLE_EXTRA_VARS_FILE" in target
    assert "deploy dry-run: export DEPLOY_LIMIT = $(ANSIBLE_LIMIT)" in makefile
    assert "deploy dry-run: export DEPLOY_EXTRA_VARS_FILE = $(ANSIBLE_EXTRA_VARS_FILE)" in makefile


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
                             'tf-policy-verify'], cwd=tmp_path, capture_output=True, text=True, timeout=10, check=False)
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
    ], cwd=tmp_path, capture_output=True, text=True, timeout=10, check=False)
    if accepted:
        assert result.returncode == 0, result.stderr
        assert marker.read_text().strip() == 'ENV=canary deploy'
    else:
        assert result.returncode == 2, result.stderr
        assert 'refusing deploy-canary' in result.stderr
        assert not marker.exists()
