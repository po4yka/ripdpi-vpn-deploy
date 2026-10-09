"""Log provisioning rejects link attacks and preserves writable positive startup."""
import importlib.util
import os
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'ansible/roles/xray/files/xray_log_setup.py'
spec = importlib.util.spec_from_file_location('xray_log_setup', SOURCE)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def provision(directory, **kwargs):
    # Test trees are below the user's writable temporary parents. Start from a
    # private root fixture, while still exercising all real descriptor syscalls.
    return setup.provision(str(directory.resolve()), os.getuid(), os.getgid(), **kwargs)


@pytest.fixture
def logs(tmp_path, monkeypatch):
    # Production runs as root with root-owned ancestors. This local subprocess
    # tests the same ownership rules for the executing account.
    original = setup.os.fstat
    def fstat(fd):
        result = original(fd)
        if stat.S_ISDIR(result.st_mode) and result.st_uid != os.getuid():
            values = list(result)
            values[4] = os.getuid()
            values[0] &= ~0o022
            return os.stat_result(values)
        return result
    monkeypatch.setattr(setup.os, 'fstat', fstat)
    return tmp_path / 'logs'


def test_provision_then_append_with_restrictive_modes(logs):
    assert provision(logs)
    assert not provision(logs)
    assert stat.S_IMODE(logs.stat().st_mode) == 0o750
    for name in ('access.log', 'error.log'):
        with (logs / name).open('a') as output:
            output.write('synthetic log\n')
        assert stat.S_IMODE((logs / name).stat().st_mode) == 0o640
    service = (ROOT / 'ansible/roles/xray/templates/xray.service.j2').read_text()
    assert 'ExecStartPre=+' not in service
    assert 'chown' not in service


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'directory', 'fifo'])
def test_hostile_entry_does_not_repair_target(logs, tmp_path, kind):
    logs.mkdir(mode=0o750)
    victim = tmp_path / 'unrelated'
    victim.write_bytes(b'preserve')
    victim.chmod(0o600)
    before = victim.stat()
    entry = logs / 'error.log'
    (logs / 'access.log').write_text('prior')
    (logs / 'access.log').chmod(0o600)
    if kind == 'symlink':
        entry.symlink_to(victim)
    elif kind == 'hardlink':
        os.link(victim, entry)
    elif kind == 'directory':
        entry.mkdir()
    else:
        os.mkfifo(entry)
    with pytest.raises((OSError, ValueError)):
        provision(logs)
    after = victim.stat()
    assert (after.st_uid, after.st_gid, after.st_mode) == (before.st_uid, before.st_gid, before.st_mode)
    assert victim.read_bytes() == b'preserve'
    assert stat.S_IMODE((logs / 'access.log').stat().st_mode) == 0o600


def test_check_mode_does_not_create_missing_logs(logs):
    assert provision(logs, check=True)
    assert not logs.exists()
