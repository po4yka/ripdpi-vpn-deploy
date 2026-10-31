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
    vars_["vpn"]["enable_nginx_xhttp"] = False
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
    assert config["outbounds"][1]["streamSettings"]["finalmask"] == {"tcp": [{"type": "sudoku", "settings": {}}]}


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
    assert f"XRAY_REALITY_TARGET={vars_['xray']['target']}" in rendered
    assert f"XRAY_REALITY_SNI={vars_['xray']['server_names'][0]}" in rendered
    assert "NTFY_" not in rendered
    assert "PUSHOVER_" not in rendered
    vars_["vpn_subscription_only"] = True
    quiet = render_template(TEMPLATES / "vpn-watchdog.env.j2", vars_)
    assert "XRAY_REALITY_TARGET=\n" in quiet and "XRAY_REALITY_SNI=\n" in quiet


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
    assert "TimeoutStartSec=565s" in unit
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
    from template_render import render_fragment

    journal_record = {
        "__CURSOR": "s=actual-journal-boundary",
        "MESSAGE": "untrusted message\n-- cursor: s=old-boundary\nmore text",
    }
    assert (
        render_fragment(
            "journal-cursor.txt",
            cursor_argument,
            {"watchdog_journal_boundary": {"stdout": json.dumps(journal_record)}},
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


def test_failure_fixture_admits_guarded_config_and_explicit_runtime_authority(tmp_path, monkeypatch):
    """Actual semantic admission; the intentional protocol stub is not engine proof."""
    import importlib.util
    import subprocess
    import yaml
    from transport_fixtures import guarded_xray_config
    from template_render import render_fragment

    scenario = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/watchdog/molecule/failure/converge.yml").read_text()
    )[0]
    variables = scenario["vars"]
    fixture = variables["watchdog_failure_server_config"]
    assert fixture == guarded_xray_config("watchdog-failure")
    config_task = next(task for task in scenario["pre_tasks"]
                       if task["name"] == "Drop fake Xray server config")
    config = render_fragment("failure-config.json", config_task["ansible.builtin.copy"]["content"], variables)
    assert json.loads(config) == fixture
    assert config_task["no_log"] is True and config_task["diff"] is False
    assert config_task["ansible.builtin.copy"]["mode"] == "0600"
    candidate = tmp_path / "config.json"
    candidate.write_text(config)
    candidate.chmod(int(config_task["ansible.builtin.copy"]["mode"], 8))
    assert candidate.stat().st_mode & 0o777 == 0o600
    spec = importlib.util.spec_from_file_location(
        "watchdog_failure_xray_validator", REPO_ROOT / "ansible/roles/xray/files/xray_validate.py"
    )
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.read_candidate(str(candidate))
    candidate.write_text("{}\n")
    with pytest.raises(ValueError, match="unguarded-outbound-shape"):
        validator.read_candidate(str(candidate))

    unit_task = next(task for task in scenario["pre_tasks"]
                     if task["name"] == "Install fake Xray service")
    unit = render_fragment("failure-unit.txt", unit_task["ansible.builtin.copy"]["content"], variables)
    binary = variables["watchdog_failure_runtime_binary"]
    assets = variables["watchdog_failure_asset_dir"]
    assert binary.startswith("/opt/watchdog-fixture/releases/v1/")
    assert assets.startswith("/opt/watchdog-fixture/releases/v1/")
    assert f"ExecStart={binary} run -config /etc/xray/config.json" in unit
    environment = " ".join(line.removeprefix("Environment=") for line in unit.splitlines()
                           if line.startswith("Environment="))
    def show(argv, **kwargs):
        assert argv == ["systemctl", "show", "xray.service", "--property=Environment", "--value"]
        return subprocess.CompletedProcess(argv, 0, environment, "")
    monkeypatch.setattr(validator.subprocess, "run", show)
    assert validator.managed_authority(None, "XRAY_RUNTIME_BINARY") == binary
    assert validator.managed_authority(None, "XRAY_LOCATION_ASSET") == assets
    environment = f"XRAY_LOCATION_ASSET={assets}"
    with pytest.raises(ValueError, match="missing or ambiguous runtime authority"):
        validator.managed_authority(None, "XRAY_RUNTIME_BINARY")
    link = next(task for task in scenario["pre_tasks"]
                if task["name"] == "Expose failure-fixture CLI without choosing its accepted runtime")
    assert link["ansible.builtin.file"] == {
        "src": "{{ watchdog_failure_runtime_binary }}", "dest": "/usr/local/bin/xray",
        "state": "link", "owner": "root", "group": "root",
    }


def test_watchdog_fails_when_stats_service_is_not_queryable():
    rendered = render_template(TEMPLATES / "vpn-watchdog.sh.j2", _multi_cohort_vars())

    assert '"xray StatsService query"' in rendered
    assert 'api statsquery "--server=${XRAY_API_SERVER}"' in rendered


def test_watchdog_sandbox_allows_xray_config_validation_to_open_logs():
    variables = _multi_cohort_vars()
    variables["xray_log_dir"] = "/var/lib/vpn-xray-logs-custom"

    rendered = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)

    assert "ReadWritePaths=/var/lib/vpn-watchdog /var/lib/vpn-xray-logs-custom" in rendered


def test_watchdog_sandbox_keeps_xray_logs_read_only_when_xray_is_disabled():
    variables = _multi_cohort_vars()
    variables["vpn"].update(enable_xray_reality=False, enable_nginx_xhttp=False)

    rendered = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)

    assert "/var/lib/vpn-xray-logs" not in rendered


def test_watchdog_sandbox_allows_nginx_config_validation_to_open_logs():
    variables = _multi_cohort_vars()
    variables["vpn"]["enable_xray_reality"] = False
    variables["vpn"]["enable_nginx_xhttp"] = True

    rendered = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)

    assert "ReadWritePaths=/var/lib/vpn-watchdog /var/lib/vpn-xray-logs /var/log/nginx" in rendered


def test_reality_probe_requires_the_explicit_service_address() -> None:
    variables = _multi_cohort_vars()
    variables.pop("vpn_service_address")

    with pytest.raises(UndefinedError, match="vpn_service_address"):
        render_template(TEMPLATES / "reality-probe.json.j2", variables)


@pytest.mark.parametrize(
    "authority,mount_failure", [(True, False), (False, False), (True, True)]
)
def test_failure_sender_wrapper_preserves_delegate_inputs_and_result(
    tmp_path, authority, mount_failure
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
    if mount_failure:
        source = source.replace(
            "import sys\n",
            "import sys\n"
            "def failed_mount(path):\n"
            "    raise OSError(95, 'SYNTHETIC_PRIVATE_MOUNT_ERROR')\n"
            "os.statvfs = failed_mount\n",
        )
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
        metadata_output = result.stdout.splitlines(keepends=True)[1]
        if mount_failure:
            assert (
                result.stdout.splitlines()[1]
                == "watchdog-credential-metadata stage=mount-stat errno=95"
            )
            metadata_output = result.stdout.splitlines(keepends=True)[2]
        assert re.fullmatch(
            r"watchdog-credential-metadata mode=0o100400 uid=[0-9]+ gid=[0-9]+ nlink=1 size=[0-9]+ readonly="
            + ("unknown" if mount_failure else "0")
            + r"\n",
            metadata_output,
        )
    else:
        assert (
            result.stdout.splitlines()[-1]
            == "watchdog-credential-metadata stage=file-stat errno=2"
        )
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
    outputs["systemctl"] += "\nLoadCredential=[unprintable]"
    for name, output in outputs.items():
        executable = tmp_path / name
        code = "print(" + repr(output) + ")\n"
        if name == "systemctl":
            unit = "[Service]\nLoadCredential=notifications.json:" + private
            code = (
                "import sys\nif 'cat' in sys.argv:\n    print("
                + repr(unit)
                + ")\nelse:\n    "
                + code
            )
        if name == "journalctl":
            metadata = (
                json.dumps(
                    {
                        "MESSAGE": "watchdog-credential-metadata mode=0o100400 uid=0 gid=0 nlink=0 size=144 readonly=1"
                    }
                )
                + "\n"
                + json.dumps(
                    {"MESSAGE": "watchdog-credential-metadata stage=file-stat errno=2"}
                )
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
    assert report["effective_unit_required_credential"] is True
    assert "unit startup step=NAMESPACE" in report["journal_signals"]
    assert "watchdog counters=1,2,1" in report["journal_signals"]
    assert "watchdog notification failed" in report["journal_signals"]
    assert (
        "watchdog-credential-metadata mode=0o100400 uid=0 gid=0 nlink=0 size=144 readonly=1"
        in report["journal_signals"]
    )
    assert private not in result.stdout


@pytest.mark.parametrize("scenario", ["default", "failure"])
@pytest.mark.parametrize("initial", ["private", "shared"])
def test_owned_molecule_runtime_propagation_is_prepared_only_when_needed(
    tmp_path, scenario, initial
):
    import os
    import subprocess
    import sys
    import yaml

    fixture = yaml.safe_load(
        (
            REPO_ROOT / "ansible/roles/watchdog/molecule" / scenario / "converge.yml"
        ).read_text()
    )[0]
    tasks = fixture["pre_tasks"][:4]
    assert tasks[0]["ansible.builtin.command"]["argv"] == [
        "findmnt",
        "--mountpoint",
        "/run",
        "--output",
        "PROPAGATION",
        "--noheadings",
    ]
    assert tasks[1]["ansible.builtin.command"]["argv"] == [
        "mount",
        "--make-rshared",
        "/run",
    ]
    assert "ansible.builtin.assert" in tasks[-1]
    state = tmp_path / "propagation"
    state.write_text(initial)
    calls = tmp_path / "calls"
    for name in ("findmnt", "mount"):
        executable = tmp_path / name
        operation = (
            "print(state.read_text())"
            if name == "findmnt"
            else "state.write_text('shared'); calls.write_text(' '.join(sys.argv[1:]))"
        )
        executable.write_text(
            "#!"
            + sys.executable
            + "\nimport sys\nfrom pathlib import Path\n"
            + "state=Path("
            + repr(str(state))
            + ")\ncalls=Path("
            + repr(str(calls))
            + ")\n"
            + operation
            + "\n"
        )
        executable.chmod(0o755)
    playbook = tmp_path / "play.yml"
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
                        "ansible_become": False,
                    },
                    "environment": {
                        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"]
                    },
                    "tasks": tasks,
                }
            ]
        )
    )
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        capture_output=True,
        text=True,
        env={**os.environ, "ANSIBLE_CONFIG": str(REPO_ROOT / "ansible/ansible.cfg")},
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert state.read_text() == "shared"
    if initial == "private":
        assert calls.read_text() == "--make-rshared /run"
    else:
        assert not calls.exists()


@pytest.mark.parametrize("xray,hysteria,control", [(True, True, 60), (True, False, 60), (False, True, 60), (False, False, 60)])
@pytest.mark.parametrize("xhttp", [False, True])
def test_service_deadline_includes_each_enabled_guarded_recovery(xray, hysteria, control, xhttp):
    variables = _multi_cohort_vars()
    variables["vpn"].update(enable_xray_reality=xray, enable_hysteria=hysteria, enable_nginx_xhttp=xhttp)
    variables["transport_egress_control_timeout_seconds"] = control
    unit = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)
    probe_budget = 300 + (3 + int(xhttp) + 2 * int(hysteria)) * variables["watchdog"].get("reality_probe_timeout", 15)
    expected = probe_budget + (int(xray or xhttp)+int(hysteria))*(3*control+5)
    assert f"TimeoutStartSec={expected}s" in unit


def test_p1_only_retains_backend_sandbox_paths_and_recovery_budget():
    variables = _multi_cohort_vars()
    variables["vpn"].update(enable_xray_reality=False, enable_nginx_xhttp=True, enable_hysteria=False)
    variables["watchdog_reality_probes"] = []
    unit = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)
    assert " /var/lib/vpn-xray-logs" in unit
    assert "TimeoutStartSec=425s" in unit
    environment = render_template(TEMPLATES / "vpn-watchdog.env.j2", variables)
    assert "ENABLE_XRAY=false" in environment and "ENABLE_NGINX_XHTTP=true" in environment
    assert "XHTTP_BACKEND_PORT=10085" in environment


def test_subscription_only_has_no_absent_transport_probes():
    variables = _multi_cohort_vars()
    variables["vpn_subscription_only"] = True
    variables["vpn"].update(enable_xray_reality=True, enable_nginx_xhttp=True, enable_hysteria=True, enable_amneziawg=True)
    unit = render_template(TEMPLATES / "vpn-watchdog.service.j2", variables)
    assert "/var/lib/vpn-xray-logs" not in unit
    environment = render_template(TEMPLATES / "vpn-watchdog.env.j2", variables)
    for toggle in ("ENABLE_XRAY", "ENABLE_NGINX_XHTTP", "ENABLE_HYSTERIA", "ENABLE_AMNEZIAWG"):
        assert toggle + "=false" in environment


def test_environment_lists_every_enabled_xhttp_frontend():
    variables = _multi_cohort_vars()
    variables["vpn"]["enable_nginx_xhttp"] = True
    variables["nginx_xhttp"]["fallback_enabled"] = True
    variables["nginx_xhttp_public_port"] = 2443
    rendered = render_template(TEMPLATES / "vpn-watchdog.env.j2", variables)
    assert "NGINX_PORT=2443\nXHTTP_BACKEND_PORT=10085\nNGINX_FALLBACK_PORT=2083" in rendered


@pytest.mark.parametrize("subscription_only", [False, True])
def test_disabled_xhttp_does_not_require_nginx_role_variables(subscription_only):
    values = _multi_cohort_vars()
    values["vpn"]["enable_nginx_xhttp"] = subscription_only
    values["vpn_subscription_only"] = subscription_only
    for name in ("nginx_xhttp_public_port", "nginx_xhttp_port", "nginx_xhttp_fallback_port", "nginx_xhttp"):
        values.pop(name, None)
    rendered = render_template(TEMPLATES / "vpn-watchdog.env.j2", values)
    assert "NGINX_PORT=0\nXHTTP_BACKEND_PORT=0" in rendered


def _reality_target_handshake_probe() -> str:
    rendered = render_template(TEMPLATES / "vpn-watchdog.sh.j2", _multi_cohort_vars())
    assert 'classes[reality_target_drift]=' in rendered
    start = rendered.index("<<'PY'\n", rendered.index("reality_target_handshake() {")) + len("<<'PY'\n")
    return rendered[start:rendered.index("\nPY\n", start)]


@pytest.mark.parametrize(
    ("alpn", "trusted", "expected"),
    [(["h2", "http/1.1"], True, 0), (["http/1.1"], True, 2), (["h2"], False, 1)],
    ids=["h2-trusted", "no-h2", "untrusted-chain"],
)
def test_reality_target_probe_requires_h2_over_a_trusted_tls13_handshake(tmp_path, alpn, trusted, expected):
    import os
    import socket
    import ssl
    import subprocess
    import sys
    import threading

    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                    "-days", "2", "-subj", "/CN=edge.example.test", "-addext", "subjectAltName=DNS:edge.example.test",
                    "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True)
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.minimum_version = ssl.TLSVersion.TLSv1_3
    server.load_cert_chain(cert, key)
    server.set_alpn_protocols(alpn)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(10)

    def serve():
        with listener:
            try:
                connection, _ = listener.accept()
                with server.wrap_socket(connection, server_side=True):
                    pass
            except (OSError, ssl.SSLError):
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    environment = {**os.environ, "SSL_CERT_FILE": str(cert)} if trusted else {**os.environ, "SSL_CERT_FILE": os.devnull}
    result = subprocess.run([sys.executable, "-", f"127.0.0.1:{listener.getsockname()[1]}", "edge.example.test"],
                            input=_reality_target_handshake_probe(), text=True, capture_output=True, env=environment, timeout=30)
    thread.join(10)
    assert result.returncode == expected, result.stderr
