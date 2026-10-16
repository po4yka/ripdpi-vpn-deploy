"""Complete isolated native acceptance; raw diagnostics remain private to the runner."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
SUITES = (
    ('completion', ['tests/native/transport_acceptance/test_completion.py',
                    'tests/unit/test_xhttp_endpoint_contract_native.py',
                    'tests/unit/test_awg_device_binding_native.py',
                    'tests/unit/test_awg_dualstack_native.py']),
    ('lifecycle', ['tests/unit/test_awg_activation_native.py',
                   'tests/native/transport_acceptance/test_awg_lifecycle.py',
                   'tests/unit/test_nginx_transaction_native.py']),
    ('hopping', ['tests/native/transport_acceptance/test_hopping.py']),
    ('compensation', ['tests/unit/test_transport_runtime_acceptance_native.py',
                        'tests/native/transport_acceptance/test_rotation.py']),
)


def run(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, timeout=30, check=True, **kwargs).stdout


def resources():
    """Compare only identities, never configurations or peer keys."""
    tables = json.loads(run(['nft', '-j', 'list', 'tables']))
    return {
        'namespaces': sorted(line.split()[0] for line in run(['ip', 'netns', 'list']).decode().splitlines()),
        'tables': sorted((row['table']['family'], row['table']['name'])
                         for row in tables['nftables'] if 'table' in row),
        'units': sorted(path.name for path in Path('/etc/systemd/system').glob('*.service')),
        'links': sorted(row['ifname'] for row in json.loads(run(['ip', '-j', 'link', 'show']))),
    }


def case_results(path):
    root = ET.parse(path).getroot()
    rows = []
    for case in root.iter('testcase'):
        result = 'passed'
        for tag in ('failure', 'error', 'skipped'):
            if case.find(tag) is not None:
                result = tag
        rows.append({'case': case.get('classname', '') + '.' + case.get('name', ''), 'result': result})
    return rows


def cases(path):
    rows = case_results(path)
    if not rows or any(row['result'] != 'passed' for row in rows):
        raise RuntimeError('selected-case-incomplete')
    return rows


def engines():
    sys.path.insert(0, str(ROOT / 'scripts'))
    sys.path.insert(0, str(ROOT / 'tests/unit'))
    from test_transport_semantics_native import exact_awg_sources
    go, tools = exact_awg_sources()
    result = {}
    for name, path in [('xray', shutil.which('xray')), ('hysteria', shutil.which('hysteria')),
                       ('amneziawg-go', go), ('awg', tools)]:
        data = Path(path).read_bytes()
        if data[:4] != b'\x7fELF':
            raise RuntimeError('engine-not-native')
        result[name] = hashlib.sha256(data).hexdigest()
    # Compare executable bytes against independently checksum-admitted archives.
    import importlib.util
    import zipfile
    spec = importlib.util.spec_from_file_location('acceptance_pins', ROOT / 'tests/integration/transport_runtime_acceptance/fixture.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cache = module.artifacts(ROOT / '.cache/transport-runtime-acceptance')
    with zipfile.ZipFile(cache / 'xray-v26.3.27.zip') as archive:
        if hashlib.sha256(archive.read('xray')).hexdigest() != result['xray']:
            raise RuntimeError('xray-pin-mismatch')
    if hashlib.sha256((cache / 'hysteria-v2.13.0').read_bytes()).hexdigest() != result['hysteria']:
        raise RuntimeError('hysteria-pin-mismatch')
    return result


def main():
    if sys.platform != 'linux' or os.geteuid() != 0 or os.environ.get('TRANSPORT_NATIVE_ISOLATED') != '1':
        raise RuntimeError('isolated-Linux-root-required')
    if not Path('/run/systemd/system').is_dir() or not Path('/dev/net/tun').exists():
        raise RuntimeError('systemd-TUN-required')
    if os.environ.get('PYTEST_ADDOPTS') or os.environ.get('PYTEST_PLUGINS'):
        raise RuntimeError('pytest-selection-overrides-refused')
    sha = run(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    if run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT).strip():
        raise RuntimeError('exact-source-clean-tree-required')
    os.umask(0o077)
    output = Path(os.environ.get('TRANSPORT_NATIVE_EVIDENCE', '/var/tmp/transport-native-evidence.json'))
    if output.exists() or output.is_symlink():
        raise RuntimeError('evidence-path-already-exists')
    evidence = {'source': sha, 'scope': 'isolated-native-source', 'engines': engines(),
                'suites': {}, 'cleanup': False, 'success': False}
    before = resources()
    try:
        with tempfile.TemporaryDirectory(prefix='transport-native-', dir='/var/tmp') as private:
            for name, paths in SUITES:
                report = Path(private) / (name + '.xml')
                with (Path(private) / (name + '.log')).open('wb') as log:
                    result = subprocess.run([sys.executable, '-m', 'pytest', *paths,
                        '--fail-on-skip', '--tb=short', '-q', '--junitxml=' + str(report)],
                        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=2400)
                if result.returncode:
                    # Keep diagnostics on this isolated machine only, with private modes.
                    if report.exists():
                        evidence['suites'][name] = case_results(report)
                        evidence['failure_locations'] = sorted(set(re.findall(r'tests/[A-Za-z0-9_/]+\.py:[0-9]+', report.read_text())))
                    diagnostic = output.with_suffix('.' + name + '.log')
                    shutil.copyfile(Path(private) / (name + '.log'), diagnostic)
                    diagnostic.chmod(0o600)
                    raise RuntimeError('native-suite-failed:' + name)
                evidence['suites'][name] = cases(report)
                print('native-suite-passed:' + name, flush=True)
        evidence['success'] = True
    finally:
        evidence['cleanup'] = resources() == before
        evidence['success'] = evidence['success'] and evidence['cleanup']
        with output.open('x') as stream:
            json.dump(evidence, stream, sort_keys=True, indent=2)
        output.chmod(0o600)
        if not evidence['cleanup']:
            raise RuntimeError('owned-resource-cleanup-unconfirmed')


if __name__ == '__main__':
    main()
