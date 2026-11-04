#!/usr/bin/env python3
"""Refuse a node backup credential that could delete or reach other offsite copies.

Reads the rclone configuration on stdin, authorizes its B2 key and requires the
exact append-only grant: no deleteFiles, one private bucket, and a name prefix
equal to this node's replica directory, plus a bucket lifecycle that keeps hidden
versions for at least 30 days. A same-host local remote has no remote grant to check.
Prints one refusal category on failure.
"""
import argparse
import base64
import configparser
import json
import sys
from urllib import request

CAPABILITIES = {'listBuckets', 'listFiles', 'readFiles', 'writeFiles'}
RETENTION_DAYS = 30
AUTHORIZE = 'https://api.backblazeb2.com/b2api/v4/b2_authorize_account'


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('provider-redirect')


def post(opener, url, headers, data=None):
    body = None if data is None else json.dumps(data).encode()
    with opener.open(request.Request(url, data=body, headers=headers), timeout=20) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('provider-response-limit')
    return json.loads(raw)


def check(config_text, remote, path, host, opener):
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(config_text)
    if not config.has_section(remote):
        raise ValueError('remote-missing')
    section = config[remote]
    if section.get('type') == 'local':
        return 'backup-storage-grant-not-applicable'
    if section.get('type') != 'b2':
        raise ValueError('remote-not-b2')
    if section.get('hard_delete', 'false').strip().lower() not in ('false', ''):
        raise ValueError('hard-delete-configured')
    bucket, _, subpath = path.strip('/').partition('/')
    prefix = f'{subpath}/{host}/' if subpath else f'{host}/'
    basic = base64.b64encode(f"{section['account']}:{section['key']}".encode()).decode()
    auth = post(opener, AUTHORIZE, {'Authorization': 'Basic ' + basic})
    storage = auth['apiInfo']['storageApi']
    allowed = storage['allowed']
    if set(allowed['capabilities']) != CAPABILITIES:
        raise ValueError('append-only-grant-required')
    if [item['name'] for item in allowed.get('buckets') or []] != [bucket]:
        raise ValueError('single-bucket-grant-required')
    if allowed.get('namePrefix') != prefix:
        raise ValueError('node-prefix-grant-required')
    buckets = post(opener, storage['apiUrl'].rstrip('/') + '/b2api/v4/b2_list_buckets',
                   {'Authorization': auth['authorizationToken'], 'Content-Type': 'application/json'},
                   {'accountId': auth['accountId'], 'bucketName': bucket})['buckets']
    if len(buckets) != 1 or buckets[0]['bucketType'] != 'allPrivate':
        raise ValueError('private-bucket-required')
    # Hidden versions are the only copy left after a compromised node's sync deletes.
    rules = [rule for rule in buckets[0].get('lifecycleRules') or [] if prefix.startswith(rule['fileNamePrefix'])]
    if (len(rules) != 1 or rules[0].get('daysFromUploadingToHiding') is not None
            or (rules[0].get('daysFromHidingToDeleting') or 0) < RETENTION_DAYS):
        raise ValueError('hidden-version-retention-required')
    return 'backup-storage-grant-accepted'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--remote', required=True)
    parser.add_argument('--path', required=True)
    parser.add_argument('--host', required=True)
    args = parser.parse_args()
    opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
    try:
        outcome = check(sys.stdin.read(), args.remote, args.path, args.host, opener)
    except Exception as error:  # every failure is a refusal with one category
        category = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(f'backup-storage-grant-refused: {category}', file=sys.stderr)
        return 1
    print(outcome)
    return 0


if __name__ == '__main__':
    sys.exit(main())
