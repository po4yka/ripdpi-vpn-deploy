#!/usr/bin/env python3
"""Prepare coherent release inputs from checksum-verified local artifacts."""
from __future__ import annotations

import argparse
from email.parser import Parser
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import tarfile
from urllib.parse import urlsplit
import zipfile

from operator_maintenance_io import MaintenanceError, read_bytes, write_document
from recovery_io import document

MEMBERS = {
    'prometheus': {'archive_members': 'prometheus-{version}.linux-{arch}/prometheus',
                   'promtool_archive_members': 'prometheus-{version}.linux-{arch}/promtool'},
    'alertmanager': {'archive_members': 'alertmanager-{version}.linux-{arch}/alertmanager',
                     'amtool_archive_members': 'alertmanager-{version}.linux-{arch}/amtool'},
    'rclone': {'archive_members': 'usr/bin/rclone'},
    'xray': {'archive_members': 'xray'},
    'vmagent': {'archive_members': 'vmagent-prod'},
    'hysteria': {'archive_members': 'hysteria'},
}
FORMATS = {'prometheus': 'tar', 'alertmanager': 'tar', 'rclone': 'deb',
           'xray': 'zip', 'vmagent': 'tar', 'hysteria': 'binary'}
MAX_EXPANDED = 512 * 1024 * 1024


def safe_name(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or '\x00' in name:
        raise MaintenanceError('unsafe-archive-member')
    return str(path)


def contents(raw, kind):
    """Read archive entries without extracting paths onto the filesystem."""
    if kind == 'binary':
        yield None, raw
        return
    total, seen = 0, set()
    if kind == 'tar':
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
            for index, member in enumerate(archive):
                name = safe_name(member.name)
                if index >= 4096 or name in seen or not (member.isfile() or member.isdir()):
                    raise MaintenanceError('ambiguous-or-unsupported-archive-member')
                seen.add(name)
                total += member.size
                if total > MAX_EXPANDED or member.size < 0:
                    raise MaintenanceError('expanded-archive-limit')
                if member.isfile():
                    with archive.extractfile(member) as stream:
                        yield name, stream.read(member.size + 1)
    elif kind == 'zip':
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for index, member in enumerate(archive.infolist()):
                name = safe_name(member.filename)
                mode = member.external_attr >> 16
                if index >= 4096 or name in seen or mode & 0o170000 == 0o120000:
                    raise MaintenanceError('ambiguous-or-unsupported-archive-member')
                seen.add(name)
                total += member.file_size
                if total > MAX_EXPANDED:
                    raise MaintenanceError('expanded-archive-limit')
                if not member.is_dir():
                    with archive.open(member) as stream:
                        yield name, stream.read(member.file_size + 1)
    else:
        raise MaintenanceError('unsupported-artifact-format')


def elf_architecture(data, architecture):
    if (len(data) < 20 or data[:4] != b'\x7fELF' or data[4:6] != b'\x02\x01'
            or struct.unpack('<H', data[18:20])[0] != {'amd64': 62, 'arm64': 183}[architecture]):
        raise MaintenanceError('binary-architecture-mismatch')


def deb_contents(raw, version, architecture):
    if raw[:8] != b'!<arch>\n':
        raise MaintenanceError('invalid-deb-envelope')
    position, members = 8, {}
    while position < len(raw):
        header = raw[position:position + 60]
        if len(header) != 60 or header[58:] != b'`\n':
            raise MaintenanceError('invalid-deb-member')
        name = header[:16].decode('ascii').strip().removesuffix('/')
        size = int(header[48:58].decode('ascii').strip())
        if size < 0 or size > len(raw) - position - 60 or name in members:
            raise MaintenanceError('invalid-deb-member')
        members[name] = raw[position + 60:position + 60 + size]
        position += 60 + size + size % 2
    names = list(members)
    if (position != len(raw) or len(names) != 3 or names[0] != 'debian-binary'
            or members[names[0]] != b'2.0\n'
            or names[1] not in {'control.tar', 'control.tar.gz', 'control.tar.xz'}
            or names[2] not in {'data.tar', 'data.tar.gz', 'data.tar.xz'}):
        raise MaintenanceError('unsupported-deb-layout')
    control = dict(contents(members[names[1]], 'tar'))
    if set(control) != {'control'}:
        raise MaintenanceError('unexpected-deb-control-files')
    fields = Parser().parsestr(control['control'].decode('utf-8'))
    for key, expected in {'Package': 'rclone', 'Version': version, 'Architecture': architecture}.items():
        if fields.get_all(key) != [expected]:
            raise MaintenanceError('deb-package-identity-mismatch')
    payload = dict(contents(members[names[2]], 'tar'))
    if set(payload) - {'usr/bin/rclone', 'usr/share/doc/rclone/copyright'} or 'usr/bin/rclone' not in payload:
        raise MaintenanceError('unexpected-deb-payload')
    return payload.items()


def role_variables(component, release, binary_hashes, config):
    if component == 'prometheus':
        return {'observability_control_plane': {'prometheus': release}}
    if component == 'alertmanager':
        return {'observability_control_plane': {'alerting': {'alertmanager': release}}}
    hashes = {f'linux_{arch}_sha256': value for arch, value in release['sha256'].items()}
    if component == 'vmagent':
        # The collector relay pins the same verified vmutils archives as the sender.
        return {'observability_agent': {'version': release['version'], 'release_urls': release['urls'], **hashes},
                'observability_control_plane': {'relay': release}}
    if component == 'rclone':
        return {'backup_rclone_version': release['version'], 'backup_rclone_binary_sha256': binary_hashes,
                'backup_rclone_packages': {arch: {'url': release['urls'][arch], 'sha256': release['sha256'][arch]}
                                           for arch in ('amd64', 'arm64')}}
    values = {component: {'version': release['version'], **hashes}}
    values['xray_runtime_release_urls' if component == 'xray' else 'hysteria_release_urls'] = release['urls']
    if component == 'hysteria':
        values['hysteria_runtime_release_version'] = config['runtime_release_version']
    return values


def prepare(config):
    fields = {'schema_version', 'component', 'version', 'artifacts'}
    if config.get('component') == 'hysteria':
        fields.add('runtime_release_version')
    if (set(config) != fields
            or config['schema_version'] != 1 or config['component'] not in MEMBERS
            or not isinstance(config['version'], str)
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:\+go[0-9]+\.[0-9]+\.[0-9]+-[0-9]+)?'
                                if config['component'] == 'rclone' else r'[0-9]+\.[0-9]+\.[0-9]+', config['version'])
            or set(config['artifacts']) != {'amd64', 'arm64'}):
        raise MaintenanceError('invalid-release-configuration')
    component, version = config['component'], config['version']
    if component == 'hysteria' and not re.fullmatch(r'v?[0-9]+\.[0-9]+\.[0-9]+(?:-go[0-9]+\.[0-9]+\.[0-9]+)?',
                                                   config['runtime_release_version']):
        raise MaintenanceError('invalid-runtime-release-identity')
    result = {'version': version, 'urls': {}, 'sha256': {},
              **{key: {} for key in MEMBERS[component]}}
    proof, binary_hashes = {}, {}
    for arch, artifact in config['artifacts'].items():
        if (set(artifact) != {'url', 'path', 'sha256', 'format'}
                or not re.fullmatch(r'[0-9a-f]{64}', artifact['sha256'])
                or artifact['format'] != FORMATS[component]):
            raise MaintenanceError('invalid-artifact-configuration')
        url = urlsplit(artifact['url'])
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.port not in (None, 443)):
            raise MaintenanceError('invalid-artifact-origin')
        raw = read_bytes(artifact['path'], private=False)
        if hashlib.sha256(raw).hexdigest() != artifact['sha256']:
            raise MaintenanceError('artifact-checksum-mismatch')
        expected = {key: template.format(version=version, arch=arch)
                    for key, template in MEMBERS[component].items()}
        found = set()
        entries = deb_contents(raw, version, arch) if artifact['format'] == 'deb' else contents(raw, artifact['format'])
        for name, data in entries:
            if name is None:
                if len(expected) != 1:
                    raise MaintenanceError('archive-required')
                name = next(iter(expected.values()))
            if name in expected.values():
                elf_architecture(data, arch)
                found.add(name)
                if len(expected) == 1:
                    binary_hashes[arch] = hashlib.sha256(data).hexdigest()
        if found != set(expected.values()):
            raise MaintenanceError('required-archive-member-missing')
        result['urls'][arch] = artifact['url']
        result['sha256'][arch] = artifact['sha256']
        for key, member in expected.items():
            result[key][arch] = member
        proof[arch] = {'sha256': artifact['sha256'], 'members': sorted(found),
                       'ELF_architecture_verified': True}
    return {'schema_version': 1, 'component': component,
            'ansible_variables': role_variables(component, result, binary_hashes, config),
            'artifact_verification': proof}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = prepare(document(args.config))
        if args.action == 'prepare':
            if args.output is None:
                raise MaintenanceError('output-required')
            write_document(args.output, result)
        print(json.dumps({'phase': 'artifacts-verified', 'component': result['component'],
                          'architectures': sorted(result['artifact_verification'])}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, zipfile.BadZipFile):
        print('release-inputs: artifact verification refused', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
