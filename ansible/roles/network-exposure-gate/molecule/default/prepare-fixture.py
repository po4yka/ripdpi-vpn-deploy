#!/usr/bin/env python3
"""Generate ephemeral signed test data; never persist feed addresses in Git."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import secrets
import subprocess
import sys

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
root.chmod(0o700)
private = root / 'signing.pem'
public = root / 'trusted.pem'
subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(private)], check=True, capture_output=True)
private.chmod(0o600)
subprocess.run(['openssl', 'pkey', '-in', str(private), '-pubout', '-out', str(public)], check=True, capture_output=True)
public.chmod(0o600)
der = subprocess.run(['openssl', 'pkey', '-pubin', '-in', str(public), '-outform', 'DER'], check=True, capture_output=True).stdout
canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
now = datetime.now(timezone.utc)
policy = {name: [str(ipaddress.ip_network((secrets.randbits(bits), bits)))]
          for name, bits in [('ingress', 32), ('host_egress', 128), ('forwarded', 32)]}
metadata = {'schema_version': 1, 'source_id': 'reviewed-molecule',
            'created_at': (now-timedelta(minutes=2)).isoformat(),
            'expires_at': (now+timedelta(hours=2)).isoformat(),
            'review': {'approved': True, 'reviewer': 'molecule-reviewer', 'review_id': 'molecule-review'},
            'content_sha256': hashlib.sha256(canonical(policy)).hexdigest(), 'policy': policy}
for name, expires in [('reviewed', metadata['expires_at']), ('expired', (now-timedelta(minutes=1)).isoformat())]:
    value = {**metadata, 'expires_at': expires}
    signature = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(private)], input=canonical(value), check=True, capture_output=True).stdout
    value['signature'] = {'algorithm': 'rsa-sha256', 'value': base64.b64encode(signature).decode()}
    path = root / f'{name}.json'
    path.write_bytes(canonical(value))
    path.chmod(0o600)
config = {'mode': 'canary', 'artifact': str(root / 'reviewed.json'), 'trusted_key': str(public),
          'trusted_key_sha256': hashlib.sha256(der).hexdigest(), 'source_id': 'reviewed-molecule',
          'promotion_approved': True, 'promotion_digest': hashlib.sha256((root / 'reviewed.json').read_bytes()).hexdigest(),
          'authorized_hosts': ['vpn-network-exposure-debian13']}
variables = root / 'vars.json'
variables.write_text(json.dumps({'exposure_fixture_config': config, 'exposure_expired_artifact': str(root / 'expired.json'),
                                'exposure_test_ssh_cidrs': policy['ingress']}))
variables.chmod(0o600)
