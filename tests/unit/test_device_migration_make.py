"""Make passes literal migration arguments without loading operator configuration."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def checkout(tmp_path):
    shutil.copy2(ROOT / 'Makefile', tmp_path / 'Makefile')
    (tmp_path / '.fleet.mk').write_text('$(error operator configuration must not be loaded)\n')
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts/device-migration.py').write_text(
        'import json,pathlib,sys\npathlib.Path("arguments.json").write_text(json.dumps(sys.argv[1:]))\n')
    return tmp_path


def invoke(checkout, *args):
    environment = {key: value for key, value in os.environ.items()
                   if key not in {'MAKEFILES', 'MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS'}}
    return subprocess.run(['make', 'device-migration', *args], cwd=checkout, env=environment,
                          capture_output=True, text=True, timeout=10, check=False)


@pytest.mark.parametrize('action', ['plan', 'prepare', 'publish', 'status', 'receipt', 'attest', 'ready', 'rollback'])
def test_all_migration_actions_dispatch_without_fleet_configuration(checkout, action):
    result = invoke(checkout, 'ACTION=' + action, 'DEVICE_MIGRATION_PLAN=/private/a plan.json')
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((checkout / 'arguments.json').read_text()) == [action, '--plan=/private/a plan.json']


def test_arguments_remain_literal_even_with_make_and_shell_syntax(checkout):
    marker = checkout / 'injected'
    reason = f'literal $(shell touch {marker}) $(touch {marker}); touch {marker}'
    result = invoke(checkout, 'ACTION=attest', 'DEVICE_MIGRATION_PLAN=/private/plan;literal.json',
                    'DEVICE_MIGRATION_APPROVAL=' + 'a' * 64, 'MIGRATION_RECEIPT=/private/a receipt.json',
                    'MIGRATION_CLIENT=-device', 'MIGRATION_REASON=' + reason)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
    assert json.loads((checkout / 'arguments.json').read_text()) == [
        'attest', '--plan=/private/plan;literal.json', '--approve=' + 'a' * 64,
        '--receipt=/private/a receipt.json', '--client=-device', '--reason=' + reason]


@pytest.mark.parametrize('args', [[], ['ACTION=status'], ['ACTION=invalid', 'DEVICE_MIGRATION_PLAN=/private/plan'],
    ['ACTION=status', 'DEVICE_MIGRATION_PLAN=/private/plan', 'help']])
def test_missing_or_mixed_actions_do_not_reach_controller(checkout, args):
    result = invoke(checkout, *args)
    assert result.returncode != 0 and not (checkout / 'arguments.json').exists()


def test_blue_green_make_preserves_literal_migration_inputs(checkout):
    (checkout / '.fleet.mk').write_text('')
    marker = checkout / 'unexpected'
    (checkout / 'scripts/blue-green.sh').write_text('#!/usr/bin/env python3\nimport json,os,pathlib\n'
        'pathlib.Path("arguments.json").write_text(json.dumps({key:os.environ[key] for key in '
        '["BLUE_ENV","GREEN_ENV","GREEN_SOPS_FILE","DEVICE_MIGRATION_PLAN","DEVICE_MIGRATION_APPROVAL"]}))\n')
    (checkout / 'scripts/blue-green.sh').chmod(0o700)
    path = f'/private/$(shell touch {marker})/plan;literal.json'
    result = subprocess.run(['make', 'blue-green', 'BLUE_ENV=source', 'GREEN_ENV=target',
        'GREEN_SOPS_FILE=/private/separate target.sops.yaml', 'DEVICE_MIGRATION_PLAN=' + path,
        'DEVICE_MIGRATION_APPROVAL=' + 'a' * 64], cwd=checkout, capture_output=True, text=True, timeout=10, check=False,
        env={key: value for key, value in os.environ.items() if key not in {'MAKEFILES', 'MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS'}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
    assert json.loads((checkout / 'arguments.json').read_text()) == {
        'BLUE_ENV': 'source', 'GREEN_ENV': 'target', 'GREEN_SOPS_FILE': '/private/separate target.sops.yaml',
        'DEVICE_MIGRATION_PLAN': path, 'DEVICE_MIGRATION_APPROVAL': 'a' * 64}
