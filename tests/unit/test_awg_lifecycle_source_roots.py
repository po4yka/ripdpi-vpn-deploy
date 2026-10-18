"""Real Git/receipt admission with synthetic source; no AWG or compiler runs."""

import copy
import hashlib
import importlib.util
from pathlib import Path
import shutil
import sys

import pytest

from test_awg_source_correction import correction

ROOT = Path(__file__).resolve().parents[2]
AREA = ROOT / 'tests/integration/awg_source_candidate'


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source_lab(correction, tmp_path, monkeypatch):
    _helper, original, commit, assets, _manifest = correction
    directory = tmp_path / 'lab'
    directory.mkdir()
    shutil.copytree(assets, directory / 'awg-source-correction')
    shutil.copyfile(AREA / 'sources.json', directory / 'sources.json')
    apt = directory / 'ubuntu.sources'
    shutil.copyfile(AREA / 'ubuntu.sources', apt)
    # Relocate only container-owned absolute inputs for this portable test.
    source = (AREA / 'acceptance.py').read_text()
    source = source.replace('ROOT = Path("/lab")', f'ROOT = Path({str(directory)!r})')
    source = source.replace('"/etc/apt/sources.list.d/ubuntu.sources"', repr(str(apt)))
    relocated = directory / 'acceptance.py'
    relocated.write_text(source)
    monkeypatch.syspath_prepend(str(ROOT / 'ansible/roles/runtime-release/files'))
    monkeypatch.syspath_prepend(str(AREA))
    module = load_module(relocated, 'relocated_awg_lifecycle_acceptance')
    canonical = tmp_path / 'canonical-sources'
    build = load_module(AREA / 'corrected_build.py', 'lifecycle_corrected_build')
    receipts = {}
    for pair in ('baseline', 'candidate'):
        selected = canonical / pair / 'go'
        shutil.copytree(original, selected)
        build.prepare(selected, commit, directory / 'awg-source-correction')
        # These executable bytes exercise receipt identity only, never AWG.
        shutil.copyfile(sys.executable, selected / 'amneziawg-go')
        (selected / 'amneziawg-go').chmod(0o755)
        receipts[pair] = build.publish(selected, commit, directory / 'awg-source-correction')
        module.PINS[pair]['go']['commit'] = commit
    return module, canonical, receipts


@pytest.mark.parametrize('pair', ['baseline', 'candidate'])
def test_descriptor_admits_explicit_canonical_source_and_exact_receipt(source_lab, pair):
    module, canonical, receipts = source_lab
    module.SOURCE_ROOT = canonical
    before = copy.deepcopy(module.PINS[pair])

    descriptor = module.descriptor(pair)

    assert descriptor['source']['pair'] == before
    assert descriptor['source']['patches'] == receipts[pair]['correction']
    assert descriptor['source']['package_sources_sha256'] == hashlib.sha256(
        (module.ROOT / 'ubuntu.sources').read_bytes()).hexdigest()
    assert [row['argv'][3] for row in descriptor['steps']] == [
        str(canonical / pair / 'go/amneziawg-go'),
        str(canonical / pair / 'tools/src/wg'),
        str(canonical / pair / 'tools/src/wg-quick/linux.bash'),
    ]
    assert [row['path'] for row in descriptor['outputs']] == [
        '/usr/local/lib/awg-candidate/' + name for name in ('amneziawg-go', 'awg', 'awg-quick')]
    assert module.PINS[pair] == before


def test_source_alias_still_refuses_without_receipt_or_source_mutation(source_lab, tmp_path):
    module, canonical, _receipts = source_lab
    alias = tmp_path / 'alias'
    alias.symlink_to(canonical, target_is_directory=True)
    module.SOURCE_ROOT = alias
    receipt = next((canonical / 'baseline/go/.ripdpi-build').glob('*/receipt.json'))
    before = receipt.read_bytes()

    with pytest.raises(ValueError, match='unsafe-source-directory'):
        module.descriptor('baseline')

    assert receipt.read_bytes() == before
    assert alias.is_symlink()


def test_wrong_source_pin_still_refuses_the_canonical_tree(source_lab):
    module, canonical, _receipts = source_lab
    module.SOURCE_ROOT = canonical
    module.PINS['baseline']['go']['commit'] = 'f' * 40

    with pytest.raises(ValueError, match='unsupported-commit'):
        module.descriptor('baseline')


def test_default_source_root_and_pair_boundary(source_lab):
    module, _canonical, _receipts = source_lab
    assert module.SOURCE_ROOT == Path('/opt')
    assert module.source('baseline') == Path('/opt/baseline')
    assert module.source('candidate') == Path('/opt/candidate')
    with pytest.raises(ValueError, match='source-pair'):
        module.source('../unowned')
