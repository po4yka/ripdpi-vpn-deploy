"""Real SOPS proof of the CI age identity revocation in docs/how-to/ci-identities.md."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def keygen(path: Path) -> str:
    subprocess.run(['age-keygen', '-o', str(path)], capture_output=True, check=True)
    return subprocess.check_output(['age-keygen', '-y', str(path)], text=True).strip()


def sops(*args: str, cwd: Path, key: Path) -> subprocess.CompletedProcess[bytes]:
    env = {key_: value for key_, value in os.environ.items() if key_ != 'SOPS_CONFIG'}
    return subprocess.run(['sops', *args], cwd=cwd, capture_output=True, check=False,
                          env={**env, 'SOPS_AGE_KEY_FILE': str(key)})


def with_stanza(document: Path, stanza: dict, target: Path) -> Path:
    data = json.loads(document.read_text())
    data['sops']['age'].append(stanza)
    target.write_text(json.dumps(data))
    return target


def test_updatekeys_and_rotate_lock_out_the_ci_identity_and_its_retained_data_key(tmp_path):
    operator_key, ci_key = tmp_path / 'operator.key', tmp_path / 'ci.key'
    operator, ci = keygen(operator_key), keygen(ci_key)
    config = tmp_path / '.sops.yaml'
    config.write_text(f'creation_rules:\n  - path_regex: \\.sops\\.json$\n    age: {operator},{ci}\n')
    document = tmp_path / 'deploy.secrets.sops.json'
    document.write_text('{"token": "synthetic-value"}')
    assert sops('--encrypt', '-i', document.name, cwd=tmp_path, key=operator_key).returncode == 0
    # The retained pre-revocation fixture: the CI stanza that wraps the original data key.
    retained = next(entry for entry in json.loads(document.read_text())['sops']['age'] if entry['recipient'] == ci)
    assert sops('--decrypt', document.name, cwd=tmp_path, key=ci_key).returncode == 0

    config.write_text(f'creation_rules:\n  - path_regex: \\.sops\\.json$\n    age: {operator}\n')
    assert sops('updatekeys', '-y', document.name, cwd=tmp_path, key=operator_key).returncode == 0
    assert sops('--decrypt', document.name, cwd=tmp_path, key=ci_key).returncode != 0
    # updatekeys alone keeps the data key, so the retained stanza still opens the document.
    spliced = with_stanza(document, retained, tmp_path / 'before-rotate.sops.json')
    assert json.loads(sops('--decrypt', spliced.name, cwd=tmp_path, key=ci_key).stdout) == {'token': 'synthetic-value'}

    assert sops('rotate', '-i', document.name, cwd=tmp_path, key=operator_key).returncode == 0
    assert [entry['recipient'] for entry in json.loads(document.read_text())['sops']['age']] == [operator]
    spliced = with_stanza(document, retained, tmp_path / 'after-rotate.sops.json')
    assert sops('--decrypt', spliced.name, cwd=tmp_path, key=ci_key).returncode != 0
    operator_view = sops('--decrypt', document.name, cwd=tmp_path, key=operator_key)
    assert json.loads(operator_view.stdout) == {'token': 'synthetic-value'}
