"""Execute the rescue collector with portable CLI faults; no native readiness credit."""
import copy
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTIVATE = ROOT / "ansible/roles/transport-egress/tasks/activate.yml"
INVOCATION = "0123456789abcdef0123456789abcdef"
MARKER = "synthetic-private-diagnostic-marker"


def rescue_tasks():
    return next(task for task in yaml.safe_load(ACTIVATE.read_text())
                if task["name"] == "Activate only a ready guarded generation after frontend staging")["rescue"]


def diagnostic_tasks():
    return rescue_tasks()[0]["block"]


def collector_code(tmp_path, *, messages=None, fields=None, show_delay=0, journal_delay=0, fault=None):
    if fields is None:
        fields = {
            "ActiveState": "active", "SubState": "running", "Result": "success",
            "MainPID": "123", "ExecMainStatus": "0", "InvocationID": INVOCATION,
        }
    if messages is None:
        messages = [{"_SYSTEMD_INVOCATION_ID": INVOCATION,
                     "MESSAGE": "transport-generation-recovering:generation-command-failed-systemctl-start-xray"}]
    show, journal = tmp_path / "show.py", tmp_path / "journal.py"
    events = tmp_path / "events"
    for path, delay, output, command in (
        (show, show_delay, "\n".join(key + "=" + value for key, value in fields.items()), "show"),
        (journal, journal_delay, "\n".join(json.dumps(item) for item in messages), "journal"),
    ):
        source = (
            "import pathlib,sys,time\n"
            f"with pathlib.Path({str(events)!r}).open('a') as stream:stream.write({command!r}+'\\n')\n"
            f"time.sleep({delay!r})\n"
            f"print({output!r})\n"
        )
        if command == "journal":
            source += (
                f"assert '_SYSTEMD_INVOCATION_ID={INVOCATION}' in sys.argv\n"
                "assert '--lines=20' in sys.argv\n"
            )
        if fault == command:
            source += f"print({MARKER!r},file=sys.stderr);raise SystemExit(1)\n"
        path.write_text(source)
        path.chmod(0o600)
    # Substitute only the two platform CLI paths, preserving the actual collector.
    code = diagnostic_tasks()[0]["ansible.builtin.command"]["argv"][-1]
    code = code.replace("'/usr/bin/systemctl'", repr(sys.executable) + ", " + repr(str(show)))
    code = code.replace("'/usr/bin/journalctl'", repr(sys.executable) + ", " + repr(str(journal)))
    return code, events


def collect(tmp_path, *, stderr="transport-generation-refused:FileNotFoundError", **options):
    code, events = collector_code(tmp_path, **options)
    started = time.monotonic()
    result = subprocess.run([sys.executable, "-Es", "-c", code], input=stderr,
                            text=True, capture_output=True, timeout=5)
    elapsed = time.monotonic() - started
    assert result.returncode == 0, result.stderr
    assert MARKER not in result.stdout + result.stderr
    assert len(result.stdout.encode()) <= 2049
    assert result.stderr == ""
    return json.loads(result.stdout), elapsed, events.read_text().splitlines() if events.exists() else []


def test_rescue_diagnostic_precedes_unchanged_rollback_and_original_refusal():
    tasks = rescue_tasks()
    assert [task["name"] for task in tasks] == [
        "Record categorical generation failure without blocking rollback",
        "Restore the previous complete guarded route",
        "Report candidate activation failure after bounded recovery",
    ]
    collector, decode, publish = diagnostic_tasks()
    assert collector["no_log"] is True and collector["diff"] is False
    assert collector["changed_when"] is False and collector["failed_when"] is False
    argv = collector["ansible.builtin.command"]["argv"]
    assert argv[:6] == ["/usr/bin/timeout", "--signal=KILL", "5s", "/usr/bin/python3", "-Es", "-c"]
    assert collector["ansible.builtin.command"]["stdin"] == "{{ (_transport_egress_readiness.stderr | default(''))[:4096] }}"
    assert tasks[1]["ansible.builtin.include_tasks"] == "rollback.yml"
    assert tasks[2]["ansible.builtin.fail"]["msg"] == (
        "Guarded transport candidate failed readiness; accepted route recovery was attempted."
    )
    assert decode["no_log"] is True
    assert "{'diagnostic': 'unavailable'}" in decode["ansible.builtin.set_fact"]["_transport_egress_safe_failure_diagnostic"]
    assert publish["ansible.builtin.debug"]["msg"] == "{{ _transport_egress_safe_failure_diagnostic }}"
    assert tasks[0]["rescue"][0]["ansible.builtin.debug"]["msg"] == {"diagnostic": "unavailable"}


def test_current_invocation_category_and_whitelisted_metadata_are_reported(tmp_path):
    report, elapsed, events = collect(tmp_path)
    assert report == {
        "status_refusal": "FileNotFoundError",
        "controller_refusal": "generation-command-failed-systemctl-start-xray",
        "unit": {"active_state": "active", "sub_state": "running", "result": "success",
                 "has_main_pid": True, "exec_main_status": 0},
        "diagnostic": "available",
    }
    assert INVOCATION not in json.dumps(report)
    assert events == ["show", "journal"] and elapsed < 5


def test_unknown_private_messages_states_and_wrong_invocation_never_escape(tmp_path):
    fields = {key: MARKER for key in ("ActiveState", "SubState", "Result", "MainPID", "ExecMainStatus")}
    fields["InvocationID"] = INVOCATION
    messages = [
        {"_SYSTEMD_INVOCATION_ID": "f" * 32, "MESSAGE": "transport-generation-recovering:generation-process-identity"},
        {"_SYSTEMD_INVOCATION_ID": INVOCATION, "MESSAGE": "transport-generation-recovering:" + MARKER},
        {"_SYSTEMD_INVOCATION_ID": INVOCATION, "MESSAGE": MARKER},
    ]
    report, _, _ = collect(tmp_path, stderr="transport-generation-refused:" + MARKER,
                           fields=fields, messages=messages)
    assert report["status_refusal"] == report["controller_refusal"] == "unclassified"
    assert report["unit"] == {"active_state": "unclassified", "sub_state": "unclassified",
                             "result": "unclassified", "has_main_pid": False, "exec_main_status": None}


@pytest.mark.parametrize("kind", ["show", "journal", "oversized-input", "oversized-output", "too-many-records", "invalid-invocation"])
def test_failed_or_oversized_evidence_is_fixed_unavailable(tmp_path, kind):
    options = {}
    if kind in ("show", "journal"):
        options["fault"] = kind
    elif kind == "oversized-input":
        options["stderr"] = MARKER * 2000
    elif kind == "oversized-output":
        options["messages"] = [{"MESSAGE": MARKER * 4000}]
    elif kind == "too-many-records":
        options["messages"] = [{}] * 21
    else:
        options["fields"] = {"InvocationID": MARKER}
    report, _, events = collect(tmp_path, **options)
    assert report["diagnostic"] == "unavailable"
    assert report["controller_refusal"] == "unclassified"
    if kind in ("oversized-input", "invalid-invocation"):
        assert "journal" not in events


def test_show_and_journal_share_one_deadline(tmp_path):
    report, elapsed, events = collect(tmp_path, show_delay=2.3, journal_delay=2.3)
    assert report["diagnostic"] == "unavailable"
    assert events == ["show", "journal"]
    assert 3.5 <= elapsed < 5


def test_finite_journal_attribution_stage_is_retained(tmp_path):
    stage = "generation-readiness-journal-message-1-uid-0-process-1-timeout"
    report, _, _ = collect(tmp_path, messages=[{
        "_SYSTEMD_INVOCATION_ID": INVOCATION,
        "MESSAGE": "transport-generation-recovering:" + stage,
    }])
    assert report["controller_refusal"] == stage


@pytest.mark.parametrize("reason,expected", [
    ("generation-config-invalid", "generation-config-invalid"),
    (MARKER, "unclassified"),
])
def test_terminal_constructor_refusal_retains_only_known_category(tmp_path, reason, expected):
    report, _, _ = collect(tmp_path, messages=[{
        "_SYSTEMD_INVOCATION_ID": INVOCATION,
        "MESSAGE": "transport-generation-refused:" + reason,
    }])
    assert report["controller_refusal"] == expected
    assert report["diagnostic"] == "available"


@pytest.mark.parametrize("collector_fault", [None, "exit", "malformed"])
def test_actual_ansible_diagnostic_failure_cannot_prevent_rollback_or_original_refusal(tmp_path, collector_fault):
    executable = shutil.which("ansible-playbook")
    assert executable, "the genuine pinned Ansible toolchain is required"
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\ncallback_result_format=json\n")
    config.chmod(0o600)
    marker = tmp_path / "rollback-ran"
    rollback = tmp_path / "rollback.yml"
    rollback.write_text(yaml.safe_dump([{"name": "Record actual fixture rollback", "ansible.builtin.copy": {
        "content": "rollback completed\n", "dest": str(marker), "mode": "0600"}}]))
    rollback.chmod(0o600)
    tasks = copy.deepcopy(rescue_tasks())
    code, _ = collector_code(tmp_path, messages=[{
        "_SYSTEMD_INVOCATION_ID": INVOCATION,
        "MESSAGE": "transport-generation-recovering:" + MARKER,
    }])
    # Host reporting test substitutes only Linux executable paths; the actual
    # collector and rescue predicates remain intact, without native credit.
    if collector_fault == "exit":
        code = "raise SystemExit(124)"
    elif collector_fault == "malformed":
        code = f"print({MARKER!r})"
    tasks[0]["block"][0]["ansible.builtin.command"]["argv"] = [sys.executable, "-Es", "-c", code]
    tasks[1]["ansible.builtin.include_tasks"] = str(rollback)
    playbook = tmp_path / "diagnostic.yml"
    playbook.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "become": False, "gather_facts": False,
        "vars": {"_transport_egress_readiness": {"stderr": "transport-generation-refused:" + MARKER}},
        "tasks": [{"block": [{"name": "Preserve deliberate readiness failure", "ansible.builtin.fail": {
            "msg": "synthetic readiness failure"}}], "rescue": tasks}],
    }]))
    playbook.chmod(0o600)
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}
    environment.update({"ANSIBLE_CONFIG": str(config), "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
                        "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"), "ANSIBLE_NOCOLOR": "1",
                        "ANSIBLE_BECOME": "false", "ANSIBLE_STDOUT_CALLBACK": "default",
                        "ANSIBLE_PYTHON_INTERPRETER": sys.executable})
    result = subprocess.run([executable, "-i", "localhost,", str(playbook)], cwd=tmp_path,
                            env=environment, text=True, capture_output=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert MARKER not in output
    assert marker.read_text() == "rollback completed\n"
    assert tasks[2]["ansible.builtin.fail"]["msg"] in output
    assert '"diagnostic": "unavailable"' in output if collector_fault else '"diagnostic": "available"' in output
