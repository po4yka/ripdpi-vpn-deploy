"""`state pull` wrapper boundary; a stub replaces scripts/terraform-env.sh."""
from __future__ import annotations

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
