from __future__ import annotations

import os
import pathlib
import socket
import stat
import subprocess

import pytest

pytestmark = pytest.mark.usefixtures("stub_tofu_backend")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "burn-check.sh"


def _write_executable(path: pathlib.Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_burn_check(
    tmp_path: pathlib.Path, curl_script: str, *args: str, third_party: bool = True, **overrides: str
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    metrics_dir = tmp_path / "metrics"
    bin_dir.mkdir()
    metrics_dir.mkdir()

    _write_executable(
        bin_dir / "tofu",
        "#!/usr/bin/env bash\n"
        "case \"$*\" in\n"
        "  *'workspace select test'*) exit 0 ;;\n"
        "  *'output -raw service_ipv4'*) printf '%s\\n' 203.0.113.10 ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )
    _write_executable(bin_dir / "curl", curl_script)
    # The poll loop waits on real time; the stubbed service answers at once.
    _write_executable(bin_dir / "sleep", "#!/bin/sh\nexit 0\n")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "NODE_EXPORTER_TEXTFILE_DIR": str(metrics_dir),
            "ENABLE_HYSTERIA": "false",
            "PROVIDER": "upcloud",
            "ENV": "test",
            "NODES": "node-a.example,node-b.example",
            "FAIL_THRESHOLD": "2",
        }
    )
    env.update(overrides)
    return subprocess.run(
        [str(SCRIPT), *(["--third-party"] if third_party else []), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _metrics(tmp_path: pathlib.Path) -> str:
    return (tmp_path / "metrics" / "vpn_burn.prom").read_text()


def test_api_failure_replaces_stale_green_metrics(tmp_path: pathlib.Path) -> None:
    result = _run_burn_check(
        tmp_path,
        "#!/usr/bin/env bash\nexit 22\n",
    )

    assert result.returncode == 2
    metrics = _metrics(tmp_path)
    assert 'vpn_burn_api_error{provider="upcloud",env="test"} 1' in metrics
    assert 'vpn_burn_run_error{provider="upcloud",env="test"} 1' in metrics
    assert "vpn_burn_failed_nodes" not in metrics
    assert "vpn_burn_last_run_unixtime" in metrics


def test_malformed_api_response_is_explicit_error(tmp_path: pathlib.Path) -> None:
    result = _run_burn_check(
        tmp_path,
        "#!/usr/bin/env bash\nprintf '%s\\n' 'not-json'\n",
    )

    assert result.returncode == 2
    metrics = _metrics(tmp_path)
    assert 'vpn_burn_api_error{provider="upcloud",env="test"} 1' in metrics
    assert 'vpn_burn_run_error{provider="upcloud",env="test"} 1' in metrics


def test_successful_probe_clears_error_metrics(tmp_path: pathlib.Path) -> None:
    result = _run_burn_check(
        tmp_path,
        "#!/usr/bin/env bash\n"
        "case \"$*\" in\n"
        "  *check-tcp*) printf '%s\\n' '{\"request_id\":\"request-1\"}' ;;\n"
        "  *check-result*) printf '%s\\n' '{\"node-a.example\":[[{\"address\":\"203.0.113.10\"}]],\"node-b.example\":[[{\"address\":\"203.0.113.10\"}]]}' ;;\n"
        "  *) exit 22 ;;\n"
        "esac\n",
    )

    assert result.returncode == 0, result.stderr
    metrics = _metrics(tmp_path)
    assert 'vpn_burn_api_error{provider="upcloud",env="test"} 0' in metrics
    assert 'vpn_burn_run_error{provider="upcloud",env="test"} 0' in metrics
    assert 'vpn_burn_failed_nodes{provider="upcloud",env="test"} 0' in metrics


def test_reachability_failure_is_not_reported_as_probe_error(tmp_path: pathlib.Path) -> None:
    result = _run_burn_check(
        tmp_path,
        "#!/usr/bin/env bash\n"
        "case \"$*\" in\n"
        "  *check-tcp*) printf '%s\\n' '{\"request_id\":\"request-1\"}' ;;\n"
        "  *check-result*) printf '%s\\n' '{\"node-a.example\":[[{\"error\":\"timeout\"}]],\"node-b.example\":[[{\"error\":\"timeout\"}]]}' ;;\n"
        "  *) exit 22 ;;\n"
        "esac\n",
    )

    assert result.returncode == 1
    metrics = _metrics(tmp_path)
    assert 'vpn_burn_api_error{provider="upcloud",env="test"} 0' in metrics
    assert 'vpn_burn_run_error{provider="upcloud",env="test"} 0' in metrics
    assert 'vpn_burn_failed_nodes{provider="upcloud",env="test"} 2' in metrics


def test_pending_nodes_are_never_counted_as_burn_failures(tmp_path: pathlib.Path) -> None:
    result = _run_burn_check(
        tmp_path,
        "#!/usr/bin/env bash\n"
        "case \"$*\" in\n"
        "  *check-tcp*) printf '%s\\n' '{\"request_id\":\"request-1\"}' ;;\n"
        "  *check-result*) printf '%s\\n' '{\"node-a.example\":[[{\"address\":\"203.0.113.10\"}]],\"node-b.example\":null}' ;;\n"
        "  *) exit 22 ;;\n"
        "esac\n",
    )

    assert result.returncode == 0, result.stderr
    assert "still pending" in result.stderr
    metrics = _metrics(tmp_path)
    assert 'vpn_burn_run_error{provider="upcloud",env="test"} 1' in metrics
    assert 'vpn_burn_pending_nodes{provider="upcloud",env="test"} 1' in metrics
    # An incomplete run publishes no burn verdict series at all.
    assert "vpn_burn_failed_nodes" not in metrics
    assert "vpn_burn_reachable" not in metrics


RECORDING_CURL = '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$CURL_LOG"\nexit 22\n'


def _udp_listener() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(("127.0.0.1", 0))
    listener.settimeout(0.2)
    return listener


def _received(listener: socket.socket) -> bool:
    try:
        listener.recvfrom(2048)
    except socket.timeout:
        return False
    return True


def _closed_tcp_port() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return str(probe.getsockname()[1])


def test_default_run_uses_no_third_party_service_and_sends_no_udp_probe(tmp_path: pathlib.Path) -> None:
    curl_log = tmp_path / "curl.log"
    with _udp_listener() as listener:
        # NODES stays set: the variable alone must not enable the service.
        result = _run_burn_check(
            tmp_path, RECORDING_CURL, third_party=False, IP="127.0.0.1", TCP_PORT=_closed_tcp_port(),
            CURL_LOG=str(curl_log), ENABLE_HYSTERIA="true", HYSTERIA_PORT=str(listener.getsockname()[1]),
            UDP_PROBE_TIMEOUT="1", FAIL_THRESHOLD="9",
        )
        assert not _received(listener)
    assert not curl_log.exists()
    assert "no third-party service is used" in result.stderr
    # A refused direct probe is a completed burn verdict, whatever FAIL_THRESHOLD the environment holds.
    assert result.returncode == 1, result.stderr
    metrics = _metrics(tmp_path)
    assert 'vpn_burn_total_nodes{provider="upcloud",env="test"} 1' in metrics
    assert 'vpn_burn_failed_nodes{provider="upcloud",env="test"} 1' in metrics
    assert 'vpn_burn_reachable{provider="upcloud",env="test",node="operator"} 0' in metrics
    assert 'vpn_burn_run_error{provider="upcloud",env="test"} 0' in metrics


def test_default_run_reports_a_reachable_listener(tmp_path: pathlib.Path) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        result = _run_burn_check(
            tmp_path, RECORDING_CURL, third_party=False, IP="127.0.0.1", TCP_PORT=str(listener.getsockname()[1]),
            CURL_LOG=str(tmp_path / "curl.log"), NODES="",
        )
    assert result.returncode == 0, result.stderr
    assert 'vpn_burn_reachable{provider="upcloud",env="test",node="operator"} 1' in _metrics(tmp_path)
    assert 'vpn_burn_failed_nodes{provider="upcloud",env="test"} 0' in _metrics(tmp_path)


def test_udp_probe_needs_its_own_option(tmp_path: pathlib.Path) -> None:
    with _udp_listener() as listener:
        _run_burn_check(
            tmp_path, RECORDING_CURL, "--udp-probe", third_party=False, IP="127.0.0.1", TCP_PORT=_closed_tcp_port(),
            CURL_LOG=str(tmp_path / "curl.log"),
            ENABLE_HYSTERIA="true", HYSTERIA_PORT=str(listener.getsockname()[1]), UDP_PROBE_TIMEOUT="1",
        )
        assert _received(listener)


def test_third_party_run_needs_named_vantage_points(tmp_path: pathlib.Path) -> None:
    curl_log = tmp_path / "curl.log"
    result = _run_burn_check(tmp_path, RECORDING_CURL, NODES="", CURL_LOG=str(curl_log))
    assert result.returncode == 64 and not curl_log.exists()


def test_scheduled_entry_passes_no_probe_option(tmp_path) -> None:
    reader = tmp_path / "read-only.sops.json"
    phrase = tmp_path / "state.sops.json"
    reader.touch()
    phrase.touch()
    plan = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "install-operator-crons.sh"), "--dry-run"],
        cwd=REPO_ROOT, env={**os.environ, "PROVIDER": "upcloud", "ENV": "test",
                       "MONITOR_STATE_IDENTITY_SOPS_FILE": str(reader), "STATE_PASSPHRASE_SOPS_FILE": str(phrase)}, text=True, capture_output=True, check=False,
    )
    entry = next(line for line in plan.stdout.splitlines() if "make burn-check" in line)
    assert "NODES" not in entry and "--third-party" not in entry and "--udp-probe" not in entry
    recipe = (REPO_ROOT / "Makefile").read_text().split("\nburn-check:\n", 1)[1].split("\n\n", 1)[0]
    assert recipe.strip() == "PROVIDER=$(PROVIDER) ENV=$(ENV) ./scripts/burn-check.sh"
