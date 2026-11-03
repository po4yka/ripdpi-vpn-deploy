#!/usr/bin/env python3
"""Check project pins without loading fleet configuration or running builds."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys

try:
    import tomllib
except ImportError:
    print(json.dumps({'schema_version': 1, 'verdict': 'not-ready', 'reason': 'Python 3.12 required'}))
    raise SystemExit(2) from None

from bootstrap_readiness import ReadinessError, run_command

ROOT = Path(__file__).resolve().parents[1]


def probe(argv, *, docker=False, include_stderr=False):
    if shutil.which(argv[0]) is None:
        return None
    allowed = ('PATH', 'HOME', 'LANG', 'LC_ALL')
    if docker:
        allowed += ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH', 'DOCKER_CONFIG')
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    environment.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    stderr = bytearray()
    try:
        code, output = run_command(argv, timeout=5, environment=environment, cwd=ROOT,
                                   capture=True, output_limit=16384, stderr_output=stderr)
    except (ReadinessError, OSError):
        return None
    return (output + (stderr if include_stderr else b'')).decode(errors='replace') if code == 0 else None


def version_result(name, expected, actual, *, prefix=False):
    if not isinstance(actual, str) or not re.fullmatch(r'[0-9][0-9A-Za-z.!+_-]{0,79}', actual):
        actual = None
    matched = isinstance(actual, str) and (actual == expected or prefix and actual.startswith(expected + '.'))
    return {'name': name, 'expected': expected, 'actual': actual,
            'status': 'ok' if matched else 'missing-or-invalid' if actual is None else 'wrong-version'}


def collect(*, docker=False):
    pins = tomllib.loads((ROOT / 'mise.toml').read_text())['tools']
    requirements = re.findall(r'^([A-Za-z0-9_.-]+)==([^\s\\]+)',
                              (ROOT / 'requirements.txt').read_text(), re.MULTILINE)
    if not requirements:
        raise ValueError('missing package pins')
    package_pins = dict(requirements)
    result = [version_result('active-python', pins['python'], platform.python_version(), prefix=True)]
    child = probe(['python3', '-c', 'import json, platform, sys; print(json.dumps({"version": platform.python_version(), "prefix": sys.prefix}))'])
    try:
        child = json.loads(child) if child else {}
        active = version_result('child-python', pins['python'], child.get('version'), prefix=True)
        if active['status'] == 'ok' and child.get('prefix') != sys.prefix:
            active['status'] = 'wrong-environment'
    except (ValueError, TypeError, AttributeError):
        active = version_result('child-python', pins['python'], None, prefix=True)
    result.append(active)
    imports = probe([sys.executable, '-c', 'import yaml, ansible; print("ok")'])
    result.append({'name': 'python-imports', 'status': 'ok' if imports and imports.strip() == 'ok' else 'unavailable'})
    commands = (
        ('go', 'go', ['go', 'version'], r'go version go([0-9.]+)'),
        ('terraform', 'terraform', ['terraform', 'version', '-json'], None),
        ('conftest', 'conftest', ['conftest', '--version'], r'Conftest: ([0-9.]+)'),
        ('gitleaks', 'gitleaks', ['gitleaks', 'version'], r'^v?([0-9.]+)'),
        ('promtool', 'aqua:prometheus/prometheus', ['promtool', '--version'], r'version ([0-9.]+)'),
        ('zizmor', 'zizmor', ['zizmor', '--version'], r'zizmor ([0-9.]+)'),
        ('ansible', 'ansible-core', ['ansible', '--version'], r'ansible \[core ([0-9.]+)\]'),
        ('ansible-playbook', 'ansible-core', ['ansible-playbook', '--version'], r'ansible-playbook \[core ([0-9.]+)\]'),
        ('ansible-lint', 'ansible-lint', ['ansible-lint', '--version'], r'ansible-lint ([0-9.]+)'),
    )
    for name, pin, argv, pattern in commands:
        output, actual = probe(argv, include_stderr=True), None
        if output is not None:
            if pattern is None:
                try:
                    actual = json.loads(output)['terraform_version']
                except (ValueError, KeyError, TypeError):
                    pass
            else:
                match = re.search(pattern, output)
                if match:
                    actual = match[1]
        result.append(version_result(name, pins[pin] if pin in pins else package_pins[pin], actual))
    for name in ('sops', 'age', 'jq', 'ssh'):
        result.append({'name': name, 'status': 'ok' if shutil.which(name) else 'missing'})
    packages = []
    for name, expected in requirements:
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        packages.append(version_result(name, expected, actual))
    if docker:
        daemon = probe(['docker', 'info', '--format', '{{.OSType}}/{{.Architecture}}'], docker=True)
        api = probe([sys.executable, '-c', 'import docker; print("ok" if docker.from_env(timeout=3).ping() else "failed")'],
                    docker=True)
        result.append({'name': 'docker-cli', 'status': 'ok' if daemon and daemon.startswith('linux/') else 'unavailable'})
        result.append({'name': 'docker-sdk', 'status': 'ok' if api and api.strip() == 'ok' else 'unavailable',
                       'connection_hint': 'Select the active Docker context endpoint with DOCKER_HOST if needed.'})
    issues = [entry for entry in packages if entry['status'] != 'ok']
    return {'schema_version': 1,
            'verdict': 'ready' if not issues and all(entry['status'] == 'ok' for entry in result) else 'not-ready',
            'tools': result, 'packages_checked': len(packages), 'package_issues': issues,
            'scope': 'tool versions, Python package metadata and core imports; images, builds and deployments are not verified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker', action='store_true', help='Also check the existing Linux daemon and Python SDK.')
    args = parser.parse_args()
    try:
        result = collect(docker=args.docker)
    except (OSError, ValueError, KeyError, TypeError):
        result = {'schema_version': 1, 'verdict': 'not-ready', 'reason': 'invalid project toolchain configuration'}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['verdict'] == 'ready' else 2


if __name__ == '__main__':
    raise SystemExit(main())
