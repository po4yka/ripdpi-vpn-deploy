#!/usr/bin/python3
"""Refresh client routing lists from a moving feed and publish only admitted pairs.

The feed is untrusted input that decides which destinations leave the tunnel, so
a candidate must satisfy the operator's policy before it replaces served files.
Any refusal leaves the previous generation in place.
"""

import hashlib
import http.client
import ipaddress
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CONFIG_PATH = '/etc/vpn-routing-lists.json'
FILES = ('geosite.dat', 'geoip.dat')
TIMEOUT_SECONDS = 60
GENERATIONS = 'generations'
KEEP_GENERATIONS = 2
MANIFEST = 'manifest.json'
# domain-list-community rule types.
PLAIN, REGEX, DOMAIN, FULL = 0, 1, 2, 3
# GeoIP entry field that makes a clean-looking list match everything else.
INVERSE_MATCH = 3
MAPPED_IPV4 = ipaddress.ip_network('::ffff:0:0/96')


class Refused(Exception):
    """A categorical refusal; the category is safe to log."""


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise Refused('feed-redirect-not-https')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, limit):
    opener = urllib.request.build_opener(_HttpsOnlyRedirects)
    request = urllib.request.Request(url, headers={'User-Agent': 'vpn-routing-lists'})
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(limit + 1)
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as error:
        raise Refused('feed-unreachable') from error
    if len(body) > limit:
        raise Refused('feed-too-large')
    return body


def _varint(data, offset):
    value = shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7f) << shift
        shift += 7
        if byte < 0x80:
            return value, offset
        if shift > 63:
            raise ValueError('varint')


def _fields(data):
    offset = 0
    while offset < len(data):
        key, offset = _varint(data, offset)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, offset = _varint(data, offset)
        elif wire == 2:
            size, offset = _varint(data, offset)
            value = data[offset:offset + size]
            if len(value) != size:
                raise ValueError('truncated')
            offset += size
        else:
            raise ValueError('wire-type')
        yield field, value


def _entries(data, parse_item):
    """Parse a v2ray list: repeated {1: tag, 2: repeated item}."""
    tags = {}
    try:
        for field, entry in _fields(data):
            if field != 1:
                continue
            tag, items = None, []
            for inner, value in _fields(entry):
                if inner == 1:
                    tag = value.decode().lower()
                elif inner == 2:
                    items.append(parse_item(value))
                elif inner == INVERSE_MATCH and value:
                    raise Refused('feed-unbounded-rule')
            # Clients may pick another duplicate than the one admitted here.
            if tag is None or tag in tags:
                raise ValueError('tag')
            tags[tag] = items
    except (ValueError, IndexError, TypeError, AttributeError) as error:
        raise Refused('feed-malformed') from error
    return tags


def _domain(raw):
    kind, value = PLAIN, ''
    for field, item in _fields(raw):
        if field == 1:
            kind = item
        elif field == 2:
            value = item.decode().lower()
    return kind, value


def _cidr(raw):
    address, prefix = b'', 0
    for field, item in _fields(raw):
        if field == 1:
            address = item
        elif field == 2:
            prefix = item
    return ipaddress.ip_network((address, prefix), strict=False)


def parse_geosite(data):
    return _entries(data, _domain)


def parse_geoip(data):
    return _entries(data, _cidr)


def _tags(rules, scheme):
    prefix = scheme + ':'
    return [rule[len(prefix):].lower() for rule in rules if rule.startswith(prefix)]


def _host(name):
    return name.lower().rstrip('.')


def _site_matches(host, tags, sites):
    for tag in tags:
        for kind, value in sites[tag]:
            if kind == DOMAIN and (host == value or host.endswith('.' + value)):
                return True
            if kind == FULL and host == value:
                return True
    return False


def admit(config, sites, addresses):
    """Refuse a candidate that could widen what leaves the tunnel."""
    profile = config['profile']
    policy = config['policy']
    direct_sites = _tags(profile['DirectSites'], 'geosite')
    direct_ips = _tags(profile['DirectIp'], 'geoip')
    referenced_sites = direct_sites + _tags(profile['ProxySites'] + profile.get('BlockSites', []), 'geosite')
    referenced_ips = direct_ips + _tags(profile['ProxyIp'] + profile.get('BlockIp', []), 'geoip')
    for tag in referenced_sites:
        if not sites.get(tag):
            raise Refused('feed-missing-tag')
    for tag in referenced_ips:
        if not addresses.get(tag):
            raise Refused('feed-missing-tag')

    allowed_labels = set(policy['single_label_allow'])
    for tag in direct_sites:
        for kind, value in sites[tag]:
            if kind not in (DOMAIN, FULL):
                raise Refused('feed-unbounded-rule')
            labels = value.split('.')
            if not all(labels) or (len(labels) < 2 and value not in allowed_labels):
                raise Refused('feed-broad-domain')
    for tag in direct_ips:
        for network in addresses[tag]:
            floor = policy['min_ipv4_prefix'] if network.version == 4 else policy['min_ipv6_prefix']
            if network.prefixlen < floor or (network.version == 6 and network.overlaps(MAPPED_IPV4)):
                raise Refused('feed-broad-network')

    for host in policy['must_direct']:
        if not _site_matches(_host(host), direct_sites, sites):
            raise Refused('feed-lost-required-direct')
    for host in policy['must_not_direct']:
        if _site_matches(_host(host), direct_sites, sites):
            raise Refused('feed-direct-canary')
    for literal in policy['must_not_direct_ips']:
        address = ipaddress.ip_address(literal)
        if any(address in network for tag in direct_ips for network in addresses[tag]):
            raise Refused('feed-direct-canary')


def _counts(config, sites, addresses):
    profile = config['profile']
    return {
        **{f'geosite:{tag}': len(sites[tag]) for tag in _tags(profile['DirectSites'], 'geosite')},
        **{f'geoip:{tag}': len(addresses[tag]) for tag in _tags(profile['DirectIp'], 'geoip')},
    }


def check_drift(config, previous, counts):
    ratio = config['policy']['max_change_ratio']
    for tag, count in counts.items():
        known = previous.get('counts', {}).get(tag)
        if known and not known / ratio <= count <= known * ratio:
            raise Refused('feed-size-drift')


def _current(root):
    """Read the manifest behind the served link, whichever token it belongs to."""
    manifests = []
    try:
        for name in os.listdir(root):
            if name.startswith('.') or not os.path.islink(os.path.join(root, name)):
                continue
            with open(os.path.join(root, name, MANIFEST), encoding='utf-8') as handle:
                manifests.append(json.load(handle))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise Refused('state-unreadable') from error
    return max(manifests, key=lambda manifest: manifest.get('published', 0), default={})


def _write(directory, name, data):
    path = os.path.join(directory, name)
    with open(path, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish(config, payloads, digests, counts, now):
    root, token = config['root'], config['token']
    generations = os.path.join(root, GENERATIONS)
    os.makedirs(generations, mode=0o750, exist_ok=True)
    # A run killed at its timeout cannot clean up after itself.
    for name in os.listdir(generations):
        if name.startswith('.stage-'):
            shutil.rmtree(os.path.join(generations, name), ignore_errors=True)
    # The setgid root and the unit's UMask keep generations readable by nginx's group only.
    stage = os.path.join(generations, f'.stage-{os.getpid()}')
    os.mkdir(stage)
    try:
        profile = dict(config['profile'])
        for key, name in (('Geositeurl', 'geosite.dat'), ('Geoipurl', 'geoip.dat')):
            profile[key] = f"{config['base_url']}/{name}"
        # INCY reloads the lists when this timestamp grows.
        profile['LastUpdated'] = str(now)
        for name in FILES:
            _write(stage, name, payloads[name])
            _write(stage, f'{name}.sha256', f'{digests[name]}  {name}\n'.encode())
        _write(stage, 'profile.json', json.dumps(profile, ensure_ascii=False, indent=2).encode())
        manifest = {'digests': digests, 'counts': counts, 'published': now}
        _write(stage, MANIFEST, json.dumps(manifest).encode())
        _sync_directory(stage)
        target = os.path.join(generations, f'{now}-{digests["geosite.dat"][:12]}')
        os.rename(stage, target)
        _sync_directory(generations)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    link = os.path.join(root, f'.{token}.next')
    if os.path.lexists(link):
        os.unlink(link)
    os.symlink(os.path.relpath(target, root), link)
    os.replace(link, os.path.join(root, token))
    # A rotated token stops resolving as soon as the new one is live.
    for name in os.listdir(root):
        if name != token and os.path.islink(os.path.join(root, name)):
            os.unlink(os.path.join(root, name))
    _sync_directory(root)
    active = os.path.basename(target)
    finished = sorted(name for name in os.listdir(generations) if not name.startswith('.'))
    for name in finished[:-KEEP_GENERATIONS]:
        if name != active:
            shutil.rmtree(os.path.join(generations, name), ignore_errors=True)


def refresh(config, now=None):
    limit = config['policy']['max_bytes']
    payloads, digests = {}, {}
    for name, key in (('geosite.dat', 'geosite_url'), ('geoip.dat', 'geoip_url')):
        body = download(config[key], limit)
        digest = hashlib.sha256(body).hexdigest()
        published = download(f'{config[key]}.sha256', 4096).split()
        if not published or published[0].decode('ascii', 'replace').lower() != digest:
            raise Refused('feed-digest-mismatch')
        payloads[name], digests[name] = body, digest
    sites = parse_geosite(payloads['geosite.dat'])
    addresses = parse_geoip(payloads['geoip.dat'])
    admit(config, sites, addresses)
    counts = _counts(config, sites, addresses)
    previous = _current(config['root'])
    # A new policy must be republished even when the feed did not move.
    identity = hashlib.sha256(
        json.dumps([config['profile'], config['base_url']], sort_keys=True).encode()).hexdigest()
    digests['profile'] = identity
    if previous.get('digests') == digests:
        return 'unchanged'
    check_drift(config, previous, counts)
    # INCY reloads only when the timestamp grows, even after a clock step.
    stamp = max(int(time.time()) if now is None else now, previous.get('published', 0) + 1)
    publish(config, payloads, digests, counts, stamp)
    return 'published'


def main():
    try:
        with open(CONFIG_PATH, encoding='utf-8') as handle:
            config = json.load(handle)
        print(f'routing-lists: {refresh(config)}')
        return 0
    except Refused as refusal:
        print(f'routing-lists: refused {refusal}', file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f'routing-lists: failed {type(error).__name__}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
