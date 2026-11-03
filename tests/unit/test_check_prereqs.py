"""Version and interpreter diagnostics do not become behavior acceptance."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def doctor(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('prereqs', ROOT / 'scripts/check-prereqs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / 'mise.toml').write_text('''[tools]
python="3.12"
go="1.27.3"
terraform="1.15.9"
conftest="0.57.0"
gitleaks="8.30.1"
"aqua:prometheus/prometheus"="3.15.1"
zizmor="1.29.0"
''')
    (tmp_path / 'requirements.txt').write_text('ansible-core==2.21.5\nansible-lint==26.10.1\nPyYAML==6.0.3\n')
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module.platform, 'python_version', lambda: '3.12.15')
    monkeypatch.setattr(module.shutil, 'which', lambda name: '/fixture/' + name)
    monkeypatch.setattr(module.importlib.metadata, 'version', lambda name: {
        'ansible-core': '2.21.5', 'ansible-lint': '26.10.1', 'PyYAML': '6.0.3'}[name])
    outputs = {'python3': json.dumps({'version': '3.12.15', 'prefix': sys.prefix}),
               sys.executable: 'ok', 'go': 'go version go1.27.3 darwin/arm64',
               'terraform': '{"terraform_version":"1.15.9"}', 'conftest': 'Conftest: 0.57.0',
               'gitleaks': '8.30.1', 'promtool': 'promtool, version 3.15.1', 'zizmor': 'zizmor 1.29.0',
               'ansible': 'ansible [core 2.21.5]', 'ansible-playbook': 'ansible-playbook [core 2.21.5]',
               'ansible-lint': 'ansible-lint 26.10.1', 'docker': 'linux/aarch64', 'docker-sdk': 'ok'}
    calls = []
    def execute(argv, **options):
        calls.append((argv, options))
        name = 'docker-sdk' if argv[0] == sys.executable and 'from_env' in argv[-1] else argv[0]
        return (0, outputs[name].encode()) if name in outputs else (1, b'synthetic-private-output')
    monkeypatch.setattr(module, 'run_command', execute)
    return module, outputs, calls


@pytest.mark.parametrize('fault', [None, 'python', 'child-environment', 'go', 'terraform', 'missing', 'package', 'invalid-output'])
def test_diagnostics_separate_toolchain_failures_without_raw_output(doctor, monkeypatch, fault):
    module, outputs, calls = doctor
    monkeypatch.setenv('VULTR_API_KEY', 'synthetic-administrative-value')
    if fault == 'python':
        monkeypatch.setattr(module.platform, 'python_version', lambda: '3.15.0')
    if fault == 'child-environment':
        outputs['python3'] = json.dumps({'version': '3.12.15', 'prefix': '/other-interpreter'})
    if fault == 'go': outputs['go'] = 'go version go1.26.0 darwin/arm64'
    if fault == 'terraform': outputs['terraform'] = '{"terraform_version":"1.14.99"}'
    if fault == 'missing': monkeypatch.setattr(module.shutil, 'which', lambda _: None)
    if fault == 'package': monkeypatch.setattr(module.importlib.metadata, 'version', lambda _: '1.0.0')
    if fault == 'invalid-output': outputs['terraform'] = '{"terraform_version":"synthetic-private-output"}'
    result = module.collect()
    assert result['verdict'] == ('ready' if fault is None else 'not-ready')
    assert result['packages_checked'] == 3
    assert 'synthetic-private-output' not in json.dumps(result)
    assert all('VULTR_API_KEY' not in options['environment'] for _, options in calls)
    if fault == 'child-environment':
        assert next(row for row in result['tools'] if row['name'] == 'child-python')['status'] == 'wrong-environment'


@pytest.mark.parametrize('connected', [False, True])
def test_docker_checks_do_not_create_containers_or_claim_image_support(doctor, connected):
    module, outputs, calls = doctor
    if not connected: outputs['docker-sdk'] = 'failed'
    result = module.collect(docker=True)
    assert result['verdict'] == ('ready' if connected else 'not-ready')
    assert next(row for row in result['tools'] if row['name'] == 'python-imports')['status'] == 'ok'
    assert next(row for row in result['tools'] if row['name'] == 'docker-sdk')['status'] == ('ok' if connected else 'unavailable')
    assert 'images, builds and deployments are not verified' in result['scope']
    assert all(not any(arg in argv for arg in ('run', 'pull', 'create', 'build', 'deploy')) for argv, _ in calls)


def test_make_diagnostics_does_not_parse_private_fleet_configuration(tmp_path):
    (tmp_path / 'scripts').mkdir()
    shutil.copy2(ROOT / 'Makefile', tmp_path / 'Makefile')
    marker = tmp_path / 'fleet-loaded'
    (tmp_path / '.fleet.mk').write_text('$(shell touch ' + str(marker) + ')\n')
    (tmp_path / 'scripts/check-prereqs.py').write_text('print("isolated-diagnostic-entry")\n')
    result = subprocess.run(['make', 'check-prereqs'], cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout.strip() == 'isolated-diagnostic-entry'
    assert not marker.exists()


def test_probe_captures_real_child_output_without_forwarding_stderr(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location('real_prereq_probe', ROOT / 'scripts/check-prereqs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    program = tmp_path / 'version-tool'
    program.write_text('#!' + sys.executable + '\nimport sys\nprint("1.2.3")\nprint("synthetic-private-stderr", file=sys.stderr)\n')
    program.chmod(0o700)
    assert module.probe([str(program)]) == '1.2.3\n'
    assert module.probe([str(program)], include_stderr=True) == '1.2.3\nsynthetic-private-stderr\n'
    assert 'synthetic-private-stderr' not in capsys.readouterr().err
