#!/usr/bin/env python3
"""Exercise official mtg bytes, native parsing and rejected publication locally."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[2]
VERSION = '2.2.8'
SHA256 = {
    ('linux', 'amd64'): '7ef19d079d85f4e00d4f8334ec1f3f3c8718e3d0ed1f3109ea9a8673138a2102',
    ('linux', 'arm64'): '562a94dd4cafcb8f179b76cfeafb76da12747c8e230bc76235bf8746cc189644',
    ('darwin', 'amd64'): '178f7903c2e2aa82f7cc045438f10ca30e7469c579e6de85caf52fc450890a65',
    ('darwin', 'arm64'): '98af09fb555749aa446d1aec35efc2065ad1ed630abacd5299c703f75cc0cbe6',
}
VALIDATOR = ROOT / 'ansible/roles/probe-matrix-target/files/validate_mtg.py'


def static_task_labels():
    """Bind repository-owned literal task names to payload-free identifiers."""
    source = ROOT / 'ansible/roles/runtime-release/tasks/main.yml'
    labels = {}
    def visit(rows):
        for row in rows:
            name = row.get('name')
            if isinstance(name, str) and '{{' not in name and '{%' not in name:
                labels['runtime-release : ' + name] = f'runtime-release-task-{len(labels) + 1}'
            for key in ('block', 'rescue', 'always'):
                visit(row.get(key, []))
    visit(yaml.safe_load(source.read_text()))
    return labels


def failure_context(result):
    """Expose static task labels and refusal categories, never tool payloads."""
    tasks = list(re.finditer(r"(?m)^TASK \[(.{1,512})\] \*+$", result.stdout))
    labels = static_task_labels()
    failed = []
    for index, task in enumerate(tasks):
        end = tasks[index + 1].start() if index + 1 < len(tasks) else len(result.stdout)
        body = result.stdout[task.end():end]
        if re.search(r"(?m)^(?:fatal:|failed:|\[ERROR\])", body):
            failed.append(labels.get(task.group(1), 'unknown-task'))
    categories = []
    diagnostic = result.stdout + result.stderr
    for marker, category in (
        ('unsafe-storage-ancestor', 'unsafe-storage-ancestor'),
        ('unsafe-public-link-parent-directory', 'unsafe-public-link-parent-directory'),
        ('a password is required', 'become-password-required'),
        ('Missing sudo password', 'become-password-required'),
        ('Permission denied', 'permission-refused'),
        ("couldn't resolve module", 'module-unavailable'),
        ('No module named', 'python-dependency-unavailable'),
        ('untrusted', 'templating-untrusted'),
        ('Module result deserialization failed', 'interpreter-result-refused'),
    ):
        if marker in diagnostic and category not in categories:
            categories.append(category)
    # Keep the first causal failure even when an always cleanup task runs last.
    label = failed[0] if failed else labels.get(tasks[-1].group(1), 'unknown-task') if tasks else 'no-task-label'
    helper = ROOT / 'ansible/roles/runtime-release/files/runtime_release_activate.py'
    allowed = set(re.findall(r'UnsafeState\("([a-z][a-z0-9-]+)"', helper.read_text()))
    for category in sorted(allowed):
        if category in diagnostic and category not in categories:
            categories.append(category)
    return f"rc={result.returncode}; task={label}; categories={','.join(categories) or 'uncategorized'}"


def command(argv, *, success=True, env=None):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=90, env=env)
    if (result.returncode == 0) != success:
        # Ansible and mtg can include synthetic credentials in errors. Keep the
        # same categorical diagnostic contract as the production validator.
        raise RuntimeError('native-command-outcome-mismatch: ' + failure_context(result))
    return result


def config(secret):
    return f'secret = "{secret}"\nbind-to = "127.0.0.1:10443"\n'


def parser_checks(directory, binary):
    raw = b'\xee' + b'\xaa' * 16 + b'example.com'
    candidate = directory / 'candidate.toml'
    for secret in (raw.hex(), base64.urlsafe_b64encode(raw).decode().rstrip('=')):
        candidate.write_text(config(secret))
        command([sys.executable, str(VALIDATOR), '--binary', str(binary), '--version', 'v'+VERSION, '--config', str(candidate)])
    for text in (config('aa'*16), config('ee'+'aa'*16), 'secret = [\n', config(raw.hex())+'bind-to = "invalid"\n'):
        candidate.write_text(text)
        result = command([sys.executable, str(VALIDATOR), '--binary', str(binary), '--version', 'v'+VERSION, '--config', str(candidate)], success=False)
        if result.stdout or result.stderr != 'mtg: native candidate validation refused\n':
            raise RuntimeError('native-validator-output-not-redacted')
    candidate.write_text(config(raw.hex()))
    command([sys.executable, str(VALIDATOR), '--binary', str(binary), '--version', 'v0.0.1', '--config', str(candidate)], success=False)


def create_runtime_public_link(directory):
    """Keep private input ancestry while meeting the public-parent contract."""
    parent = directory / 'bin'
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)
    return parent / 'mtg'


def publication_checks(directory, archive, arch, member):
    if platform.system() != 'Linux' or os.geteuid() != 0:
        raise RuntimeError('full-native-publication-requires-root-Linux')
    install = directory / 'runtime'
    public = create_runtime_public_link(directory)
    upstream_version = 'v' + VERSION
    local_version = upstream_version + '+archive.1'
    legacy = install / 'releases' / upstream_version
    staged = install / 'releases' / local_version / 'mtg'
    destination = directory / 'accepted.toml'
    accepted_config = config((b'\xee' + b'\xaa' * 16 + b'example.com').hex())
    destination.write_text(accepted_config)
    old = destination.stat().st_ino
    template = directory / 'candidate.toml.j2'
    template.write_text('secret = "invalid-synthetic-secret"\nbind-to = "127.0.0.1:10443"\n')
    base_contract = {
        'runtime_release_install_root': str(install), 'runtime_release_binary_name': 'mtg',
        'runtime_release_public_link': str(public),
        'runtime_release_urls': {key: archive.as_uri() for key in ('amd64', 'arm64')},
        'runtime_release_sha256': {key: SHA256[('linux', arch)] for key in ('amd64', 'arm64')},
    }
    corrected = {
        **base_contract, 'runtime_release_version': local_version,
        'runtime_release_artifact_filename': 'mtg.tar.gz', 'runtime_release_artifact_type': 'archive',
        'runtime_release_archive_members': {key: member for key in ('amd64', 'arm64')},
        'runtime_release_archive_strip_components': 1,
        'runtime_release_stage_only': True,
    }
    play = directory / 'publication.yml'
    env = {**os.environ, 'ANSIBLE_ROLES_PATH': str(ROOT/'ansible/roles'), 'ANSIBLE_CONFIG': str(ROOT/'ansible/ansible.cfg')}

    def run_play(tasks, *, success=True):
        play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
            'vars': {'ansible_python_interpreter': sys.executable,
                     'ansible_facts': {'architecture': 'x86_64' if arch == 'amd64' else 'aarch64'}},
            'tasks': tasks}]))
        return command(['ansible-playbook', '-i', 'localhost,', str(play)], success=success, env=env)

    # Reproduce the old role exactly: the official archive is published as an
    # executable binary, with the genuine shared installer's immutable receipt.
    run_play([{'name': 'Reproduce legacy raw archive publication',
        'ansible.builtin.include_role': {'name': 'runtime-release'},
        'vars': {**base_contract, 'runtime_release_version': upstream_version,
                 'runtime_release_artifact_filename': 'mtg', 'runtime_release_artifact_type': 'binary',
                 'runtime_release_stage_only': False}}])
    legacy_binary = legacy / 'mtg'
    receipt = legacy / '.runtime-release.json'
    legacy_receipt = receipt.read_bytes()
    legacy_receipt_inode = receipt.stat().st_ino
    legacy_binary_inode = legacy_binary.stat().st_ino
    if legacy_binary.read_bytes() != archive.read_bytes():
        raise RuntimeError('legacy-installer-did-not-publish-raw-archive')
    document = json.loads(legacy_receipt)
    if (document['version'] != upstream_version
            or document['artifact_sha256'] != SHA256[('linux', arch)]
            or document['binary_sha256'] != document['artifact_sha256']):
        raise RuntimeError('legacy-shared-receipt-was-not-authentic')

    def retain_legacy(*, active=True):
        if (receipt.read_bytes() != legacy_receipt or receipt.stat().st_ino != legacy_receipt_inode
                or legacy_binary.stat().st_ino != legacy_binary_inode
                or legacy_binary.read_bytes() != archive.read_bytes()):
            raise RuntimeError('migration-changed-legacy-bytes-or-receipt')
        if active and (destination.stat().st_ino != old or destination.read_text() != accepted_config
                or public.readlink() != install/'current'/'mtg'
                or (install/'current').readlink() != legacy):
            raise RuntimeError('rejected-candidate-changed-legacy-authority')

    # Reusing the upstream identity cannot repair immutable tarball bytes. The
    # existing receipt remains authoritative and native execution must refuse.
    run_play([{'name': 'Attempt same-identity archive adoption',
        'ansible.builtin.include_role': {'name': 'runtime-release'},
        'vars': {**corrected, 'runtime_release_version': upstream_version}}])
    command([sys.executable, str(VALIDATOR), '--binary', str(legacy_binary),
             '--version', upstream_version, '--config', str(destination)], success=False)
    retain_legacy()

    validate = ' '.join(map(shlex.quote, [sys.executable, str(VALIDATOR), '--binary', str(staged),
                         '--version', upstream_version, '--config'])) + ' %s'
    tasks = [
        {'name': 'Acquire corrected candidate without changing legacy authority',
         'ansible.builtin.include_role': {'name': 'runtime-release'}, 'vars': corrected},
        {'name': 'Refuse invalid candidate before any config or runtime publication',
         'ansible.builtin.template': {'src': str(template), 'dest': str(destination), 'validate': validate, 'mode': '0600'},
         'no_log': True},
        {'name': 'Validate the candidate even when accepted config bytes are unchanged',
         'ansible.builtin.command': {'argv': [sys.executable, str(VALIDATOR), '--binary', str(staged),
                                            '--version', upstream_version, '--config', str(destination)]},
         'changed_when': False, 'no_log': True},
        {'name': 'Publish only after successful native config validation',
         'ansible.builtin.include_role': {'name': 'runtime-release'},
         'vars': {**corrected, 'runtime_release_stage_only': False}},
    ]
    run_play(tasks, success=False)
    if not staged.is_file() or not (staged.parent/'.runtime-release.json').is_file():
        raise RuntimeError('corrected-candidate-was-not-staged')
    retain_legacy()
    template.write_text(accepted_config)
    run_play(tasks)
    retain_legacy(active=False)
    if ((install/'current').readlink() != staged.parent or public.resolve() != staged
            or (install/'previous').readlink() != legacy):
        raise RuntimeError('validated-migration-was-not-published')
    command([sys.executable, str(VALIDATOR), '--binary', str(public), '--version', upstream_version,
             '--config', str(destination)])
    repeated = run_play(tasks)
    if 'changed=0' not in repeated.stdout:
        raise RuntimeError('accepted-native-publication-was-not-idempotent')
    retain_legacy(active=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, help='Use an already downloaded official archive; its checksum is still required.')
    parser.add_argument('--parser-only', action='store_true', help='Run the explicit host parser subset; full CI requires Linux root publication checks.')
    args = parser.parse_args()
    system = platform.system().lower()
    arch = {'x86_64':'amd64', 'amd64':'amd64', 'aarch64':'arm64', 'arm64':'arm64'}.get(platform.machine())
    if (system, arch) not in SHA256:
        raise RuntimeError('unsupported-native-platform')
    name = f'mtg-{VERSION}-{system}-{arch}'
    with tempfile.TemporaryDirectory(prefix='.mtg-native-', dir=Path.home()) as temporary:
        directory = Path(temporary)
        archive = directory / (name+'.tar.gz')
        if args.archive:
            payload = args.archive.read_bytes()
        else:
            with urllib.request.urlopen(f'https://github.com/9seconds/mtg/releases/download/v{VERSION}/{name}.tar.gz', timeout=60) as source:
                payload = source.read(32*1024*1024+1)
        if len(payload) > 32*1024*1024 or hashlib.sha256(payload).hexdigest() != SHA256[(system, arch)]:
            raise RuntimeError('official-archive-checksum-mismatch')
        archive.write_bytes(payload)
        member = name+'/mtg'
        with tarfile.open(archive) as source:
            selected = [entry for entry in source.getmembers() if entry.name == member]
            if len(selected) != 1 or not selected[0].isfile() or selected[0].size > 64*1024*1024:
                raise RuntimeError('official-archive-member-mismatch')
            binary = directory/'mtg'
            binary.write_bytes(source.extractfile(selected[0]).read())
            binary.chmod(0o755)
        parser_checks(directory, binary)
        if not args.parser_only:
            publication_checks(directory, archive, arch, member)
        print('mtg native compatibility: '+('parser subset passed' if args.parser_only else 'archive, parser and legacy migration passed'))


if __name__ == '__main__':
    main()
