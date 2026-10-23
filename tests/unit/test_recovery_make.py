"""Canonical recovery Make dispatch preserves literal private selectors."""
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
    (tmp_path / '.fleet.mk').write_text('$(error no operator configuration before admission)\n')
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts/recovery.py').write_text('import json,pathlib,sys\npathlib.Path("argv.json").write_text(json.dumps(sys.argv[1:]))\n')
    return tmp_path


def invoke(checkout, *args):
    return subprocess.run(['make', 'recovery', *args], cwd=checkout, capture_output=True, text=True, timeout=10, check=False,
                          env={key:value for key,value in os.environ.items() if key not in {'MAKEFLAGS','MAKEFILES','GNUMAKEFLAGS','MFLAGS'}})


@pytest.mark.parametrize('action', ['run','resume','status'])
def test_make_forwards_literal_manifest_without_fleet_inputs(checkout, action):
    marker = checkout / 'unexpected'
    value = f'/private/$(shell touch {marker})/plan;literal.json'
    result = invoke(checkout, 'ACTION='+action, 'RECOVERY_MANIFEST='+value, 'RECOVERY_APPROVAL='+'a'*64)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
    assert json.loads((checkout / 'argv.json').read_text()) == [action, '--manifest='+value, '--approve='+'a'*64]


@pytest.mark.parametrize('args', [[],['ACTION=run'],['ACTION=unknown','RECOVERY_MANIFEST=/private/a'],
                                   ['ACTION=run','RECOVERY_MANIFEST=/private/a','help']])
def test_make_refuses_missing_or_mixed_execution(checkout, args):
    result = invoke(checkout, *args)
    assert result.returncode != 0 and not (checkout / 'argv.json').exists()
