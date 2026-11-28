"""Schema readers may name their sentinel; runtime placeholders still refuse."""

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('placeholder_scan', ROOT / 'scripts/pre-commit-placeholder-scan.py')
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


@pytest.mark.parametrize('name,expected', [
    ('scripts/check-secrets-coverage.py', 0),
    # The workflow reads real pins now; a placeholder there could only make a job skip.
    ('.github/workflows/reproducible-build.yml', 1),
    ('.github/workflows/unselected.yml', 1),
    ('ansible/roles/hysteria/templates/unselected.j2', 1),
])
@pytest.mark.parametrize("words", [("REPLACE", "WITH"), ("Replace", "with")])
def test_only_the_declared_schema_reader_is_exempt(tmp_path, monkeypatch, name, expected, words):
    monkeypatch.chdir(tmp_path)
    path = Path(name)
    path.parent.mkdir(parents=True)
    path.write_text('_'.join((*words, 'TEST_SENTINEL')))
    assert scanner.main([name]) == expected
