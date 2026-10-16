"""Warm AWG runtime/unit notification adoption with exact ELF processes.

Source acquisition is owned by the pinned native builder. This test republishes
its exact bytes to a new inode and executes the role's real notification and
handler, independently of the private configuration transaction.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest
import yaml

from test_transport_semantics_native import command, exact_awg_sources

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/amneziawg"
pytestmark = pytest.mark.native_runtime


def test_warm_binary_and_unit_adoption_then_unchanged_convergence(tmp_path):
    go, tools = exact_awg_sources()
    assert os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    assert Path('/run/systemd/system').is_dir()
    token = "warm" + uuid.uuid4().hex[:7]
    interface = "a" + uuid.uuid4().hex[:10]
    unit = Path('/etc/systemd/system') / f'awg-quick@{interface}.service'
    assert not unit.exists()
    private = Path('/var/lib') / token
    assert not private.exists()
    private.mkdir(mode=0o700)
    executable = private / 'amneziawg-go'
    shutil.copyfile(go, executable); executable.chmod(0o755)
    bin_dir = private / 'bin'; bin_dir.mkdir(mode=0o700)
    # CI builds under /home, which the real unit deliberately hides. Stage
    # exact runtime bytes beside the private fixture, as deployment does.
    staged_tools = bin_dir / 'awg'
    shutil.copyfile(tools, staged_tools); staged_tools.chmod(0o755)
    quick_source = tools.parent / 'wg-quick/linux.bash'
    assert quick_source.is_file()
    quick = private / 'awg-quick'
    shutil.copyfile(quick_source, quick); quick.chmod(0o755)
    key = command([str(tools), 'genkey']).strip()
    config = private / (interface + '.conf')
    config.write_text('[Interface]\nPrivateKey = ' + key + '\nAddress = 10.88.0.1/24\nMTU = 1420\n')
    config.chmod(0o600)
    config_bytes = config.read_bytes()
    base = (ROLE / 'templates/awg-quick@.service.j2').read_text()
    # Only fixture resource locations and outer network isolation differ.
    base = base.replace('ExecStart=/usr/bin/awg-quick up %i', f'ExecStart=/bin/bash {quick} up {config}')
    base = base.replace('ExecStop=/usr/bin/awg-quick down %i', f'ExecStop=/bin/bash {quick} down {config}')
    base = base.replace('[Service]', '[Service]\nNetworkNamespacePath=/run/netns/' + token +
                        '\nEnvironment=WG_QUICK_USERSPACE_IMPLEMENTATION=' + str(executable) +
                        '\nEnvironment=PATH=' + str(bin_dir) + ':/usr/sbin:/usr/bin:/sbin:/bin')
    template = private / 'unit.j2'; template.write_text(base); template.chmod(0o600)
    tasks = yaml.safe_load((ROLE / 'tasks/enable.yml').read_text())
    notification = next(task for task in tasks if task['name'] == 'Apply changed AmneziaWG runtimes to current instances')
    installation = copy.deepcopy(next(task for task in tasks if task['name'] == 'Install awg-quick systemd unit (shared across instances)'))
    installation['ansible.builtin.template'].update(src=str(template), dest=str(unit))
    handlers = yaml.safe_load((ROLE / 'handlers/main.yml').read_text())

    def converge(changed):
        play = private / 'play.yml'
        play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
            'vars': {'ansible_python_interpreter': sys.executable, 'amneziawg_role_enabled': True,
                     '_awg_instances': [{'name': interface}],
                     'runtime_build_results': {'amneziawg-go': {'changed': changed}}},
            'tasks': [notification, installation, {'ansible.builtin.meta': 'flush_handlers'}],
            'handlers': handlers}], sort_keys=False))
        play.chmod(0o600)
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(play)], capture_output=True,
                                text=True, timeout=45, env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')})
        assert result.returncode == 0, 'native warm AWG convergence failed'
        assert key not in result.stdout + result.stderr
        assert config.read_bytes() == config_bytes
        return result.stdout

    def daemon():
        group = command(['systemctl', 'show', unit.name, '--property=ControlGroup', '--value']).strip()
        assert group.startswith('/') and '..' not in group
        pids = (Path('/sys/fs/cgroup') / group.lstrip('/') / 'cgroup.procs').read_text().split()
        matches = [int(pid) for pid in pids if Path('/proc', pid, 'exe').exists()
                   and Path('/proc', pid, 'exe').resolve().name == executable.name]
        assert len(matches) == 1, 'exact owned AWG daemon absent'
        pid = matches[0]
        assert os.path.samefile(Path('/proc', str(pid), 'exe'), executable)
        return pid, Path('/proc', str(pid), 'status').read_text()

    try:
        command(['ip', 'netns', 'add', token])
        command(['ip', '-n', token, 'link', 'set', 'lo', 'up'])
        converge(True)
        first, status = daemon()
        assert 'NoNewPrivs:\t1' in status
        assert int(next(line.split()[1] for line in status.splitlines() if line.startswith('CapEff:')), 16) == 1 << 12
        # Publication-only: private config is byte-identical; old running inode
        # must be replaced through the actual role notification.
        candidate = private / 'candidate'
        shutil.copyfile(go, candidate); candidate.chmod(0o755)
        candidate.replace(executable)
        converge(True)
        second, _ = daemon()
        assert second != first
        # Unit-only sandbox change must also reach the actual daemon.
        template.write_text(base.replace('[Service]', '[Service]\nUMask=0077', 1))
        converge(False)
        third, status = daemon()
        assert third != second and 'Umask:\t0077' in status
        output = converge(False)
        assert daemon()[0] == third and 'changed=0' in output
    finally:
        subprocess.run(['systemctl', 'stop', unit.name], capture_output=True, timeout=15)
        if unit.exists():
            unit.unlink()
            command(['systemctl', 'daemon-reload'])
        subprocess.run(['systemctl', 'reset-failed', unit.name], capture_output=True, timeout=10)
        subprocess.run(['ip', 'netns', 'delete', token], capture_output=True, timeout=10)
        shutil.rmtree(private)
