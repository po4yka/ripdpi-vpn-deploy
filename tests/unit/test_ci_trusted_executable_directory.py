"""Execute the disposable CI directory admission with owned temporary paths."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
STEP = 'Admit trusted executable directory for disposable CI'


def setup_steps():
    action = yaml.safe_load((ROOT / '.github/actions/setup-disposable-ci/action.yml').read_text())
    return action['runs']['steps']


def admission_script():
    step = next((step for step in setup_steps() if step.get('name') == STEP), None)
    assert step is not None, 'trusted directory admission step missing'
    return step['run'].split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]


def execute(path, *, expected_uid=None):
    source = admission_script()
    assert source.count("TRUSTED_PATH = '/usr/local/bin'") == 1
    assert source.count('TRUSTED_UID = 0') == 1
    source = source.replace("TRUSTED_PATH = '/usr/local/bin'", f'TRUSTED_PATH = {str(path)!r}')
    source = source.replace('TRUSTED_UID = 0', f'TRUSTED_UID = {os.getuid() if expected_uid is None else expected_uid}')
    return subprocess.run([sys.executable, '-Es', '-'], input=source, capture_output=True, text=True, timeout=10)


def layout(root):
    leaf = root / 'usr/local/bin'
    leaf.mkdir(parents=True)
    leaf.chmod(0o777)
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
    parents = {path: stat.S_IMODE(path.stat().st_mode) for path in (leaf.parent, leaf.parent.parent)}
    for _ in range(2):
        result = execute(leaf)
        assert result.returncode == 0, result.stderr
        assert leaf.stat().st_ino == inode
        assert stat.S_IMODE(leaf.stat().st_mode) == 0o755
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
