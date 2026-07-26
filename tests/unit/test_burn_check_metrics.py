from __future__ import annotations

import os
import pathlib
import stat
import subprocess


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "burn-check.sh"


def _write_executable(path: pathlib.Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_burn_check(tmp_path: pathlib.Path, curl_script: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    metrics_dir = tmp_path / "metrics"
    bin_dir.mkdir()
    metrics_dir.mkdir()

    _write_executable(
        bin_dir / "terraform",
        "#!/usr/bin/env bash\n"
        "case \"$*\" in\n"
        "  *'workspace select test'*) exit 0 ;;\n"
        "  *'output -raw server_ipv4'*) printf '%s\\n' 203.0.113.10 ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )
    _write_executable(bin_dir / "curl", curl_script)

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
    return subprocess.run(
        [str(SCRIPT)],
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
