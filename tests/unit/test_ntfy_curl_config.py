"""The curl config helper keeps the notification destination and token out of argv."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ntfy-curl-config.sh"


def run(**env):
    return subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, env={"PATH": os.environ["PATH"], **env}
    )


def test_config_carries_destination_and_token_with_curl_quoting():
    result = run(NTFY_URL="https://alerts.example/", NTFY_TOPIC="topic", NTFY_TOKEN='to"k\\en')
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        'url = "https://alerts.example/topic"\n'
        'header = "Authorization: Bearer to\\"k\\\\en"\n'
    )


def test_token_is_optional():
    result = run(NTFY_URL="https://alerts.example", NTFY_TOPIC="topic")
    assert result.stdout == 'url = "https://alerts.example/topic"\n'


def test_there_is_no_default_destination():
    result = run(NTFY_TOPIC="topic")
    assert result.returncode == 1 and not result.stdout


def test_line_break_in_a_value_is_refused():
    result = run(NTFY_URL="https://alerts.example", NTFY_TOPIC="topic", NTFY_TOKEN="a\nurl = x")
    assert result.returncode == 1 and "url = x" not in result.stdout


INSTALLER = SCRIPT.parent / "install-operator-crons.sh"


def test_cron_block_carries_the_operator_destination_and_resolver():
    plan = subprocess.run(
        ["bash", str(INSTALLER), "--dry-run"], capture_output=True, text=True,
        env={**os.environ, "NTFY_URL": "https://alerts.example", "DOH_URL": "https://resolver.example/dns-query"},
    )
    assert 'NTFY_URL="https://alerts.example"\n' in plan.stdout
    assert 'DOH_URL="https://resolver.example/dns-query"\n' in plan.stdout


def test_cron_block_has_no_destination_unless_the_operator_sets_one():
    env = {key: value for key, value in os.environ.items() if key not in {"NTFY_URL", "DOH_URL"}}
    plan = subprocess.run(["bash", str(INSTALLER), "--dry-run"], capture_output=True, text=True, env=env)
    assert "NTFY_URL" not in plan.stdout and "DOH_URL" not in plan.stdout and "ntfy.sh" not in plan.stdout


def test_cron_block_refuses_a_destination_that_is_not_plain_https():
    plan = subprocess.run(
        ["bash", str(INSTALLER), "--dry-run"], capture_output=True, text=True,
        env={**os.environ, "NTFY_URL": 'http://alerts.example" extra'},
    )
    assert plan.returncode != 0 and "extra" not in plan.stdout
