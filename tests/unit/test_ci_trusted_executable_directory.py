"""Execute the disposable CI directory admission with owned temporary paths."""
from __future__ import annotations

import os
import inspect
from pathlib import Path
import stat
import subprocess
import sys

import pytest
import yaml

from test_awg_activation_native import prepare_native_acquisition

ROOT = Path(__file__).resolve().parents[2]
STEP = 'Admit trusted executable directories for disposable CI'


def setup_steps():
    action = yaml.safe_load((ROOT / '.github/actions/setup-disposable-ci/action.yml').read_text())
    return action['runs']['steps']


def admission_script():
    step = next((step for step in setup_steps() if step.get('name') == STEP), None)
    assert step is not None, 'trusted directory admission step missing'
    return step['run'].split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]


def execute(path, *, expected_uid=None):
    source = admission_script()
    original = "TRUSTED_PATHS = ('/usr/local/bin', '/opt')"
    assert source.count(original) == 1
    assert source.count('TRUSTED_UID = 0') == 1
    paths = (str(path), str(path.parents[2] / 'opt'))
    source = source.replace(original, f'TRUSTED_PATHS = {paths!r}')
    source = source.replace('TRUSTED_UID = 0', f'TRUSTED_UID = {os.getuid() if expected_uid is None else expected_uid}')
    return subprocess.run([sys.executable, '-Es', '-'], input=source, capture_output=True, text=True, timeout=10)


def layout(root):
    leaf = root / 'usr/local/bin'
    leaf.mkdir(parents=True)
    leaf.chmod(0o777)
    (root / 'opt').mkdir(mode=0o777)
    (root / 'opt').chmod(0o777)
    return leaf


def test_admission_precedes_verified_runtime_and_client_installation():
    steps = setup_steps()
    names = [step.get('name') for step in steps]
    assert STEP in names, 'trusted directory admission step missing'
    index = names.index(STEP)
    assert index < next(i for i, step in enumerate(steps) if step.get('uses') == './.github/actions/install-xray')
    assert index < names.index('Install verified deployment clients')


def test_leaf_normalization_and_repetition_preserve_existing_content(private_authority_path):
    leaf = layout(private_authority_path)
    child = leaf / 'existing'
    child.write_bytes(b'owned existing executable bytes')
    child.chmod(0o751)
    before = child.stat().st_ino, child.stat().st_mode, child.read_bytes()
    inode = leaf.stat().st_ino
    opt = private_authority_path / 'opt'
    opt_inode = opt.stat().st_ino
    opt_child = opt / 'existing'
    opt_child.write_bytes(b'preserve acquisition content')
    opt_before = opt_child.stat().st_ino, opt_child.stat().st_mode, opt_child.read_bytes()
    parents = {path: stat.S_IMODE(path.stat().st_mode) for path in (leaf.parent, leaf.parent.parent)}
    for _ in range(2):
        result = execute(leaf)
        assert result.returncode == 0, result.stderr
        assert leaf.stat().st_ino == inode
        assert stat.S_IMODE(leaf.stat().st_mode) == 0o755
        assert opt.stat().st_ino == opt_inode and stat.S_IMODE(opt.stat().st_mode) == 0o755
        assert (opt_child.stat().st_ino, opt_child.stat().st_mode, opt_child.read_bytes()) == opt_before
        assert (child.stat().st_ino, child.stat().st_mode, child.read_bytes()) == before
        assert {path: stat.S_IMODE(path.stat().st_mode) for path in parents} == parents


@pytest.mark.parametrize('level,mode', [(1, 0o775), (2, 0o777)])
def test_unsafe_ancestor_refuses_before_leaf_mutation(private_authority_path, level, mode):
    leaf = layout(private_authority_path)
    ancestor = leaf.parents[level - 1]
    ancestor.chmod(mode)
    result = execute(leaf)
    assert result.returncode != 0
    assert stat.S_IMODE(leaf.stat().st_mode) == 0o777
    assert stat.S_IMODE(ancestor.stat().st_mode) == mode


@pytest.mark.parametrize('level', [0, 1, 2])
def test_symlink_at_leaf_or_ancestor_refuses(private_authority_path, level):
    leaf = layout(private_authority_path)
    selected = leaf if level == 0 else leaf.parents[level - 1]
    target = private_authority_path / 'relocated'
    selected.rename(target)
    selected.symlink_to(target, target_is_directory=True)
    result = execute(leaf)
    assert result.returncode != 0
    assert selected.is_symlink()
    assert stat.S_IMODE(leaf.stat().st_mode) == 0o777


def test_wrong_owner_authority_refuses_without_chmod(private_authority_path):
    leaf = layout(private_authority_path)
    result = execute(leaf, expected_uid=os.getuid() + 1)
    assert result.returncode != 0
    assert stat.S_IMODE(leaf.stat().st_mode) == 0o777


@pytest.mark.parametrize('kind', ['missing', 'file'])
def test_missing_or_regular_file_leaf_refuses(private_authority_path, kind):
    leaf = layout(private_authority_path)
    leaf.rmdir()
    if kind == 'file':
        leaf.write_bytes(b'preserve this regular file')
        leaf.chmod(0o777)
    result = execute(leaf)
    assert result.returncode != 0
    if kind == 'file':
        assert leaf.read_bytes() == b'preserve this regular file'
        assert stat.S_IMODE(leaf.stat().st_mode) == 0o777
    else:
        assert not os.path.lexists(leaf)


def test_second_admitted_leaf_refuses_symlink_without_touching_target(private_authority_path):
    leaf = layout(private_authority_path)
    opt = private_authority_path / 'opt'
    target = private_authority_path / 'relocated-opt'
    opt.rename(target)
    opt.symlink_to(target, target_is_directory=True)
    result = execute(leaf)
    assert result.returncode != 0
    assert opt.is_symlink() and stat.S_IMODE(target.stat().st_mode) == 0o777


@pytest.mark.parametrize('mask', [0o000, 0o777])
def test_fresh_acquisition_creation_has_explicit_modes_under_actual_umask(private_authority_path, mask):
    root = private_authority_path / 'acquisition'
    source = ('from pathlib import Path\nimport os\n' + inspect.getsource(prepare_native_acquisition)
              + f'\nos.umask({mask})\nprepare_native_acquisition(Path({str(root)!r}))\n')
    result = subprocess.run([sys.executable, '-Es', '-'], input=source, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(root.stat().st_mode) == stat.S_IMODE((root / 'releases').stat().st_mode) == 0o755


def test_acquisition_creation_refuses_existing_authority_without_chmod(private_authority_path):
    root = private_authority_path / 'existing'
    root.mkdir(mode=0o777)
    root.chmod(0o777)
    child = root / 'foreign'
    child.write_bytes(b'preserve existing authority')
    before = child.stat().st_ino, child.stat().st_mode, child.read_bytes()
    with pytest.raises(FileExistsError):
        prepare_native_acquisition(root)
    assert stat.S_IMODE(root.stat().st_mode) == 0o777
    assert (child.stat().st_ino, child.stat().st_mode, child.read_bytes()) == before
    assert not (root / 'releases').exists()
