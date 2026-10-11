"""Explicit host identity reaches real child-process boundaries."""
import json
from artifact_helpers import scaffold, executable, cli


def test_doctor_and_probe_propagate_selected_host(tmp_path):
    scaffold(tmp_path)
    for directory in ['home/.config/vpn-provision', 'home/Library/Application Support/vpn-provision']:
        folder = tmp_path / directory
        folder.mkdir(parents=True)
        (folder / 'hosts.toml').write_text("[hosts.selected]\nenv='test'\nprovider='upcloud'\nipv4='203.0.113.77'\n")
    executable(tmp_path, 'make', '''#!/usr/bin/env python3
import json, os, sys
print(json.dumps({'target':sys.argv[1], 'ip':os.environ.get('IP'), 'args':[arg for arg in sys.argv[2:] if arg.startswith('HOST=')]}))
''')
    result = cli(tmp_path, 'doctor', '--host', 'selected')
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    assert len(rows) == 6
    for row in rows:
        if row['target'] in {'fleet-status', 'audit-permissions'}:
            assert row['ip'] is None
        else:
            assert row['ip'] == '203.0.113.77'
    assert result.stdout.count('(global check)') == 2
    result = cli(tmp_path, 'probe', '--host', 'selected')
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    for row in rows:
        if row['target'] in {'probing-summary', 'burn-check', 'asn-drift'}:
            assert row['ip'] == '203.0.113.77'
        if row['target'] == 'test-tls-policing':
            assert 'HOST=203.0.113.77' in row['args']
    assert 'not host-specific' in result.stderr
