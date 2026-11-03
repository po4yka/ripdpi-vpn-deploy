"""Release identity and real peer-process admission for engine CI."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from test_bootstrap_readiness_io import descendant_program, stopped

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def engine():
    spec = importlib.util.spec_from_file_location('engine_interop', ROOT / 'scripts/check-engine-interop.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.mark.parametrize('mutation', [None, 'version', 'source', 'go'])
def test_release_policy_binds_complete_candidate_and_toolchain(engine, tmp_path, monkeypatch, mutation):
    policy = engine.pins()
    for name in ('tools', 'secrets'):
        (tmp_path / name).mkdir()
    (tmp_path / 'secrets/prod.secrets.example.yaml').write_bytes((ROOT / 'secrets/prod.secrets.example.yaml').read_bytes())
    (tmp_path / 'mise.toml').write_bytes((ROOT / 'mise.toml').read_bytes())
    if mutation == 'version':
        policy['xray_version'] = 'v1.2.3'
    elif mutation == 'source':
        policy['xray_revision'] = 'main'
    elif mutation == 'go':
        policy['go_version'] = '1.27.2'
    (tmp_path / 'tools/engine-interop.json').write_text(json.dumps(policy))
    monkeypatch.setattr(engine, 'ROOT', tmp_path)
    if mutation:
        with pytest.raises(ValueError):
            engine.pins()
    else:
        assert engine.pins() == policy


@pytest.mark.parametrize('payload,accepted', [
    ({'endpoint': '127.0.0.1:54321', 'udp': '127.0.0.1:54322', 'udp2': '127.0.0.1:54323'}, True),
    ({'endpoint': '127.0.0.1:54321', 'vision': '192.0.2.1:54322'}, False),
    ({'endpoint': '0.0.0.0:54321'}, False),
    ({'endpoint': '127.0.0.1:0'}, False),
    ({'endpoint': 123}, False),
    ({'tcp': '127.0.0.1:54321'}, False),
    ({'endpoint': '127.0.0.1:54321', 'FIELD': 'refused'}, False),
])
def test_peer_announcement_bounds_actual_process_to_loopback(engine, payload, accepted):
    with subprocess.Popen([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(sys.argv[1].encode())',
                           json.dumps(payload) + '\n'], stdout=subprocess.PIPE) as peer:
        if accepted:
            assert engine.announcement(peer) == payload
        else:
            with pytest.raises(ValueError):
                engine.announcement(peer)


def test_peer_partial_line_cannot_extend_startup_deadline(engine):
    with subprocess.Popen([sys.executable, '-c', 'import sys,time;sys.stdout.write("{");sys.stdout.flush();time.sleep(10)'],
                          stdout=subprocess.PIPE) as peer:
        try:
            with pytest.raises(TimeoutError):
                engine.announcement(peer, timeout=0.05)
        finally:
            peer.terminate();peer.wait(timeout=2)


def test_engine_checkout_rejects_wrong_revision_and_worktree_changes(engine, tmp_path, isolated_synthetic_git_config):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], stderr=subprocess.DEVNULL, text=True).strip()
    git('init', '-q')
    git('config', 'user.name', 'Engine fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    (tmp_path / 'engine').write_text('source')
    git('add', 'engine');git('commit', '-qm', 'test: add engine fixture')
    revision = git('rev-parse', 'HEAD')
    engine.checkout(tmp_path, revision)
    with pytest.raises(ValueError):
        engine.checkout(tmp_path, 'f' * 40)
    (tmp_path / 'engine').write_text('changed')
    with pytest.raises(ValueError):
        engine.checkout(tmp_path, revision)


@pytest.mark.parametrize('outcome', ['complete', 'timeout', 'cancelled'])
def test_engine_command_reclaims_its_quiet_descendants(engine, tmp_path, outcome):
    marker = tmp_path / 'descendant.json'
    program, stop = descendant_program(marker, wait=outcome != 'complete')
    owner = None
    try:
        if outcome == 'cancelled':
            launch = (
                'import importlib.util,sys\n'
                f'sys.path.insert(0,{str(ROOT / "scripts")!r})\n'
                f'spec=importlib.util.spec_from_file_location("engine",{str(ROOT / "scripts/check-engine-interop.py")!r})\n'
                'engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)\n'
                'with engine.cancellation():\n'
                f' engine.checked([sys.executable,"-c",{program!r}],{str(tmp_path)!r},engine.command_environment(),limit=30)\n'
            )
            owner = subprocess.Popen([sys.executable, '-c', launch], stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 10
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert marker.exists(), 'owned command did not start'
            owner.terminate()
            assert owner.wait(timeout=10) == 143
        elif outcome == 'timeout':
            with pytest.raises(engine.ReadinessError):
                engine.checked([sys.executable, '-c', program], tmp_path,
                               engine.command_environment(), limit=1)
        else:
            engine.checked([sys.executable, '-c', program], tmp_path,
                           engine.command_environment(), limit=10)
        assert stopped(json.loads(marker.read_text())[-1]), 'quiet descendant escaped engine cleanup'
    finally:
        stop.touch()
        if owner is not None:
            if owner.poll() is None:
                owner.kill()
            owner.wait(timeout=5)


def test_stopped_peer_is_reaped_without_signalling_a_reused_process(engine, monkeypatch):
    peer = subprocess.Popen([sys.executable, '-c', 'pass'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    peer.wait(timeout=5)
    def refuse_signal():
        pytest.fail('a reaped peer must not receive a signal')
    monkeypatch.setattr(peer, 'terminate', refuse_signal)
    monkeypatch.setattr(peer, 'kill', refuse_signal)
    engine.stop_peer(peer)
    assert peer.stdin.closed and peer.stdout.closed


@pytest.mark.parametrize('selected,passed,exit_code,accepted', [
    ('selected', 1, 0, True), ('selected', 0, 0, False),
    ('different', 1, 0, False), ('selected', 1, 7, False),
])
def test_engine_check_requires_one_exact_successful_test(engine, tmp_path, selected, passed, exit_code, accepted):
    output = f'test {selected} ... ok\ntest result: ok. {passed} passed; 0 failed; 0 ignored\n'
    command = [sys.executable, '-c', 'import sys;print(sys.argv[1]);sys.exit(int(sys.argv[2]))', output, str(exit_code)]
    if accepted:
        assert output in engine.checked(command, tmp_path, engine.command_environment(), expected_test='selected')
    else:
        with pytest.raises(RuntimeError):
            engine.checked(command, tmp_path, engine.command_environment(), expected_test='selected')
