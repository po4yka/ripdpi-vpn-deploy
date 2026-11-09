"""The routing-list refresher publishes admitted feeds and keeps serving otherwise."""
import hashlib
import http.server
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import threading

from jinja2 import Environment
import pytest

ROLE = Path(__file__).resolve().parents[2] / 'ansible/roles/subscription-host'
SPEC = importlib.util.spec_from_file_location('routing_lists_refresh', ROLE / 'files/routing_lists_refresh.py')
refresh_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh_module)
Refused = refresh_module.Refused

SITE_URL = 'https://feed.example.net/geosite.dat'
IP_URL = 'https://feed.example.net/geoip.dat'
DOMAIN, FULL, REGEX = 2, 3, 1


def varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7f
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def field(number, payload):
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def number(index, value):
    return varint(index << 3) + varint(value)


def geosite(tags):
    def rule(kind, value):
        return number(1, kind) + field(2, value.encode())
    return b''.join(
        field(1, field(1, tag.upper().encode()) + b''.join(field(2, rule(*item)) for item in items))
        for tag, items in tags.items())


def geoip(tags):
    def cidr(address, prefix):
        return field(1, ipaddress.ip_address(address).packed) + number(2, prefix)
    return b''.join(
        field(1, field(1, tag.upper().encode()) + b''.join(field(2, cidr(*item)) for item in items))
        for tag, items in tags.items())


GOOD_SITES = {
    'allow': [(DOMAIN, 'service.example.net'), (FULL, 'exact.example.net')],
    'proxied': [(DOMAIN, 'video.example.org')],
}
GOOD_IPS = {'allow': [('198.51.100.0', 24)]}


@pytest.fixture
def feed(monkeypatch):
    state = {'sites': dict(GOOD_SITES), 'ips': dict(GOOD_IPS), 'overrides': {}}

    def fake_download(url, limit):
        if url in state['overrides']:
            return state['overrides'][url]
        if url == SITE_URL:
            return geosite(state['sites'])
        if url == IP_URL:
            return geoip(state['ips'])
        body = fake_download(url.removesuffix('.sha256'), limit)
        return f'{hashlib.sha256(body).hexdigest()}  release/file\n'.encode()

    monkeypatch.setattr(refresh_module, 'download', fake_download)
    return state


@pytest.fixture
def config(tmp_path):
    return {
        'root': str(tmp_path), 'token': 'A' * 24, 'base_url': 'https://sub.example.net:8444/routing/' + 'A' * 24,
        'geosite_url': SITE_URL, 'geoip_url': IP_URL,
        'profile': {
            'Name': 'Direct allowlist', 'GlobalProxy': 'true',
            'DirectSites': ['geosite:allow', 'domain:extra.example.net'],
            'DirectIp': ['geoip:allow', '10.0.0.0/8'],
            'ProxySites': ['geosite:proxied'], 'ProxyIp': [],
        },
        'policy': {
            'max_bytes': 1 << 20, 'max_change_ratio': 2, 'min_ipv4_prefix': 12, 'min_ipv6_prefix': 28,
            'single_label_allow': [],
            'must_direct': ['service.example.net'], 'must_not_direct': ['blocked.example.org'],
            'must_not_direct_ips': ['192.0.2.1'],
        },
    }


def served(config, name):
    return Path(config['root'], config['token'], name)


def test_published_generation_is_what_incy_downloads(feed, config):
    assert refresh_module.refresh(config, now=1000) == 'published'
    body = served(config, 'geosite.dat').read_bytes()
    assert body == geosite(GOOD_SITES)
    assert served(config, 'geosite.dat.sha256').read_text().split()[0] == hashlib.sha256(body).hexdigest()
    profile = json.loads(served(config, 'profile.json').read_text())
    assert profile['Geositeurl'] == config['base_url'] + '/geosite.dat'
    assert profile['Geoipurl'] == config['base_url'] + '/geoip.dat'
    assert profile['LastUpdated'] == '1000'
    assert profile['GlobalProxy'] == 'true'
    assert os.path.islink(Path(config['root'], config['token']))


def test_unchanged_feed_keeps_the_timestamp_clients_compare(feed, config):
    refresh_module.refresh(config, now=1000)
    assert refresh_module.refresh(config, now=2000) == 'unchanged'
    assert json.loads(served(config, 'profile.json').read_text())['LastUpdated'] == '1000'


def test_policy_change_republishes_an_unchanged_feed(feed, config):
    refresh_module.refresh(config, now=1000)
    config['profile']['Name'] = 'Renamed'
    assert refresh_module.refresh(config, now=2000) == 'published'
    assert json.loads(served(config, 'profile.json').read_text())['Name'] == 'Renamed'


def test_old_generations_are_bounded_without_touching_the_active_one(feed, config):
    for index in range(1, 5):
        feed['sites'] = {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + [(DOMAIN, f'n{index}.example.net')]}
        refresh_module.refresh(config, now=1000 + index)
    assert len(os.listdir(Path(config['root'], 'generations'))) == 2
    assert served(config, 'manifest.json').exists()


@pytest.mark.parametrize('change, category', [
    ({'sites': {k: v for k, v in GOOD_SITES.items() if k != 'proxied'}}, 'feed-missing-tag'),
    ({'ips': {}}, 'feed-missing-tag'),
    ({'sites': {**GOOD_SITES, 'allow': [(FULL, 'exact.example.net')]}}, 'feed-lost-required-direct'),
    ({'sites': {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + [(DOMAIN, 'blocked.example.org')]}}, 'feed-direct-canary'),
    ({'sites': {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + [(DOMAIN, 'example.org')]}}, 'feed-direct-canary'),
    ({'sites': {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + [(DOMAIN, 'com')]}}, 'feed-broad-domain'),
    ({'sites': {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + [(REGEX, '.*')]}}, 'feed-unbounded-rule'),
    ({'ips': {**GOOD_IPS, 'allow': GOOD_IPS['allow'] + [('8.0.0.0', 8)]}}, 'feed-broad-network'),
    ({'ips': {**GOOD_IPS, 'allow': GOOD_IPS['allow'] + [('192.0.2.0', 24)]}}, 'feed-direct-canary'),
    ({'ips': {**GOOD_IPS, 'allow': GOOD_IPS['allow'] + [('2001:db8::', 16)]}}, 'feed-broad-network'),
    ({'ips': {**GOOD_IPS, 'allow': GOOD_IPS['allow'] + [('::ffff:0:0', 96)]}}, 'feed-broad-network'),
    ({'sites': {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + [(DOMAIN, 'com.')]}}, 'feed-broad-domain'),
])
def test_unsafe_candidate_keeps_the_previous_generation(feed, config, change, category):
    refresh_module.refresh(config, now=1000)
    before = served(config, 'geosite.dat').read_bytes()
    feed.update(change)
    with pytest.raises(Refused, match=category):
        refresh_module.refresh(config, now=2000)
    assert served(config, 'geosite.dat').read_bytes() == before
    assert json.loads(served(config, 'profile.json').read_text())['LastUpdated'] == '1000'


def test_allowlisted_single_label_is_admitted(feed, config):
    feed['sites'] = {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + [(DOMAIN, 'brand')]}
    config['policy']['single_label_allow'] = ['brand']
    assert refresh_module.refresh(config, now=1000) == 'published'


def test_canary_spelling_cannot_disable_itself(feed, config):
    feed['sites'] = {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + [(DOMAIN, 'blocked.example.org')]}
    config['policy']['must_not_direct'] = ['Blocked.Example.ORG.']
    with pytest.raises(Refused, match='feed-direct-canary'):
        refresh_module.refresh(config, now=1000)


def test_duplicate_tag_refuses(feed, config):
    clean = field(1, field(1, b'ALLOW') + field(2, number(1, DOMAIN) + field(2, b'service.example.net')))
    feed['overrides'][SITE_URL] = geosite(GOOD_SITES) + clean
    with pytest.raises(Refused, match='feed-malformed'):
        refresh_module.refresh(config, now=1000)


def test_inverted_geoip_tag_refuses(feed, config):
    inverted = field(1, field(1, b'allow') + field(2, field(1, bytes(4)) + number(2, 24)) + number(3, 1))
    feed['overrides'][IP_URL] = inverted
    with pytest.raises(Refused, match='feed-unbounded-rule'):
        refresh_module.refresh(config, now=1000)


def test_tag_sent_as_integer_is_categorised(feed, config):
    feed['overrides'][SITE_URL] = field(1, number(1, 7))
    with pytest.raises(Refused, match='feed-malformed'):
        refresh_module.refresh(config, now=1000)


def test_missing_block_tag_refuses(feed, config):
    config['profile']['BlockSites'] = ['geosite:absent']
    with pytest.raises(Refused, match='feed-missing-tag'):
        refresh_module.refresh(config, now=1000)


def test_new_address_republishes_an_unchanged_feed(feed, config):
    refresh_module.refresh(config, now=1000)
    config['base_url'] = 'https://other.example.net:8444/routing/' + 'A' * 24
    assert refresh_module.refresh(config, now=2000) == 'published'
    assert json.loads(served(config, 'profile.json').read_text())['Geoipurl'].startswith('https://other.')


def test_timestamp_grows_after_a_clock_step(feed, config):
    refresh_module.refresh(config, now=5000)
    feed['sites'] = {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + [(DOMAIN, 'new.example.net')]}
    refresh_module.refresh(config, now=100)
    assert json.loads(served(config, 'profile.json').read_text())['LastUpdated'] == '5001'


def test_rotated_token_stops_resolving(feed, config):
    refresh_module.refresh(config, now=1000)
    old = Path(config['root'], config['token'])
    config['token'] = 'B' * 24
    config['profile']['Name'] = 'Rotated'
    refresh_module.refresh(config, now=2000)
    assert not os.path.lexists(old)
    assert served(config, 'profile.json').exists()


def test_rotated_token_keeps_the_drift_baseline(feed, config):
    grown = [(DOMAIN, f'n{index}.example.net') for index in range(10)]
    feed['sites'] = {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + grown}
    refresh_module.refresh(config, now=1000)
    old = served(config, 'profile.json').read_text()
    feed['sites'] = {**GOOD_SITES, 'allow': GOOD_SITES['allow'][:1]}
    rotated = {**config, 'token': 'B' * 24}
    with pytest.raises(Refused, match='feed-size-drift'):
        refresh_module.refresh(rotated, now=2000)
    assert served(config, 'profile.json').read_text() == old


def test_stale_stage_from_a_killed_run_is_cleared(feed, config):
    refresh_module.refresh(config, now=1000)
    stale = Path(config['root'], 'generations', '.stage-killed')
    stale.mkdir()
    config['profile']['Name'] = 'Next'
    refresh_module.refresh(config, now=2000)
    assert not stale.exists()


def test_download_stops_at_the_byte_cap():
    class Large(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'x' * 2048)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Large)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(Refused, match='feed-too-large'):
            refresh_module.download(f'http://127.0.0.1:{server.server_port}/list', 1024)
    finally:
        server.shutdown()


def _routing_location():
    template = (ROLE / 'templates/subscription.conf.j2').read_text()
    environment = Environment()
    environment.filters['bool'] = bool
    rendered = environment.from_string(template).render(
        subscription={'routing_lists': {'enabled': True}, 'server_name': 'sub.example.net', 'port': 8444},
        vpn={}, nginx_xhttp={'server_name': 'sub.example.net'}, subscription_port=8444)
    return re.search(r'location ~ "(\^/routing/[^"]+)"', rendered).group(1).replace('(?<', '(?P<')


@pytest.mark.parametrize('name', [
    'profile.json', 'geosite.dat', 'geosite.dat.sha256', 'geoip.dat', 'geoip.dat.sha256'])
def test_nginx_serves_client_files(name):
    assert re.fullmatch(_routing_location(), f'/routing/{"A" * 24}/{name}')


@pytest.mark.parametrize('path', [
    f'/routing/{"A" * 24}/manifest.json', f'/routing/{"A" * 24}/../manifest.json', '/routing/short/profile.json'])
def test_nginx_does_not_serve_other_paths(path):
    assert not re.fullmatch(_routing_location(), path)


def test_digest_mismatch_refuses(feed, config):
    feed['overrides'][SITE_URL + '.sha256'] = b'0' * 64 + b'  geosite.dat\n'
    with pytest.raises(Refused, match='feed-digest-mismatch'):
        refresh_module.refresh(config, now=1000)
    assert not Path(config['root'], config['token']).exists()


def test_truncated_list_refuses(feed, config):
    feed['overrides'][SITE_URL] = geosite(GOOD_SITES)[:-3]
    with pytest.raises(Refused, match='feed-malformed'):
        refresh_module.refresh(config, now=1000)


@pytest.mark.parametrize('count', [1, 20])
def test_sudden_size_change_refuses(feed, config, count):
    grown = [(DOMAIN, f'n{index}.example.net') for index in range(10)]
    feed['sites'] = {**GOOD_SITES, 'allow': GOOD_SITES['allow'] + grown}
    refresh_module.refresh(config, now=1000)
    extra = [(DOMAIN, f'm{index}.example.net') for index in range(count * 3)]
    feed['sites'] = {**GOOD_SITES, 'allow': GOOD_SITES['allow'][:1] + (extra if count > 1 else [])}
    with pytest.raises(Refused, match='feed-size-drift'):
        refresh_module.refresh(config, now=2000)


def test_redirect_to_plain_http_is_refused():
    handler = refresh_module._HttpsOnlyRedirects()
    with pytest.raises(Refused, match='feed-redirect-not-https'):
        handler.redirect_request(None, None, 302, 'Found', {}, 'http://feed.example.net/x')
