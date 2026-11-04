"""Module admission and interrupted initramfs recovery, without kernel mutation."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/baseline'
POLICY = (ROLE / 'files/unused-kernel-modules.conf').read_bytes()


@pytest.fixture
def checker(tmp_path):
    spec = importlib.util.spec_from_file_location('module_policy', ROLE / 'files/module-policy-check.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SYS_MODULE = tmp_path / 'sys-module'
    module.SYS_MODULE.mkdir()
    module.BUILTIN = tmp_path / 'modules.builtin'
    module.BUILTIN.write_text('')
    module.BOOT = tmp_path / 'boot'
    module.BOOT.mkdir()
    module.POLICY = tmp_path / 'policy.conf'
    module.POLICY.write_bytes(POLICY)
    module.POLICY.chmod(0o644)
    module.RECEIPT = tmp_path / 'receipt'
    module.CONTAINER = tmp_path / 'not-a-container'
    return module


def test_exact_unused_subsystems_and_direct_load_denial(checker):
    expected = ['ksmbd', 'nfsd', 'tipc', 'rdma_rxe', 'siw', 'ib_srpt',
                'rpcrdma', 'ceph', 'libceph', 'nvmet', 'fou', 'fou6']
    assert checker.modules(POLICY) == expected
    for name in expected:
        assert f'install {name} /bin/false\n'.encode() in POLICY
    assert b'alias ksmbd vpn_denied_ksmbd\n' in POLICY
    assert b'install vpn_denied_ksmbd /bin/false\n' in POLICY


@pytest.mark.parametrize('present', ['loaded', 'built-in', 'metadata-missing'])
def test_admission_refuses_active_or_unprovable_kernel(checker, present):
    if present == 'loaded':
        (checker.SYS_MODULE / 'rdma_rxe').mkdir()
    elif present == 'built-in':
        checker.BUILTIN.write_text('kernel/net/rds/rdma-rxe.ko\n')
    else:
        checker.BUILTIN.unlink()
    with pytest.raises(ValueError):
        checker.admit(checker.modules(POLICY))


@pytest.mark.parametrize('outcome', ['denied', 'dependency', 'target-inserted', 'softdep-override'])
def test_effective_native_denial_allows_dependencies_but_not_target(checker, monkeypatch, outcome):
    def native(argv):
        if '--showconfig' in argv:
            return POLICY.decode()
        if outcome == 'target-inserted':
            return f'insmod /lib/modules/{argv[-1]}.ko.zst\ninstall /bin/false\n'
        if outcome == 'softdep-override':
            return 'insmod /lib/modules/something.ko\n'
        return ('insmod /lib/modules/udp_tunnel.ko.zst\n' if outcome == 'dependency' else '') + 'install /bin/false\n'
    monkeypatch.setattr(checker, 'native', native)
    if outcome in {'target-inserted', 'softdep-override'}:
        with pytest.raises(ValueError, match='ineffective-module-denial'):
            checker.effective(POLICY)
    else:
        checker.effective(POLICY)


@pytest.mark.parametrize('embedded', [None, b'blacklist old_module\n', POLICY])
def test_embedded_policy_bytes_require_repair_even_with_current_receipt(checker, monkeypatch, embedded):
    checker.RECEIPT.write_text(hashlib.sha256(POLICY).hexdigest() + '\n')
    checker.RECEIPT.chmod(0o600)
    (checker.BOOT / 'initrd.img-test').write_text('image')
    extracted = []
    def extract(argv, **kwargs):
        root = Path(argv[-1])
        assert root.stat().st_mode & 0o777 == 0o700
        assert kwargs['env']['TMPDIR'] == str(root)
        extracted.append(root)
        if embedded is not None:
            path = root / 'main/etc/modprobe.d/90-vpn-unused-modules.conf'
            path.parent.mkdir(parents=True)
            path.write_bytes(embedded)
            path.chmod(0o644)
    monkeypatch.setattr(checker.subprocess, 'run', extract)
    assert checker.state(POLICY)['refresh_required'] is (embedded != POLICY)
    assert extracted and not extracted[0].exists()


def test_policy_symlinks_and_writable_records_refuse(checker):
    checker.RECEIPT.symlink_to(checker.POLICY)
    with pytest.raises(ValueError, match='unsafe-policy-file'):
        checker.state(POLICY)
    checker.RECEIPT.unlink()
    checker.RECEIPT.write_text('invalid')
    checker.RECEIPT.chmod(0o666)
    with pytest.raises(ValueError, match='unsafe-policy-file'):
        checker.state(POLICY)


def test_real_tasks_retry_failed_initramfs_before_acknowledgement(tmp_path):
    block = copy.deepcopy(yaml.safe_load((ROLE / 'tasks/module-policy.yml').read_text())[-1])
    block['block'] = block['block'][:-1]
    tasks = block['block']
    helper = (ROLE / 'files/module-policy-check.py').read_text()
    boot = tmp_path / 'boot'
    boot.mkdir()
    image = boot / 'initrd.img-test'
    image.write_text('old image')
    state = tmp_path / 'state'
    marker = state / 'unused-modules.sha256'
    helper = helper.replace("Path('/boot')", f'Path({str(boot)!r})').replace(
        "Path('/var/lib/vpn-baseline/unused-modules.sha256')", f'Path({str(marker)!r})')
    tools = tmp_path / 'bin'
    tools.mkdir()
    fail = tmp_path / 'fail'
    fail.touch()
    calls = tmp_path / 'calls'
    updater = tools / 'update-initramfs'
    updater.write_text(f'#!{sys.executable}\nfrom pathlib import Path\n'
                       f'p=Path({str(calls)!r}); p.write_text(p.read_text()+"call\\n" if p.exists() else "call\\n")\n'
                       f'if Path({str(fail)!r}).exists(): raise SystemExit(1)\n'
                       f'Path({str(image)!r}).write_bytes({POLICY!r})\n')
    updater.chmod(0o755)
    listing = tools / 'unmkinitramfs'
    listing.write_text(f'#!{sys.executable}\nimport sys\nfrom pathlib import Path\n'
                       'p=Path(sys.argv[2])/"main/etc/modprobe.d/90-vpn-unused-modules.conf"\n'
                       'p.parent.mkdir(parents=True)\np.write_bytes(Path(sys.argv[1]).read_bytes())\np.chmod(0o644)\n')
    listing.chmod(0o755)
    for task in tasks:
        for module in ['ansible.builtin.file', 'ansible.builtin.copy']:
            if module in task:
                args = task[module]
                for key in ['path', 'dest']:
                    if key in args:
                        args[key] = args[key].replace('/var/lib/vpn-baseline', str(state))
                args.pop('owner', None)
                args.pop('group', None)
        command = task.get('ansible.builtin.command')
        if command and command['argv'][0] == '/usr/bin/python3':
            command['argv'][0] = sys.executable
            command['argv'][5] = helper
            command['stdin'] = POLICY.decode()
    play = tmp_path / 'play.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local',
        'gather_facts': False, 'become': False,
        'vars': {'ansible_python_interpreter': sys.executable}, 'tasks': [block]}]))
    def run(check=False):
        return subprocess.run(['ansible-playbook', '-i', 'localhost,', str(play)] + (['--check'] if check else []),
            env={**os.environ, 'PATH': str(tools) + os.pathsep + os.environ['PATH'],
                 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')},
            text=True, capture_output=True, timeout=60)
    result = run(check=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists() and not calls.exists()
    result = run()
    assert result.returncode != 0
    assert not marker.exists()
    fail.unlink()
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.read_text() == hashlib.sha256(POLICY).hexdigest() + '\n'
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls.read_text() == 'call\ncall\n'


def test_admission_precedes_first_mutation_and_remains_active_in_check_mode():
    main = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
    assert main[1]['ansible.builtin.import_tasks'] == 'module-admission.yml'
    admission = yaml.safe_load((ROLE / 'tasks/module-admission.yml').read_text())[0]
    assert admission['check_mode'] is False
    assert admission['tags'] == ['always']
