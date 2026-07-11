"""Hermetic tests for managed operator cron serialization."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "scripts" / "install-operator-crons.sh"
MARKER_BEGIN = "# vpn-deploy: BEGIN"


def _make_stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def cron_repo(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    repo = tmp_path / "repo with 100% coverage"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(INSTALLER, scripts / INSTALLER.name)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    call_log = tmp_path / "calls.log"
    marker = tmp_path / "side-effect.marker"
    _make_stub(
        bin_dir,
        "make",
        '''printf '%s|%s|%s|%s|%s|%s|%s\n' "$PWD" "${PROVIDER-}" "${ENV-}" "${GREEN_ENV-}" "${LIVENESS_CONFIG-}" "${VANTAGE-}" "$*" >> "$CALL_LOG"''',
    )
    _make_stub(bin_dir, "logger", "cat >/dev/null")
    _make_stub(bin_dir, "crontab", "touch \"$SIDE_EFFECT_MARKER\"; exit 99")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "PROVIDER": "upcloud",
            "ENV": "prod",
            "CALL_LOG": str(call_log),
            "SIDE_EFFECT_MARKER": str(marker),
        }
    )
    return repo, env, marker


def _run(repo: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(repo / "scripts/install-operator-crons.sh"), "--dry-run"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )


def _cron_command(output: str, target: str) -> str:
    line = next(line for line in output.splitlines() if f"make {target}" in line)
    if line.startswith("@daily"):
        return line.split(maxsplit=1)[1]
    match = re.match(r"\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(.*)", line)
    assert match
    return match.group(1)


def _execute(command: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["/bin/bash", "-c", command], env=env, capture_output=True, text=True)


def _last_call(env: dict[str, str]) -> list[str]:
    return Path(env["CALL_LOG"]).read_text().splitlines()[-1].split("|", 6)


def test_base_block_quotes_every_value_and_escapes_repo_percent(cron_repo):
    repo, env, marker = cron_repo
    result = _run(repo, env)

    assert result.returncode == 0, result.stderr
    expected_repo = str(repo).replace(" ", "\\ ").replace("%", "\\%")
    executable_lines = [line for line in result.stdout.splitlines() if " make " in line]
    assert executable_lines
    assert all(f"cd {expected_repo} &&" in line for line in executable_lines)
    assert "SHELL=/bin/bash" in result.stdout
    assert "PROVIDER=upcloud ENV=prod" in result.stdout
    assert not marker.exists()


def test_base_cron_command_executes_with_exact_values(cron_repo):
    repo, env, _ = cron_repo
    rendered = _run(repo, env)
    command = _cron_command(rendered.stdout, "burn-check")
    result = _execute(command, env)

    assert result.returncode == 0, result.stderr
    assert _last_call(env) == [str(repo), "upcloud", "prod", "", "", "", "burn-check"]


def test_warm_spare_preserves_liveness_path_and_green_env(cron_repo):
    repo, env, _ = cron_repo
    liveness = repo / "configs with spaces" / "live%ness.yaml"
    liveness.parent.mkdir()
    liveness.write_text("checks: []\n")
    env.update({"WARM_SPARE_ENV": "green-2026", "LIVENESS_CONFIG": str(liveness)})

    rendered = _run(repo, env)
    result = _execute(_cron_command(rendered.stdout, "watch-spare"), env)

    assert result.returncode == 0, result.stderr
    assert _last_call(env) == [str(repo), "upcloud", "prod", "green-2026", str(liveness), "", "watch-spare"]


def test_payload_host_reaches_make_as_one_exact_argument(cron_repo):
    repo, env, _ = cron_repo
    env["PAYLOAD_THROTTLE_HOST"] = "[2001:db8::7]"

    rendered = _run(repo, env)
    command = _cron_command(rendered.stdout, "probe-payload-throttle")
    payload_log = repo / "payload throttle.log"
    command = command.replace(">>/tmp/vpn-payload-throttle.log", f">>{shlex.quote(str(payload_log))}")
    result = _execute(command, env)

    assert result.returncode == 0, result.stderr
    assert _last_call(env)[-1] == "probe-payload-throttle HOST=[2001:db8::7]"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PROVIDER", "upcloud;touch-bad"),
        ("ENV", "bad env"),
        ("WARM_SPARE_ENV", "$(touch-bad)"),
        ("PAYLOAD_THROTTLE_HOST", "-option"),
        ("PAYLOAD_THROTTLE_HOST", "host.example;touch-bad"),
    ],
)
def test_invalid_inputs_exit_before_render_or_side_effect(cron_repo, name, value):
    repo, env, marker = cron_repo
    env[name] = value

    result = _run(repo, env)

    assert result.returncode == 2
    assert MARKER_BEGIN not in result.stdout
    assert not marker.exists()
    assert not Path(env["CALL_LOG"]).exists()


def test_valid_vantage_is_rendered_and_executed_exactly(cron_repo):
    repo, env, _ = cron_repo
    env["REALITY_TARGET_VANTAGE"] = "filtered.cohort-a"

    rendered = _run(repo, env)
    result = _execute(_cron_command(rendered.stdout, "monitor-reality-target"), env)

    assert result.returncode == 0, result.stderr
    assert "VANTAGE=filtered.cohort-a" in rendered.stdout
    assert _last_call(env)[-2] == "filtered.cohort-a"
    assert _last_call(env)[-1] == "monitor-reality-target"


@pytest.mark.parametrize("value", ["unfiltered", "bad vantage", "$(touch-bad)"])
def test_invalid_vantage_is_rejected_before_render(cron_repo, value):
    repo, env, marker = cron_repo
    env["REALITY_TARGET_VANTAGE"] = value

    result = _run(repo, env)

    assert result.returncode == 2
    assert MARKER_BEGIN not in result.stdout
    assert not marker.exists()
    assert not Path(env["CALL_LOG"]).exists()
