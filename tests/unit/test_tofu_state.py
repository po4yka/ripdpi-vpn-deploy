"""`state pull` wrapper boundary; a stub replaces scripts/terraform-env.sh."""
from __future__ import annotations

import json

import pytest
import tofu_state


@pytest.fixture
def wrapper(tmp_path, monkeypatch):
    stub = tmp_path / 'terraform-env.sh'
    monkeypatch.setattr(tofu_state, 'WRAPPER', stub)
    def write(body):
        stub.write_text('#!/bin/sh\n' + body)
        stub.chmod(0o700)
    return write


def test_pull_selects_provider_and_environment_and_returns_state_bytes(wrapper):
    wrapper('[ "$1 $2" = "state pull" ] || exit 9\nprintf \'{"provider":"%s","env":"%s"}\' "$PROVIDER" "$ENV"\n')
    assert tofu_state.pull('vultr', 'staging', env={'PATH': '/usr/bin:/bin'}) == b'{"provider":"vultr","env":"staging"}'


def test_pull_returns_identical_bytes_when_check_results_change_order(wrapper, tmp_path):
    a = '{"version":4,"check_results":[{"config_addr":"var.a","objects":[{"object_addr":"x"},{"object_addr":"y"}]},{"config_addr":"var.b","objects":[]}]}'
    b = '{"version":4,"check_results":[{"config_addr":"var.b","objects":[]},{"config_addr":"var.a","objects":[{"object_addr":"y"},{"object_addr":"x"}]}]}'
    (tmp_path / 'a.json').write_text(a)
    (tmp_path / 'b.json').write_text(b)
    wrapper(f'cat "{tmp_path}/$ENV.json"\n')
    first, second = tofu_state.pull('upcloud', 'a'), tofu_state.pull('upcloud', 'b')
    assert first == second
    assert [r['config_addr'] for r in json.loads(first)['check_results']] == ['var.a', 'var.b']


def test_pull_refuses_output_that_is_not_json(wrapper):
    wrapper('echo not-json\n')
    with pytest.raises(tofu_state.StateError):
        tofu_state.pull('upcloud', 'prod')


def test_pull_reports_an_empty_workspace_as_none(wrapper):
    wrapper('printf "\\n"\n')
    assert tofu_state.pull('upcloud', 'prod') is None


@pytest.mark.parametrize('body', ['echo partial; exit 1\n', 'head -c 16777217 /dev/zero\n'])
def test_pull_refuses_failure_and_oversized_state(wrapper, body):
    wrapper(body)
    with pytest.raises(tofu_state.StateError):
        tofu_state.pull('upcloud', 'prod')


def test_pull_kills_a_wrapper_that_exceeds_the_timeout(wrapper):
    wrapper('sleep 30\n')
    with pytest.raises(tofu_state.StateError):
        tofu_state.pull('upcloud', 'prod', timeout=0.2)
