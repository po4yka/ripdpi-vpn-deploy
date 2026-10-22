#!/usr/bin/env python3
"""Private bounded route probe, supervised by the controller's total deadline."""
from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
from urllib.parse import urlsplit

from authenticated_http import https_origin


def probe(value):
    if not isinstance(value, dict) or set(value) != {'origin', 'address', 'token', 'expected_b64', 'expected_status'}:
        raise ValueError('invalid-route-input')
    origin = urlsplit(https_origin(value['origin']))
    ipaddress.ip_address(value['address'])
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', value['token']):
        raise ValueError('invalid-route-token')
    expected = base64.b64decode(value['expected_b64'], validate=True)
    if (value['expected_status'] not in (200, 410) or type(value['expected_status']) is not int
            or (value['expected_status'] == 200 and not 1 <= len(expected) <= 1024)
            or (value['expected_status'] == 410 and expected)):
        raise ValueError('invalid-route-body')
    context = ssl.create_default_context()
    connection = http.client.HTTPSConnection(origin.hostname, origin.port or 443, timeout=10, context=context)
    try:
        raw = socket.create_connection((value['address'], origin.port or 443), timeout=10)
        try:
            connection.sock = context.wrap_socket(raw, server_hostname=origin.hostname)
        except BaseException:
            raw.close()
            raise
        connection.request('GET', '/sub/' + value['token'], headers={'Cache-Control': 'no-cache'})
        response = connection.getresponse()
        body = response.read(4097 if value['expected_status'] == 410 else len(expected) + 1)
        if (response.status != value['expected_status'] or len(body) > 4096
                or value['expected_status'] == 200 and body != expected):
            raise ValueError('route-body-mismatch')
    finally:
        connection.close()


def main():
    try:
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            return 2
        probe(json.loads(raw))
        return 0
    except Exception:
        return 2


if __name__ == '__main__':
    sys.exit(main())
