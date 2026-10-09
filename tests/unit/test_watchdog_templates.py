"""Rendered-artifact tests for authenticated watchdog REALITY probes."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from scripts.template_render import merge_render_vars, render_template

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "ansible" / "roles" / "watchdog" / "templates"


def _multi_cohort_vars() -> dict:
    vars_ = deepcopy(merge_render_vars())
    vars_["vpn_service_address"] = "192.0.2.50"
    vars_["watchdog_reality_probes"] = [
        {
            "name": "primary",
            "port": 443,
            "p0_reality_shape_input": {
                "flow_mode": "vision",
                "finalmask": False,
            },
            "clients": ["watchdog"],
        },
        {
            "name": "alternate",
            "port": 8443,
            "p0_reality_shape_input": {
                "flow_mode": "mux",
                "finalmask": True,
            },
            "clients": ["watchdog"],
        },
    ]
    return vars_


def test_probe_config_maps_every_cohort_to_a_distinct_socks_inbound():
    vars_ = _multi_cohort_vars()
    rendered = render_template(TEMPLATES / "reality-probe.json.j2", vars_)
    config = json.loads(rendered)

    assert [inbound["port"] for inbound in config["inbounds"]] == [31082, 31083]
    assert [
        outbound["settings"]["vnext"][0]["address"] for outbound in config["outbounds"]
    ] == ["192.0.2.50", "192.0.2.50"]
    assert [
        outbound["settings"]["vnext"][0]["port"] for outbound in config["outbounds"]
    ] == [443, 8443]
    assert (
        config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["flow"]
        == "xtls-rprx-vision"
    )
    assert "flow" not in config["outbounds"][1]["settings"]["vnext"][0]["users"][0]
    assert config["outbounds"][1]["mux"]["enabled"] is True
    assert config["outbounds"][1]["streamSettings"]["sockopt"]["finalmask"] == "Sudoku"


def test_probe_config_refuses_an_unknown_p0_shape() -> None:
    variables = _multi_cohort_vars()
    variables["watchdog_reality_probes"][0]["p0_reality_shape_input"][
        "flow_mode"
    ] = "unknown-shape"

    with pytest.raises(UndefinedError, match="unknown-shape"):
        render_template(TEMPLATES / "reality-probe.json.j2", variables)


def test_environment_lists_every_probe_without_client_credentials():
    vars_ = _multi_cohort_vars()
    rendered = render_template(TEMPLATES / "vpn-watchdog.env.j2", vars_)
    watchdog_client = next(
        client for client in vars_["xray"]["clients"] if client["name"] == "watchdog"
    )

    assert "XRAY_REALITY_PROBES=443:31082,8443:31083" in rendered
    assert watchdog_client["uuid"] not in rendered
    assert watchdog_client["short_id"] not in rendered
    assert "XRAY_API_SERVER=127.0.0.1:10086" in rendered
    assert "NTFY_" not in rendered
    assert "PUSHOVER_" not in rendered


def test_notification_authority_is_separate_and_the_unit_has_a_deadline():
    variables = _multi_cohort_vars()
    variables["watchdog_secrets"]["ntfy_topic"] = "synthetic-private-topic"
    variables["watchdog_secrets"]["ntfy_token"] = "synthetic-private-token"
    config = json.loads(
        render_template(TEMPLATES / "vpn-watchdog-notifications.json.j2", variables)
    )
    assert config["topic"] == "synthetic-private-topic"
    assert config["token"] == "synthetic-private-token"
    unit = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)
    assert (
        "LoadCredential=notifications.json:/etc/vpn-watchdog-notifications.json" in unit
    )
    assert "TimeoutStartSec=345s" in unit
    assert config["token"] not in unit and config["topic"] not in unit


def test_verify_uses_loaded_credentials_and_only_new_journal_evidence():
    import yaml

    play = yaml.safe_load((REPO_ROOT / "ansible/playbooks/verify.yml").read_text())[0]
    tasks = {task["name"]: task for task in play["tasks"]}
    capture = tasks["Capture the journal boundary before the credential-bearing probe"]
    run = tasks[
        "Run authenticated watchdog through its bounded credential-bearing unit"
    ]
    evidence = tasks[
        "Verify authenticated round trips from the new watchdog journal records"
    ]
    assert capture["no_log"] is True
    assert "--output=json" in capture["ansible.builtin.command"]["argv"]
    assert run["ansible.builtin.command"]["argv"] == [
        "systemctl",
        "start",
        "vpn-watchdog.service",
    ]
    assert any(
        arg.startswith("--after-cursor=")
        for arg in evidence["ansible.builtin.command"]["argv"]
    )
    assert "OK    xray REALITY" in evidence["failed_when"]
    cursor_argument = next(
        arg
        for arg in evidence["ansible.builtin.command"]["argv"]
        if arg.startswith("--after-cursor=")
    )
    from jinja2 import Environment

    environment = Environment()
    environment.filters["from_json"] = json.loads
    journal_record = {
        "__CURSOR": "s=actual-journal-boundary",
        "MESSAGE": "untrusted message\n-- cursor: s=old-boundary\nmore text",
    }
    assert (
        environment.from_string(cursor_argument).render(
            watchdog_journal_boundary={"stdout": json.dumps(journal_record)}
        )
        == "--after-cursor=s=actual-journal-boundary"
    )


def test_failure_fixture_provisions_xray_sandbox_path_before_canonical_unit():
    import shlex
    import yaml

    scenario = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/watchdog/molecule/failure/converge.yml").read_text()
    )[0]
    variables = _multi_cohort_vars()
    variables.update(scenario["vars"])
    unit = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)
    writable = shlex.split(
        next(
            line for line in unit.splitlines() if line.startswith("ReadWritePaths=")
        ).split("=", 1)[1]
    )
    log_directory = scenario["vars"]["xray_log_dir"]
    assert log_directory in writable
    provisioned = {
        task["ansible.builtin.file"]["path"]: task["ansible.builtin.file"]
        for task in scenario["pre_tasks"]
        if task.get("ansible.builtin.file", {}).get("state") == "directory"
    }
    assert log_directory in provisioned
    assert provisioned[log_directory]["owner"] == "root"
    assert provisioned[log_directory]["group"] == "xray"
    assert provisioned[log_directory]["mode"] == "0750"


def test_watchdog_fails_when_stats_service_is_not_queryable():
    rendered = render_template(TEMPLATES / "vpn-watchdog.sh.j2", _multi_cohort_vars())

    assert '"xray StatsService query"' in rendered
    assert 'api statsquery "--server=${XRAY_API_SERVER}"' in rendered


def test_watchdog_sandbox_allows_xray_config_validation_to_open_logs():
    variables = _multi_cohort_vars()
    variables["xray_log_dir"] = "/var/log/xray-custom"

    rendered = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)

    assert "ReadWritePaths=/var/lib/vpn-watchdog /var/log/xray-custom" in rendered


def test_watchdog_sandbox_keeps_xray_logs_read_only_when_xray_is_disabled():
    variables = _multi_cohort_vars()
    variables["vpn"]["enable_xray_reality"] = False

    rendered = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)

    assert "/var/log/xray" not in rendered


def test_watchdog_sandbox_allows_nginx_config_validation_to_open_logs():
    variables = _multi_cohort_vars()
    variables["vpn"]["enable_xray_reality"] = False
    variables["vpn"]["enable_nginx_xhttp"] = True

    rendered = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)

    assert "ReadWritePaths=/var/lib/vpn-watchdog /var/log/nginx" in rendered


def test_reality_probe_requires_the_explicit_service_address() -> None:
    variables = _multi_cohort_vars()
    variables.pop("vpn_service_address")

    with pytest.raises(UndefinedError, match="vpn_service_address"):
        render_template(TEMPLATES / "reality-probe.json.j2", variables)


@pytest.mark.parametrize("authority", [True, False])
def test_failure_sender_wrapper_preserves_delegate_inputs_and_result(
    tmp_path, authority
):
    import os
    import re
    import subprocess
    import sys
    import yaml

    scenario = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/watchdog/molecule/failure/converge.yml").read_text()
    )[0]
    copies = {
        task["ansible.builtin.copy"]["dest"]: task["ansible.builtin.copy"]["content"]
        for task in scenario["pre_tasks"]
        if "content" in task.get("ansible.builtin.copy", {})
    }
    dropin = copies["/etc/systemd/system/vpn-watchdog.service.d/diagnostics.conf"]
    assert "ExecStartPre" not in dropin
    assert (
        "Environment=WATCHDOG_NOTIFY_BIN=/usr/local/sbin/watchdog-notify-diagnostic.py"
        in dropin
    )
    source = copies["/usr/local/sbin/watchdog-notify-diagnostic.py"]
    captured = tmp_path / "delegated.json"
    delegate = tmp_path / "sender.py"
    delegate.write_text(
        "#!"
        + sys.executable
        + "\nimport json,os,sys\n"
        + "with open("
        + repr(str(captured))
        + ", 'w') as output:\n"
        + "    json.dump({'argv':sys.argv[1:], 'stdin':sys.stdin.read(), "
        + "'directory':os.environ['CREDENTIALS_DIRECTORY'], 'marker':os.environ['TEST_MARKER']}, output)\n"
        + "raise SystemExit(23)\n"
    )
    delegate.chmod(0o755)
    if authority:
        credential = tmp_path / "notifications.json"
        credential.write_text('{"token":"SYNTHETIC_PRIVATE_NOTIFICATION_AUTHORITY"}')
        credential.chmod(0o400)
    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(
        source.replace("/usr/local/libexec/vpn-watchdog-notify.py", str(delegate))
    )
    arguments = [
        "--title",
        "synthetic-title",
        "--tags",
        "warning,vpn",
        "--timeout",
        "10",
    ]
    result = subprocess.run(
        [sys.executable, str(wrapper), *arguments],
        input="SYNTHETIC_PRIVATE_BODY",
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CREDENTIALS_DIRECTORY": str(tmp_path),
            "TEST_MARKER": "SYNTHETIC_PRIVATE_ENVIRONMENT",
        },
        timeout=3,
    )
    assert result.returncode == 23 and not result.stderr
    assert json.loads(captured.read_text()) == {
        "argv": arguments,
        "stdin": "SYNTHETIC_PRIVATE_BODY",
        "directory": str(tmp_path),
        "marker": "SYNTHETIC_PRIVATE_ENVIRONMENT",
    }
    if authority:
        assert re.fullmatch(
            r"watchdog-credential-metadata mode=0o100400 uid=[0-9]+ gid=[0-9]+ nlink=1 size=[0-9]+ readonly=0\n",
            result.stdout,
        )
    else:
        assert result.stdout == "watchdog-credential-metadata error=stat-unavailable\n"
    assert "SYNTHETIC_PRIVATE" not in result.stdout
    assert str(tmp_path) not in result.stdout


def test_failure_journal_diagnostics_filter_private_messages_and_preserve_hard_failure(
    tmp_path,
):
    import os
    import re
    import subprocess
    import sys
    import yaml

    scenario = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/watchdog/molecule/failure/verify.yml").read_text()
    )[0]
    boundary = scenario["tasks"][0]
    invocation, capture = [task for task in boundary["block"] if "name" in task]
    assert invocation["failed_when"] == "watchdog_run.rc != 1"
    assert capture["ansible.builtin.wait_for"]["timeout"] == 10
    assert re.fullmatch(capture["ansible.builtin.wait_for"]["search_regex"], '"title":')
    assert "ansible.builtin.fail" in boundary["rescue"][-1]
    program = boundary["rescue"][0]["ansible.builtin.command"]["argv"][-1]
    private = "SYNTHETIC_PRIVATE_NOTIFICATION_AUTHORITY"
    messages = [
        private,
        "watchdog notification failed",
        "watchdog: notification delivery failed",
        "Failed at step NAMESPACE spawning executable",
        "Failed at step " + private,
        "watchdog: consecutive_fails=1 alerts_this_hour=2 kicks_this_hour=1 classes="
        + private,
    ]
    outputs = {
        "systemctl": "Result=exit-code\nExecMainStatus=1\nEnvironment="
        + private
        + "\nExecStartPre={ path=/usr/bin/python3 ; argv[]="
        + private
        + " ; ignore_errors=yes ; code=exited ; status=0 }",
        "journalctl": "\n".join(
            json.dumps({"MESSAGE": message}) for message in messages
        ),
    }
    for name, output in outputs.items():
        executable = tmp_path / name
        code = "print(" + repr(output) + ")\n"
        if name == "journalctl":
            metadata = json.dumps(
                {
                    "MESSAGE": "watchdog-credential-metadata mode=0o100400 uid=0 gid=0 nlink=0 size=144 readonly=1"
                }
            )
            code = (
                "import sys\nif '--grep=^watchdog-credential-metadata ' in sys.argv:\n"
                "    print(" + repr(metadata) + ")\nelse:\n    " + code
            )
        executable.write_text("#!" + sys.executable + "\n" + code)
        executable.chmod(0o755)
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"]},
        timeout=8,
    )
    assert result.returncode == 0 and not result.stderr
    report = json.loads(result.stdout)
    assert report["unit"] == {"Result": "exit-code", "ExecMainStatus": "1"}
    assert report["pre_start"] == [{"code": "exited", "status": 0}]
    assert "unit startup step=NAMESPACE" in report["journal_signals"]
    assert "watchdog counters=1,2,1" in report["journal_signals"]
    assert "watchdog notification failed" in report["journal_signals"]
    assert (
        "watchdog-credential-metadata mode=0o100400 uid=0 gid=0 nlink=0 size=144 readonly=1"
        in report["journal_signals"]
    )
    assert private not in result.stdout
