#!/usr/bin/env python3
"""Render a replacement pair while retaining admitted unrelated inventory rows."""
from __future__ import annotations

import argparse
import os
import shlex
import sys
import tempfile
from pathlib import Path

from bootstrap_readiness import run_command
from device_migration_errors import MigrationRefused
from device_migration_io import load_plan
from fleet_inspection import LIMIT, _open_local_file, select_hosts


def read(path):
    with os.fdopen(_open_local_file(path), 'rb') as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise MigrationRefused('migration-inventory-limit')
    return raw


def sections(raw):
    result, section = {}, None
    for line in raw.decode().splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
            if section in result:
                raise MigrationRefused('migration-inventory-duplicate-section')
            result[section] = []
        elif section is None:
            raise MigrationRefused('migration-inventory-section-required')
        else:
            result[section].append(line)
    return result


def names(lines):
    return [shlex.split(line, comments=True)[0] for line in lines]


def admitted(plan, path):
    raw = read(path)
    blocks = sections(raw)
    aliases = names(blocks.get('vpn', []))
    if not aliases:
        raise MigrationRefused('migration-inventory-empty')
    select_hosts(path, aliases, include_variables=True, include_cohorts=True)
    expected = {'ansible_ssh_private_key_file': os.environ.get('ANSIBLE_SSH_PRIVATE_KEY_FILE'),
                'ansible_python_interpreter': '/usr/bin/python3'}
    actual = dict(word.split('=', 1) for line in blocks.get('vpn:vars', []) for word in shlex.split(line, comments=True))
    if actual != expected or expected['ansible_ssh_private_key_file'] is None:
        raise MigrationRefused('migration-inventory-global-authority-changed')
    # A topology-wide generation must be rendered as a whole by its owner.
    # Pair-only rendering cannot safely preserve a changed collector topology.
    if any(name.startswith('observability') or name == 'vpn-observability-control' for name in blocks):
        raise MigrationRefused('migration-inventory-requires-complete-topology-render')
    replaced = {plan['source']['alias'], plan['target']['alias']}
    publishers = {plan['publication']['source_alias'], plan['publication']['target_alias']} - replaced
    if not publishers <= set(aliases):
        raise MigrationRefused('migration-publisher-inventory-unavailable')
    return raw, blocks


def merge(plan, original, rendered):
    """Keep unrelated rows and cohorts; refuse changed inherited authority."""
    replaced = {plan['source']['alias'], plan['target']['alias']}
    if set(names(rendered.get('vpn', []))) != replaced:
        raise MigrationRefused('migration-rendered-pair-mismatch')
    for section in set(original) | set(rendered):
        if section.endswith(':vars') and original.get(section, []) != rendered.get(section, []):
            raise MigrationRefused('migration-inventory-global-authority-changed')
    result = {}
    for section in dict.fromkeys([*original, *rendered]):
        if section.endswith(':vars'):
            result[section] = original[section]
            continue
        if section != 'vpn' and not section.startswith('vpn-'):
            raise MigrationRefused('migration-inventory-unsupported-section')
        retained = [line for line in original.get(section, []) if names([line])[0] not in replaced]
        incoming = rendered.get(section, [])
        if any(name not in replaced for name in names(incoming)):
            raise MigrationRefused('migration-rendered-unrelated-host')
        if retained or incoming:
            result[section] = retained + incoming
    return ''.join('[' + section + ']\n' + '\n'.join(lines) + '\n\n' for section, lines in result.items()).encode()


def render(plan):
    path = Path(plan['inventory'])
    before, original = admitted(plan, path)
    descriptor, name = tempfile.mkstemp(prefix='.migration-inventory.', dir=path.parent)
    stage = Path(name)
    os.close(descriptor)
    try:
        environment = dict(os.environ, INVENTORY_OUTPUT=str(stage))
        status, _ = run_command(['bash', str(Path(__file__).with_name('render-inventory.sh'))],
                                capture=True, timeout=180, output_limit=LIMIT * 2, environment=environment)
        if status:
            raise MigrationRefused('migration-inventory-render-failed')
        fresh = sections(read(stage))
        if any(name.startswith('observability') or name == 'vpn-observability-control' for name in fresh):
            raise MigrationRefused('migration-inventory-requires-complete-topology-render')
        select_hosts(stage, [plan['source']['alias'], plan['target']['alias']], include_variables=True, include_cohorts=True)
        candidate = merge(plan, original, fresh)
        with stage.open('wb') as stream:
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        admitted(plan, stage)
        if read(path) != before:
            raise MigrationRefused('migration-inventory-changed-during-render')
        os.replace(stage, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        stage.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'render'])
    parser.add_argument('--plan', required=True)
    args = parser.parse_args()
    try:
        plan = load_plan(args.plan)
        admitted(plan, plan['inventory']) if args.action == 'check' else render(plan)
        return 0
    except Exception:
        print('device-migration: inventory preparation refused; retain the current nodes', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
