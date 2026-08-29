"""The post-deploy gate proves one effective SSH listener owner."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify-ssh-listeners.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_ssh_listeners", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unit_output(
    load: str,
    active: str,
    listen: str | None = None,
    *,
    triggers: str | None = None,
    accept: str | None = None,
) -> str:
    lines = [f"LoadState={load}", f"ActiveState={active}"]
    if listen is not None:
        if triggers is None:
            triggers = "" if load == "not-found" else "ssh.service"
        if accept is None:
            accept = "" if load == "not-found" else "no"
        lines.extend((f"Listen={listen}", f"Triggers={triggers}", f"Accept={accept}"))
    return "\n".join(lines) + "\n"


def query_fixture(service: str, socket: str):
    calls: list[tuple[str, ...]] = []

    def query(command: tuple[str, ...]) -> str:
        calls.append(command)
        if "ssh.service" in command:
            return service
        if "ssh.socket" in command:
            return socket
        raise AssertionError(f"unexpected command: {command!r}")

    return query, calls


@pytest.mark.parametrize(
    ("expected_port", "service", "socket"),
    [
        (
            22,
            unit_output("loaded", "active"),
            unit_output("not-found", "inactive", ""),
        ),
        (
            22,
            unit_output("loaded", "active"),
            unit_output("not-found", "inactive"),
        ),
        (
            22,
            unit_output("loaded", "inactive"),
            unit_output("loaded", "active", "[::]:22 (Stream)"),
        ),
        (
            2222,
            unit_output("loaded", "active"),
            unit_output(
                "loaded",
                "inactive",
                "[::]:22 (Stream)",
                triggers="alternate.service",
                accept="yes",
            ),
        ),
        (
            2222,
            unit_output("loaded", "inactive"),
            unit_output(
                "loaded",
                "active",
                "[::]:2222 (Stream) 0.0.0.0:2222 (Stream)",
            ),
        ),
    ],
)
def test_single_effective_listener_passes(expected_port, service, socket):
    module = load_module()
    query, calls = query_fixture(service, socket)
    module.verify(expected_port, run=query)
    assert calls == [
        (
            "/usr/bin/systemctl",
            "show",
            "ssh.service",
            "--all",
            "--property=LoadState",
            "--property=ActiveState",
        ),
        (
            "/usr/bin/systemctl",
            "show",
            "ssh.socket",
            "--all",
            "--property=LoadState",
            "--property=ActiveState",
            "--property=Listen",
            "--property=Triggers",
            "--property=Accept",
        ),
    ]


@pytest.mark.parametrize(
    ("expected_port", "service", "socket", "message"),
    [
        (
            2222,
            unit_output("loaded", "active"),
            unit_output("loaded", "active", "[::]:22 (Stream)"),
            "expected tcp/2222 only; service=active socket=active "
            "effective=[tcp/22,tcp/2222]",
        ),
        (
            22,
            unit_output("loaded", "inactive"),
            unit_output("loaded", "active", "[::]:22 (Stream) [::]:2222 (Stream)"),
            "expected tcp/22 only; service=inactive socket=active "
            "effective=[tcp/22,tcp/2222]",
        ),
        (
            22,
            unit_output("loaded", "inactive"),
            unit_output("loaded", "inactive", ""),
            "expected tcp/22 only; service=inactive socket=inactive effective=[]",
        ),
    ],
)
def test_ambiguous_or_absent_effective_listener_fails(
    expected_port, service, socket, message
):
    module = load_module()
    query, _ = query_fixture(service, socket)
    with pytest.raises(module.VerificationError, match=f"^{re.escape(message)}$"):
        module.verify(expected_port, run=query)


@pytest.mark.parametrize(
    "listen",
    [
        "0.0.0.0:22 (Datagram)",
        "/run/ssh.sock (Stream)",
        "not-an-endpoint (Stream)",
        "[::]:0 (Stream)",
        "[::]:65536 (Stream)",
        "0.0.0.0:22 (Stream) 0.0.0.0:22 (Stream)",
        "[::]:22 (Stream) malformed",
        "",
    ],
)
def test_active_socket_without_a_unique_valid_stream_listener_fails(listen):
    module = load_module()
    query, _ = query_fixture(
        unit_output("loaded", "inactive"),
        unit_output("loaded", "active", listen),
    )
    with pytest.raises(
        module.VerificationError,
        match="^active ssh.socket has no valid Stream listener$",
    ):
        module.verify(22, run=query)


def test_repeated_listen_properties_cover_ipv4_and_ipv6_on_one_port():
    module = load_module()
    socket = (
        "LoadState=loaded\n"
        "ActiveState=active\n"
        "Listen=[::]:2222 (Stream)\n"
        "Listen=0.0.0.0:2222 (Stream)\n"
        "Triggers=ssh.service\n"
        "Accept=no\n"
    )
    query, _ = query_fixture(unit_output("loaded", "inactive"), socket)
    module.verify(2222, run=query)


@pytest.mark.parametrize(
    ("socket", "message"),
    [
        (
            "LoadState=loaded\n"
            "ActiveState=active\n"
            "Listen=[::]:22 (Stream)\n"
            "Listen=[::]:22 (Stream)\n"
            "Triggers=ssh.service\n"
            "Accept=no\n",
            "active ssh.socket has no valid Stream listener",
        ),
        (
            "LoadState=loaded\n"
            "ActiveState=active\n"
            "Listen=[::]:22 (Stream)\n"
            "Listen=0.0.0.0:2222 (Stream)\n"
            "Triggers=ssh.service\n"
            "Accept=no\n",
            "expected tcp/22 only; service=inactive socket=active "
            "effective=[tcp/22,tcp/2222]",
        ),
    ],
)
def test_repeated_listen_properties_reject_duplicate_or_multi_port(socket, message):
    module = load_module()
    query, _ = query_fixture(unit_output("loaded", "inactive"), socket)
    with pytest.raises(
        module.VerificationError,
        match=f"^{re.escape(message)}$",
    ):
        module.verify(22, run=query)


@pytest.mark.parametrize(
    ("unit", "output", "message"),
    [
        ("service", unit_output("not-found", "inactive"), "invalid ssh.service state"),
        ("service", unit_output("loaded", "failed"), "invalid ssh.service state"),
        ("service", "LoadState=loaded\n", "invalid ssh.service state"),
        (
            "service",
            "LoadState=loaded\nLoadState=loaded\nActiveState=active\n",
            "invalid ssh.service state",
        ),
        (
            "socket",
            unit_output("loaded", "failed", ""),
            "invalid ssh.socket state",
        ),
        (
            "socket",
            "LoadState=loaded\nActiveState=inactive\nUnknown=value\nListen=\n"
            "Triggers=ssh.service\nAccept=no\n",
            "invalid ssh.socket state",
        ),
        (
            "socket",
            "LoadState=not-found\nActiveState=active\nListen=[::]:22 (Stream)\n"
            "Triggers=ssh.service\nAccept=no\n",
            "invalid ssh.socket state",
        ),
        (
            "socket",
            "LoadState=loaded\nActiveState=active\nListen=[::]:22 (Stream)\n"
            "Triggers=ssh.service\n",
            "invalid ssh.socket state",
        ),
    ],
)
def test_unknown_missing_or_duplicate_unit_state_fails(unit, output, message):
    module = load_module()
    service = output if unit == "service" else unit_output("loaded", "active")
    socket = output if unit == "socket" else unit_output("not-found", "inactive", "")
    query, _ = query_fixture(service, socket)
    with pytest.raises(module.VerificationError, match=f"^{message}$"):
        module.verify(22, run=query)


@pytest.mark.parametrize(
    ("triggers", "accept"),
    [("alternate.service", "no"), ("ssh.service", "yes"), ("", "no")],
)
def test_active_socket_must_activate_one_non_accepting_ssh_service(triggers, accept):
    module = load_module()
    query, _ = query_fixture(
        unit_output("loaded", "inactive"),
        unit_output(
            "loaded",
            "active",
            "[::]:22 (Stream)",
            triggers=triggers,
            accept=accept,
        ),
    )
    with pytest.raises(module.VerificationError, match="^invalid ssh.socket state$"):
        module.verify(22, run=query)


@pytest.mark.parametrize(
    "command",
    [
        (sys.executable, "-c", "import sys; sys.exit(7)"),
        (sys.executable, "-c", "print('x' * 4097)"),
        (sys.executable, "-c", "import time; time.sleep(1)"),
    ],
)
def test_systemctl_query_failures_are_categorical(command):
    module = load_module()
    timeout = 0.01 if "sleep" in command[-1] else module.SYSTEMCTL_TIMEOUT_SECONDS
    with pytest.raises(module.VerificationError, match="^systemctl-query-failed$"):
        module.run_bounded(command, timeout=timeout)


def test_bounded_query_kills_descendants_that_inherit_stdout(tmp_path):
    module = load_module()
    child_pid = tmp_path / "child.pid"
    survived = tmp_path / "child-survived"
    child_code = (
        "import pathlib,time; "
        "time.sleep(0.5); "
        f"pathlib.Path({str(survived)!r}).write_text('unsafe')"
    )
    parent_code = (
        "import pathlib,subprocess,sys,time; "
        f"child=subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
        f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid)); "
        "print('LoadState=loaded', flush=True); time.sleep(30)"
    )
    with pytest.raises(module.VerificationError, match="^systemctl-query-failed$"):
        module.run_bounded((sys.executable, "-c", parent_code), timeout=0.1)
    assert child_pid.exists()
    pid = int(child_pid.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("query descendant remained alive after the bounded failure")
    time.sleep(0.55)
    assert not survived.exists()


def test_cli_rejects_invalid_expected_port_without_querying(monkeypatch, capsys):
    module = load_module()
    monkeypatch.setattr(
        module,
        "run_bounded",
        lambda *_args, **_kwargs: pytest.fail("systemctl must not run"),
    )
    assert module.main(["--sshd-port", "0"]) == 2
    assert capsys.readouterr().err.strip() == "verification error: invalid sshd port"


def test_cli_does_not_print_systemctl_diagnostics(monkeypatch, capsys):
    module = load_module()

    def refuse(_port):
        raise module.VerificationError("systemctl-query-failed")

    monkeypatch.setattr(module, "verify", refuse)
    assert module.main(["--sshd-port", "22"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "verification error: systemctl-query-failed"


def test_verify_playbook_uses_effective_port_and_helper_without_process_grep():
    play = yaml.safe_load((ROOT / "ansible/playbooks/verify.yml").read_text())[0]
    tasks = play["tasks"]
    sshd = [task for task in tasks if task.get("ansible.builtin.command", {}).get("cmd") == "sshd -T"]
    assert len(sshd) == 1
    assert sshd[0]["check_mode"] is False
    assertion = next(task for task in tasks if task["name"] == "SSH listener port is unambiguous")
    conditions = assertion["ansible.builtin.assert"]["that"]
    assert "verify_effective_ssh_ports | length == 1" in conditions
    assert any("ansible_port | default(22)" in condition for condition in conditions)
    helper = next(
        task for task in tasks
        if "verify-ssh-listeners.py" in task.get("ansible.builtin.script", {}).get("cmd", "")
    )
    assert helper["changed_when"] is False
    assert helper["check_mode"] is False
    assert helper["ansible.builtin.script"]["executable"] == "python3"
    assert "{{ playbook_dir }}/../../scripts/verify-ssh-listeners.py" in helper["ansible.builtin.script"]["cmd"]
    assert "--sshd-port {{ verify_effective_ssh_ports[0] }}" in helper["ansible.builtin.script"]["cmd"]
    source = SCRIPT.read_text()
    for forbidden in ("/proc", "pgrep", "ps aux", "ss -l", "netstat"):
        assert forbidden not in source


def test_verify_producer_and_consumer_execute_in_ansible_check_mode(tmp_path):
    executable = shutil.which("ansible-playbook")
    assert executable, "real Ansible is required for check-mode regression coverage"
    play = yaml.safe_load((ROOT / "ansible/playbooks/verify.yml").read_text())[0]
    names = {
        "SSH password auth disabled",
        "Select effective SSH listener port",
        "SSH listener port is unambiguous",
        "Exactly one effective SSH listener exists",
    }
    tasks = [task for task in play["tasks"] if task["name"] in names]
    assert [task["name"] for task in tasks] == [
        "SSH password auth disabled",
        "Select effective SSH listener port",
        "SSH listener port is unambiguous",
        "Exactly one effective SSH listener exists",
    ]
    helper = tasks[-1]["ansible.builtin.script"]
    helper["cmd"] = (
        f"{SCRIPT} --sshd-port {{{{ verify_effective_ssh_ports[0] }}}}"
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sshd_trace = tmp_path / "sshd-called"
    helper_trace = tmp_path / "helper-called"
    (fake_bin / "sshd").write_text(
        f"#!/bin/sh\ntouch {shlex_quote(str(sshd_trace))}\nprintf 'port 2222\\n'\n"
    )
    (fake_bin / "python3").write_text(
        f"#!/bin/sh\ntouch {shlex_quote(str(helper_trace))}\nexit 0\n"
    )
    for path in (fake_bin / "sshd", fake_bin / "python3"):
        path.chmod(0o755)
    playbook = tmp_path / "verify-check.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "Exercise SSH listener verification in check mode",
                    "hosts": "localhost",
                    "gather_facts": False,
                    "become": False,
                    "vars": {
                        "ansible_port": 2222,
                        "ansible_python_interpreter": sys.executable,
                    },
                    "environment": {"PATH": f"{fake_bin}:{os.environ['PATH']}"},
                    "tasks": tasks,
                }
            ],
            sort_keys=False,
        )
    )
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
    env.update(ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local"))
    result = subprocess.run(
        [executable, "-i", "localhost,", "-c", "local", "--check", str(playbook)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert sshd_trace.exists(), result.stdout + result.stderr
    assert helper_trace.exists(), result.stdout + result.stderr


def test_real_ansible_script_transfers_controller_source_to_remote_tmp(tmp_path):
    executable = shutil.which("ansible-playbook")
    assert executable, "real Ansible is required for script-transfer regression coverage"
    controller = tmp_path / "controller"
    controller.mkdir()
    source = controller / "verify.py"
    trace = tmp_path / "executed-path"
    source.write_text(
        "import os, pathlib\n"
        "pathlib.Path(os.environ['TRANSFER_TRACE']).write_text(\n"
        "    str(pathlib.Path(__file__).resolve())\n"
        ")\n"
    )
    source.chmod(0o755)
    remote_tmp = tmp_path / "managed" / "ansible-tmp"
    playbook = controller / "transfer.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "Exercise controller script transfer",
                    "hosts": "localhost",
                    "gather_facts": False,
                    "become": False,
                    "vars": {
                        "ansible_python_interpreter": sys.executable,
                        "ansible_remote_tmp": str(remote_tmp),
                    },
                    "tasks": [
                        {
                            "name": "Run controller-only script on managed target",
                            "ansible.builtin.script": {
                                "cmd": str(source),
                                "executable": sys.executable,
                            },
                            "environment": {"TRANSFER_TRACE": str(trace)},
                            "changed_when": False,
                        }
                    ],
                }
            ],
            sort_keys=False,
        )
    )
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
    env.update(ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local"))
    result = subprocess.run(
        [executable, "-i", "localhost,", "-c", "local", str(playbook)],
        cwd=controller,
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert trace.exists(), result.stdout + result.stderr
    executed = Path(trace.read_text())
    assert executed != source.resolve()
    assert executed.is_relative_to(remote_tmp)


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
