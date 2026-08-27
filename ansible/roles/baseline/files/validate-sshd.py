#!/usr/bin/env python3
"""Validate SSH ownership and the candidate in the assembled OpenSSH config."""

import argparse
import fnmatch
import glob
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def directives(text):
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, value = re.split(r'[\s=]+', line, maxsplit=1)
        key = key.lower()
        if key in result or key in {'include', 'match'}:
            raise ValueError(f'duplicate or unsupported managed directive: {key}')
        result[key] = ' '.join(shlex.split(value, comments=True))
    return result


def validate(args):
    candidate = Path(args.candidate).read_text()
    expected = directives(candidate)
    bootstrap = directives(Path(args.boot).read_text())
    duplicates = expected.keys() & bootstrap.keys()
    if duplicates:
        raise ValueError('duplicate SSH directive ownership: ' + ', '.join(sorted(duplicates)))
    expected.update(bootstrap)
    managed = str(Path(args.managed).absolute())
    seen_managed = False

    def assemble(path, parents=()):
        nonlocal seen_managed
        if path in parents:
            raise ValueError(f'recursive SSH Include: {path}')
        if path == managed:
            seen_managed = True
            return candidate
        lines = []
        for line in Path(path).read_text().splitlines():
            fields = shlex.split(line, comments=True)
            if fields and fields[0].lower() == 'include':
                for pattern in fields[1:]:
                    if not Path(pattern).is_absolute():
                        pattern = str(Path(args.main).parent / pattern)
                    matches = set(glob.glob(pattern))
                    if fnmatch.fnmatchcase(managed, pattern):
                        matches.add(managed)
                    lines.extend(assemble(match, (*parents, path)) for match in sorted(matches))
            else:
                lines.append(line)
        return '\n'.join(lines) + '\n'

    assembled = assemble(str(Path(args.main).absolute()))
    if not seen_managed:
        raise ValueError('managed SSH policy is not included by the main configuration')
    with tempfile.NamedTemporaryFile(mode='w', prefix='vpn-sshd-', suffix='.conf') as config:
        config.write(assembled)
        config.flush()
        result = subprocess.run([args.sshd, '-T', '-f', config.name], capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError('assembled sshd configuration rejected: ' + result.stderr.strip())
    effective = {}
    for line in result.stdout.splitlines():
        key, value = line.split(' ', 1)
        effective.setdefault(key, []).append(value)
    for key, value in expected.items():
        actual = effective.get(key, [])
        if key == 'loglevel':
            actual, value = [entry.lower() for entry in actual], value.lower()
        if actual != [value]:
            raise ValueError(f'effective SSH directive mismatch: {key}: expected {value!r}, got {actual!r}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate')
    parser.add_argument('--main', default='/etc/ssh/sshd_config')
    parser.add_argument('--boot', default='/etc/ssh/sshd_config.d/10-cloud-init-hardening.conf')
    parser.add_argument('--managed', default='/etc/ssh/sshd_config.d/20-ansible-hardening.conf')
    parser.add_argument('--sshd', default='/usr/sbin/sshd')
    try:
        validate(parser.parse_args())
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
