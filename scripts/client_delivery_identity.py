"""Private versioned HMAC identity; no public digest or legacy comparison."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets

from client_payload import validate_options


def authority(document, *, create=False):
    if 'client_delivery_identity' not in document and create:
        key = secrets.token_hex(32)
        generation = hashlib.sha256(b'vpn-client-authority-v1\0' + bytes.fromhex(key)).hexdigest()[:32]
        document['client_delivery_identity'] = dict(version=1, generation=generation, key=key)
    value = document.get('client_delivery_identity')
    if (not isinstance(value, dict) or set(value) != {'version', 'generation', 'key'} or type(value['version']) is not int or value['version'] != 1
            or not isinstance(value['generation'], str) or not re.fullmatch('[0-9a-f]{32}', value['generation'])
            or not isinstance(value['key'], str) or not re.fullmatch('[0-9a-f]{64}', value['key'])):
        raise ValueError('identity-authority-unavailable')
    expected = hashlib.sha256(b'vpn-client-authority-v1\0' + bytes.fromhex(value['key'])).hexdigest()[:32]
    if not hmac.compare_digest(expected, value['generation']):
        raise ValueError('identity-authority-generation-mismatch')
    return value


def digest(client, options, payload, bindings, auth):
    validate_options(options)
    data = json.dumps(dict(domain='vpn-client-delivery', version=1, client=client, options=options,
                           bindings=bindings, payload=payload), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return dict(version=1, generation=auth['generation'], digest=hmac.new(bytes.fromhex(auth['key']), data, hashlib.sha256).hexdigest())


def comparable(record, auth):
    return (isinstance(record, dict) and set(record) == {'version', 'generation', 'digest'}
            and type(record['version']) is int and record['version'] == 1 and record['generation'] == auth['generation']
            and isinstance(record['digest'], str) and re.fullmatch('[0-9a-f]{64}', record['digest']) is not None)
