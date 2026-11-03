"""Validate the exact observer storage grant before credential delivery."""
import base64
import json
import os
from urllib import parse, request

CAPABILITIES = {'listBuckets', 'readBucketEncryption', 'readFiles', 'writeFiles'}


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate-field')
        value[key] = item
    return value


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('provider-redirect')


class StorageAuthority:
    def __init__(self, config):
        self.config = config
        pair = [os.environ.get(name, '') for name in ('B2_APPLICATION_KEY_ID', 'B2_APPLICATION_KEY')]
        if not all(pair):
            raise ValueError('storage-environment')
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
        basic = base64.b64encode((':'.join(pair)).encode()).decode()
        self.auth = self.json('https://api.backblazeb2.com/b2api/v4/b2_authorize_account',
                              headers={'Authorization': 'Basic ' + basic})
        storage = self.auth['apiInfo']['storageApi']
        self.api, self.download = self.origin(storage['apiUrl']), self.origin(storage['downloadUrl'])
        allowed = storage['allowed']
        if (allowed['buckets'] != [{'id': config['bucket_id'], 'name': config['bucket_name']}]
                or allowed['namePrefix'] != 'kuma/' or set(allowed['capabilities']) != CAPABILITIES):
            raise ValueError('dedicated-kuma-storage-grant-required')
        buckets = self.call('b2_list_buckets', {'accountId': self.auth['accountId'], 'bucketId': config['bucket_id']})['buckets']
        if (len(buckets) != 1 or buckets[0]['bucketId'] != config['bucket_id']
                or buckets[0]['bucketName'] != config['bucket_name'] or buckets[0]['bucketType'] != 'allPrivate'
                or buckets[0]['defaultServerSideEncryption']['value'] != {'algorithm': 'AES256', 'mode': 'SSE-B2'}):
            raise ValueError('private-encrypted-bucket-required')

    @staticmethod
    def origin(url):
        value = parse.urlsplit(url)
        if (value.scheme != 'https' or not value.hostname or not value.hostname.endswith('.backblazeb2.com')
                or value.username or value.password or value.port not in (None, 443)
                or value.path not in ('', '/') or value.query or value.fragment):
            raise ValueError('provider-origin')
        return url.rstrip('/')

    def json(self, url, *, data=None, headers=None):
        body = None if data is None else json.dumps(data, separators=(',', ':')).encode()
        outbound = request.Request(url, data=body, headers=headers or {})
        with self.opener.open(outbound, timeout=20) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('provider-response-limit')
        return json.loads(raw, object_pairs_hook=unique)

    def call(self, verb, data):
        return self.json(self.api + '/b2api/v4/' + verb, data=data,
                         headers={'Authorization': self.auth['authorizationToken'], 'Content-Type': 'application/json'})
