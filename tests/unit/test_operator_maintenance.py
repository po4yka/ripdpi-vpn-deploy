"""Real cryptographic, archive and child-process tests for operator maintenance."""
import base64
import hashlib
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    import operator_private
    import operator_release
    import operator_kit
    spec = importlib.util.spec_from_file_location('maintenance_entry', ROOT / 'scripts/operator-maintenance.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    return operator_private, operator_release, operator_kit, entry


def private(path, data):
    path.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())
    path.chmod(0o600)
    return path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def release_plan(tmp_path, archive, members, *, version="2.0", url="https://example.com/2.0/app.tar", arch="amd64"):
    descriptor = {"version": version, "urls": {arch: url}, "sha256": {arch: digest(archive.read_bytes())},
                  "archive_members": {arch: members[0]}}
    if len(members) > 1: descriptor["promtool_archive_members"] = {arch: members[1]}
    source = private(tmp_path / 'prepared.json', {"component": descriptor})
    plan = {"schema_version": 1, "releases": [{"source": str(source), "source_sha256": digest(source.read_bytes()),
             "pointer": "/component", "archives": {arch: str(archive)}}]}
    return plan, descriptor, source


def save_release(plan, descriptor, source):
    private(source, {"component": descriptor})
    plan['releases'][0]['source_sha256'] = digest(source.read_bytes())


@pytest.fixture
def keys(tmp_path):
    identity = tmp_path / 'identity'
    subprocess.run(['age-keygen', '-o', str(identity)], capture_output=True, check=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    return identity, recipient


def decrypt(path, identity):
    return subprocess.check_output(['age', '-d', '-i', str(identity), str(path)])


@pytest.mark.parametrize('kind', ['tar', 'zip'])
def test_release_reads_actual_archives_and_refuses_stale_member(modules, tmp_path, kind):
    common, releases, _, _ = modules
    path = tmp_path / ('release.' + kind)
    name = 'app-2.0.linux-amd64/app'
    if kind == 'tar':
        with tarfile.open(path, 'w:gz') as archive:
            item = tarfile.TarInfo(name); item.size = 4
            archive.addfile(item, io.BytesIO(b'app!'))
    else:
        with zipfile.ZipFile(path, 'w') as archive: archive.writestr(name, b'app!')
    plan, descriptor, source = release_plan(tmp_path, path, [name])
    assert releases.check(plan)['architectures'] == 1
    descriptor['promtool_archive_members'] = {'amd64': 'app-1.0.linux-amd64/tool'}
    save_release(plan, descriptor, source)
    with pytest.raises(common.Refusal, match='archive-member-mismatch'): releases.check(plan)
    descriptor['sha256']['amd64'] = '0' * 64
    save_release(plan, descriptor, source)
    with pytest.raises(common.Refusal, match='checksum'): releases.check(plan)


def test_release_rejects_links_traversal_and_duplicate_members(modules, tmp_path):
    common, releases, _, _ = modules
    for name, link in [('../outside', False), ('safe', True), ('safe', False)]:
        path = tmp_path / 'unsafe.tar'
        with tarfile.open(path, 'w') as archive:
            item = tarfile.TarInfo(name)
            if link: item.type = tarfile.SYMTYPE; item.linkname = 'other'
            archive.addfile(item)
            if name == 'safe' and not link: archive.addfile(item)
        plan, _, _ = release_plan(tmp_path, path, ['safe'], version='2', arch='arm64', url='https://example.com/2/arm64.tar')
        with pytest.raises(common.Refusal): releases.check(plan)


def test_apt_checks_real_command_results_and_selected_preference(modules, tmp_path, monkeypatch):
    common, releases, _, _ = modules
    pin = tmp_path / 'pin'
    pin.write_text('Package: tailscale\nPin: version 2.0\nPin-Priority: 1001\n')
    calls = []
    def boundary(argv, **kwargs):
        calls.append(argv)
        return b'2.0' if argv[0] == 'dpkg-query' else b'  Installed: 2.0\n  Candidate: 1.0\n'
    monkeypatch.setattr(releases, 'checked', boundary)
    with pytest.raises(common.Refusal, match='package-version-mismatch'):
        releases.check_apt({'package': 'tailscale', 'version': '2.0', 'preference': str(pin)})
    assert calls == [['dpkg-query', '-W', '-f=${Version}', 'tailscale'], ['apt-cache', 'policy', 'tailscale']]
    monkeypatch.setattr(releases, 'checked', lambda argv, **kw: b'2.0' if argv[0] == 'dpkg-query' else b' Installed: 2.0\n Candidate: 2.0\n')
    releases.check_apt({'package': 'tailscale', 'version': '2.0', 'preference': str(pin)})
    answer = releases.check({'schema_version': 1, 'apt': {
        'package': 'tailscale', 'version': '2.0', 'preference': str(pin)}})
    assert answer == {'result': 'release-inputs-verified', 'architectures': 0,
                      'package_policy_checked': True, 'runtime_version_qualified': False}


def test_diagnostic_failure_is_encrypted_and_preserves_exit(modules, tmp_path, keys, monkeypatch):
    _, _, _, entry = modules
    identity, recipient = keys
    output = tmp_path / 'diagnostic.age'
    monkeypatch.setenv('UNRELATED_CLOUD_TOKEN', 'should-not-enter-child')
    plan = {'schema_version': 1, 'argv': [sys.executable, '-c',
            'import os,sys; assert "UNRELATED_CLOUD_TOKEN" not in os.environ; print("private-stdout"); print("private-stderr",file=sys.stderr);sys.exit(7)'],
            'recipient': recipient, 'output': str(output), 'timeout': 5, 'max_bytes': 4096}
    answer, code = entry.diagnostics(plan)
    assert code == 7 and answer['capture'] == 'complete'
    payload = json.loads(decrypt(output, identity))
    assert payload['exit_code'] == 7
    assert base64.b64decode(payload['stdout_base64']) == b'private-stdout\n'
    assert base64.b64decode(payload['stderr_base64']) == b'private-stderr\n'
    assert b'private-stdout' not in output.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('limit,command,expected', [(128, 'print("x"*10000)', 'output-limit'),
                                                  (4096, 'import time; print("partial",flush=True);time.sleep(20)', 'timeout')])
def test_capture_limits_retain_partial_encrypted_output(modules, tmp_path, keys, limit, command, expected):
    _, _, _, entry = modules
    identity, recipient = keys
    output = tmp_path / 'limited.age'
    answer, code = entry.diagnostics({'schema_version': 1, 'argv': [sys.executable, '-c', command],
        'recipient': recipient, 'output': str(output), 'timeout': 1, 'max_bytes': limit})
    payload = json.loads(decrypt(output, identity))
    assert answer['capture'] == expected and code in (124, 125)
    assert payload['capture'] == expected and base64.b64decode(payload['stdout_base64'])


def test_closed_descriptor_descendant_is_reclaimed_before_success(modules):
    common, _, _, _ = modules
    script = 'import os,time; p=os.fork();\nif p==0:\n os.close(0);os.close(1);os.close(2);time.sleep(20)\nelse:\n print(p,flush=True)'
    result = common.capture([sys.executable, '-c', script], timeout=3)
    assert result['capture'] == 'complete' and result['exit_code'] == 0
    child = int(result['stdout'])
    state = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', str(child)], capture_output=True).stdout.strip()
    assert not state or state.startswith(b'Z')


@pytest.fixture
def kit(modules, tmp_path, keys):
    common, _, _, _ = modules
    identity, recipient = keys
    source = private(tmp_path / 'active.sops.yaml', b'protected-example-material')
    catalog = private(tmp_path / 'catalog.json', {'current': str(source)})
    return {'schema_version': 1, 'catalog': str(catalog), 'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'max_age_seconds': 3600, 'entries': [{'name': 'config/active.sops.yaml', 'pointer': '/current',
            'kind': 'secrets', 'sha256': digest(source.read_bytes())}],
            'backup': {'ciphertext': str(tmp_path / 'kit.age'), 'recipient': recipient, 'identity': str(identity)}}


def test_kit_seal_roundtrip_and_downloaded_b2_copy(modules, kit, keys, tmp_path, monkeypatch):
    common, _, kits, _ = modules
    receipt = kits.seal(kit)
    archive = Path(kit['backup']['ciphertext'])
    expected, _ = kits.selected(kit)
    kits.verify_payload(decrypt(archive, keys[0]), expected)
    binary = private(tmp_path / 'rclone', b'external-transport-boundary')
    binary.chmod(0o700)
    kit['backup'].update(sha256=receipt['ciphertext_sha256'], bucket='test-bucket', object='operator/current.age',
                          rclone=str(binary), rclone_sha256=digest(binary.read_bytes()))
    monkeypatch.setenv('RCLONE_B2_ACCOUNT', 'test-account'); monkeypatch.setenv('RCLONE_B2_KEY', 'test-key')
    original = kits.checked
    def b2(argv, **kwargs):
        if argv[0] == str(binary):
            assert argv[1:3] == ['cat', ':b2:test-bucket/operator/current.age']
            assert set(kwargs['env']) == {'PATH', 'LANG', 'LC_ALL', 'TZ', 'RCLONE_B2_ACCOUNT', 'RCLONE_B2_KEY'}
            return archive.read_bytes()
        return original(argv, **kwargs)
    monkeypatch.setattr(kits, 'checked', b2)
    assert kits.verify_backup(kit)['result'] == 'downloaded-kit-manifest-verified'
    wrong = tmp_path / 'wrong-identity'
    subprocess.run(['age-keygen', '-o', str(wrong)], capture_output=True, check=True)
    kit['backup']['identity'] = str(wrong)
    with pytest.raises(common.Refusal, match='command-failed'): kits.verify_backup(kit)
    kit['backup']['identity'] = str(keys[0])
    def corrupt(argv, **kwargs):
        return archive.read_bytes() + b'corrupt' if argv[0] == str(binary) else original(argv, **kwargs)
    monkeypatch.setattr(kits, 'checked', corrupt)
    with pytest.raises(common.Refusal, match='downloaded-ciphertext-mismatch'): kits.verify_backup(kit)
    monkeypatch.setattr(kits, 'checked', b2)
    source = Path(json.loads(Path(kit['catalog']).read_bytes())['current'])
    def changed(argv, **kwargs):
        result = b2(argv, **kwargs)
        if argv[0] == str(binary): source.write_bytes(b'rotated')
        return result
    monkeypatch.setattr(kits, 'checked', changed)
    with pytest.raises(common.Refusal, match='kit-file-mismatch'): kits.verify_backup(kit)


@pytest.mark.parametrize('change', ['hash', 'pointer', 'mode', 'stale', 'symlink', 'hardlink', 'key'])
def test_kit_refuses_invalid_current_authority(modules, kit, tmp_path, change):
    common, _, kits, _ = modules
    source = Path(json.loads(Path(kit['catalog']).read_bytes())['current'])
    if change == 'hash': kit['entries'][0]['sha256'] = '0' * 64
    if change == 'pointer': kit['entries'][0]['pointer'] = '/missing'
    if change == 'mode': source.chmod(0o644)
    if change == 'stale': kit['observed_at'] = '2000-01-01T00:00:00Z'
    if change == 'symlink':
        alias = tmp_path / 'alias'; alias.symlink_to(source)
        private(Path(kit['catalog']), {'current': str(alias)})
    if change == 'hardlink':
        alias = tmp_path / 'hard-alias'; os.link(source, alias)
        private(Path(kit['catalog']), {'current': str(alias)})
    if change == 'key':
        private(Path(kit['catalog']), {'current': kit['backup']['identity']})
        kit['entries'][0]['sha256'] = digest(Path(kit['backup']['identity']).read_bytes())
    with pytest.raises((common.Refusal, KeyError)): kits.check(kit)


def test_cli_refusal_never_prints_secret_or_starts_unapproved_command(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/operator-maintenance.py'), 'operator-diagnostics'],
                            env={**os.environ, 'OPERATOR_MAINTENANCE_PLAN': '/private-secret-marker'}, capture_output=True)
    assert result.returncode == 2
    assert b'command-authority-required' in result.stderr and b'private-secret-marker' not in result.stderr


def test_bad_recipient_and_existing_output_do_not_start_command(modules, tmp_path):
    common, _, _, entry = modules
    marker = tmp_path / 'started'
    plan = {'schema_version': 1, 'argv': [sys.executable, '-c', f'open({str(marker)!r},"w").write("started")'],
            'recipient': 'invalid-recipient', 'output': str(tmp_path / 'diag.age'), 'timeout': 2, 'max_bytes': 1024}
    with pytest.raises(common.Refusal): entry.diagnostics(plan)
    assert not marker.exists() and not Path(plan['output']).exists()
    private(Path(plan['output']), b'existing-ciphertext')
    with pytest.raises(FileExistsError): entry.diagnostics(plan)
    assert Path(plan['output']).read_bytes() == b'existing-ciphertext' and not marker.exists()


def test_encryption_failure_does_not_return_child_success(modules, tmp_path, keys, monkeypatch):
    common, _, _, entry = modules
    original, calls = entry.checked, []
    def fail_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2: raise common.Refusal('command-failed')
        return original(*args, **kwargs)
    monkeypatch.setattr(entry, 'checked', fail_second)
    output = tmp_path / 'failed.age'
    with pytest.raises(common.Refusal):
        entry.diagnostics({'schema_version': 1, 'argv': [sys.executable, '-c', 'print("private")'],
            'recipient': keys[1], 'output': str(output), 'timeout': 2, 'max_bytes': 1024})
    assert len(calls) == 2 and not output.exists()


@pytest.mark.parametrize('fault', ['extra', 'traversal', 'duplicate', 'manifest', 'oversize'])
def test_kit_payload_rejects_unsafe_or_incomplete_manifest(modules, fault):
    common, _, kits, _ = modules
    contents = {'config/data': b'selected'}
    expected = {'config/data': {'sha256': digest(b'selected'), 'size': 8}}
    if fault == 'manifest': expected['config/data']['sha256'] = '0' * 64
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as archive:
        for name, data in [('config/data', b'selected'), ('manifest.json', json.dumps(expected).encode())]:
            item = tarfile.TarInfo(name); item.size = len(data); archive.addfile(item, io.BytesIO(data))
        if fault in ('extra', 'traversal', 'duplicate'):
            name = {'extra': 'unexpected', 'traversal': '../outside', 'duplicate': 'config/data'}[fault]
            archive.addfile(tarfile.TarInfo(name))
    if fault == 'oversize': contents = {'config/data': b'wrong'}
    with pytest.raises(common.Refusal): kits.verify_payload(payload.getvalue(), contents)


def test_make_entry_ignores_fleet_code_and_does_not_expand_plan_values(tmp_path):
    marker = tmp_path / 'executed'
    (tmp_path / 'Makefile').write_bytes((ROOT / 'Makefile').read_bytes())
    (tmp_path / '.fleet.mk').write_text(f'$(shell touch {marker})\n')
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts/operator-maintenance.py').write_text('import json,os,sys;print(json.dumps([sys.argv[1],os.environ["OPERATOR_MAINTENANCE_PLAN"]]))')
    literal = '$(shell touch ' + str(marker) + ')'
    env = {k: v for k, v in os.environ.items() if k not in ('MAKEFILES', 'MAKEFLAGS', 'GNUMAKEFLAGS', 'MFLAGS')}
    result = subprocess.run(['make', 'operator-kit-check'], cwd=tmp_path,
                            env={**env, 'OPERATOR_MAINTENANCE_PLAN': literal}, capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout) == ['operator-kit-check', literal]
    assert not marker.exists()


@pytest.mark.parametrize("termination", ["SIGINT", "SIGTERM", "SIGHUP"])
def test_diagnostic_cancellation_retains_ciphertext_and_stops_child(tmp_path, keys, termination):
    import signal
    import time
    marker, output = tmp_path / 'started', tmp_path / 'cancelled.age'
    plan = private(tmp_path / 'plan.json', {'schema_version': 1,
        'argv': [sys.executable, '-c', f'import os,time;open({str(marker)!r},"w").write(str(os.getpid()));print("partial",flush=True);time.sleep(30)'],
        'recipient': keys[1], 'output': str(output), 'timeout': 30, 'max_bytes': 4096})
    child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/operator-maintenance.py'), 'operator-diagnostics'],
        env={**os.environ, 'OPERATOR_MAINTENANCE_PLAN': str(plan), 'OPERATOR_CONFIRM_COMMAND': '1'},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.monotonic() + 5
    try:
        while not marker.exists() and child.poll() is None and time.monotonic() < deadline: time.sleep(0.02)
        assert marker.exists()
        child.send_signal(getattr(signal, termination))
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode == 130, (stdout, stderr)
        payload = json.loads(decrypt(output, keys[0]))
        assert payload['capture'] == 'cancelled'
        pid = int(marker.read_text())
        state = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', str(pid)], capture_output=True).stdout.strip()
        assert not state or state.startswith(b'Z')
    finally:
        if child.poll() is None: child.kill(); child.wait()


def test_release_url_requires_exact_version_token(modules, tmp_path):
    common, releases, _, _ = modules
    archive = tmp_path / 'release.zip'
    with zipfile.ZipFile(archive, 'w') as file: file.writestr('app', b'release')
    plan, descriptor, source = release_plan(tmp_path, archive, ['app'], version='26.10.3',
                                             url='https://example.com/v26.10.31/app.zip')
    with pytest.raises(common.Refusal, match='invalid-release-url'): releases.check(plan)
    descriptor['version'] = '26.10.31'
    save_release(plan, descriptor, source)
    assert releases.check(plan)['result'] == 'release-inputs-verified'


def test_ciphertext_stdin_can_exceed_plaintext_bound(modules, tmp_path, keys, monkeypatch):
    common, _, _, _ = modules
    # Age armor is larger than its plaintext. Scale the byte ceiling, not the crypto.
    monkeypatch.setattr(common, 'MAX_BYTES', 65536)
    plaintext = b'selected material' * 3500
    encrypted = common.checked(['age', '-a', '-r', keys[1]], data=plaintext, limit=131072)
    assert 65536 < len(encrypted) < 131072
    assert common.checked(['age', '-d', '-i', str(keys[0])], data=encrypted, limit=65536) == plaintext
    with pytest.raises(common.Refusal, match='capture-limit'):
        common.capture([sys.executable, '-c', 'pass'], data=b'x' * 131073)


def test_cli_uses_frozen_plan_and_refuses_replaced_authority(modules, tmp_path, keys, monkeypatch, capsys):
    common, _, _, entry = modules
    marker = tmp_path / 'command-started'
    plan = {'schema_version': 1, 'argv': [sys.executable, '-c', f'open({str(marker)!r},"w").write("started")'],
            'recipient': keys[1], 'output': str(tmp_path / 'plan-race.age'), 'timeout': 2, 'max_bytes': 4096}
    path = private(tmp_path / 'plan.json', plan)
    original = entry.read_owned
    calls = []
    def rotate(*args, **kwargs):
        raw = original(*args, **kwargs)
        if not calls:
            calls.append(1); private(path, {**plan, 'output': str(tmp_path / 'foreign.age')})
        return raw
    monkeypatch.setattr(entry, 'read_owned', rotate)
    monkeypatch.setenv('OPERATOR_MAINTENANCE_PLAN', str(path)); monkeypatch.setenv('OPERATOR_CONFIRM_COMMAND', '1')
    monkeypatch.setattr(sys, 'argv', ['operator-maintenance.py', 'operator-diagnostics'])
    previous = {sig: __import__('signal').getsignal(sig) for sig in (__import__('signal').SIGTERM, __import__('signal').SIGHUP)}
    try:
        assert entry.main() == 2
    finally:
        for sig, handler in previous.items(): __import__('signal').signal(sig, handler)
    assert 'plan-changed' in capsys.readouterr().err and not marker.exists()


def test_kit_check_revalidates_catalog_and_earlier_files(modules, kit, tmp_path, monkeypatch):
    common, _, kits, _ = modules
    first = Path(json.loads(Path(kit['catalog']).read_bytes())['current'])
    later = private(tmp_path / 'later', b'later')
    private(Path(kit['catalog']), {'current': str(first), 'later': str(later)})
    kit['entries'].append({'name': 'config/later', 'pointer': '/later', 'kind': 'configuration',
                           'sha256': digest(b'later')})
    original = kits.read_owned
    def rotate(path, **kwargs):
        data = original(path, **kwargs)
        if Path(path) == later: private(first, b'changed-during-collection')
        return data
    monkeypatch.setattr(kits, 'read_owned', rotate)
    with pytest.raises(common.Refusal, match='kit-file-mismatch'): kits.check(kit)


def test_backup_refuses_path_search_for_pinned_rclone(modules, kit, tmp_path):
    common, _, kits, _ = modules
    sealed = kits.seal(kit)
    kit['backup'].update(sha256=sealed['ciphertext_sha256'], bucket='test-bucket', object='current.age',
                          rclone='rclone', rclone_sha256='0' * 64)
    with pytest.raises(common.Refusal, match='absolute-rclone-path-required'): kits.verify_backup(kit)


def test_release_source_hash_and_duplicate_yaml_are_checked(modules, tmp_path):
    common, releases, _, _ = modules
    archive = tmp_path / 'release.zip'
    with zipfile.ZipFile(archive, 'w') as file: file.writestr('app', b'app')
    plan, descriptor, source = release_plan(tmp_path, archive, ['app'])
    source.write_bytes(source.read_bytes() + b' ')
    with pytest.raises(common.Refusal, match='release-source-mismatch'): releases.check(plan)
    private(source, b'component:\n  version: 2.0\n  version: 1.0\n')
    plan['releases'][0]['source_sha256'] = digest(source.read_bytes())
    with pytest.raises(common.Refusal, match='duplicate-json-key'): releases.check(plan)


def test_release_bounds_gzip_expansion_before_tar_headers(modules, tmp_path, monkeypatch):
    common, releases, _, _ = modules
    archive = tmp_path / 'release.tar.gz'
    with tarfile.open(archive, 'w:gz') as file:
        item = tarfile.TarInfo('app'); item.size = 5000
        file.addfile(item, io.BytesIO(b'x' * 5000))
    plan, _, _ = release_plan(tmp_path, archive, ['app'])
    monkeypatch.setattr(releases, 'MAX_BYTES', 1024)
    with pytest.raises(common.Refusal, match='archive-expanded-limit'): releases.check(plan)


@pytest.mark.parametrize('tag', ['v26.10.31-rc1', 'v26.10.31+other', 'v26.10.310'])
def test_release_refuses_other_full_version_segments(modules, tmp_path, tag):
    common, releases, _, _ = modules
    archive = tmp_path / 'release.zip'
    with zipfile.ZipFile(archive, 'w') as file: file.writestr('app', b'app')
    plan, _, _ = release_plan(tmp_path, archive, ['app'], version='26.10.31',
                              url='https://example.com/' + tag + '/app.zip')
    with pytest.raises(common.Refusal, match='invalid-release-url'): releases.check(plan)


@pytest.mark.parametrize('extra', [{}, {'releases': []}])
def test_release_refuses_empty_maintenance_plan(modules, extra):
    common, releases, _, _ = modules
    with pytest.raises(common.Refusal): releases.check({'schema_version': 1, **extra})


def test_private_input_rejects_parent_alias_through_writable_directory(modules, tmp_path):
    common, _, _, _ = modules
    trusted = tmp_path / 'private'; trusted.mkdir(mode=0o700)
    source = private(trusted / 'plan.json', b'private-authority')
    untrusted = tmp_path / 'untrusted'; untrusted.mkdir(); untrusted.chmod(0o777)
    (untrusted / 'alias').symlink_to(trusted, target_is_directory=True)
    with pytest.raises(common.Refusal, match='unsafe-directory'):
        common.read_owned(untrusted / 'alias' / 'plan.json')
    assert common.read_owned(source) == b'private-authority'


def test_private_input_accepts_the_system_temporary_directory_alias(modules):
    import tempfile
    common, _, _, _ = modules
    with tempfile.TemporaryDirectory(prefix='operator-alias-', dir='/tmp') as directory:
        source = private(Path(directory) / 'plan.json', b'selected-authority')
        assert common.read_owned(source) == b'selected-authority'
