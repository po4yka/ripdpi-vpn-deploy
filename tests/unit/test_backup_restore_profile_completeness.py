"""Exercise selected restore artifacts with real encrypted restic snapshots."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / 'ansible/roles/backup/templates/vpn-backup-restore-drill.sh.j2'
BASELINE = {
    'etc/nftables.conf': 'table inet filter {}\n',
    'etc/ssh/sshd_config.d/20-ansible-hardening.conf': 'PasswordAuthentication no\n',
    'etc/sysctl.d/90-vpn.conf': 'net.ipv4.ip_forward = 1\n',
    'etc/systemd/system/synthetic.service': '[Service]\nExecStart=/bin/true\n',
    'etc/nginx/nginx.conf': 'events {}\n',
}
ARTIFACTS = {
    'snell': {'etc/snell/config.json': '{}'},
    'subscription-only': {'var/lib/vpn-subscription/revoked': '',
                          'etc/nginx/sites-available/vpn-sub.conf': 'server {}',
                          'etc/nginx/sites-enabled/vpn-sub.conf': 'server {}',
                          'etc/nginx/conf.d/vpn-sub-ratelimit.conf': 'synthetic',
                          'etc/nginx/tls/subscription-host/server.fullchain.pem': 'cert',
                          'etc/nginx/tls/subscription-host/server.key': 'key'},
    'naive': {'etc/naive/Caddyfile': 'synthetic', 'etc/naive/server.fullchain.pem': 'cert',
              'etc/naive/server.key': 'key'},
    'hysteria_realm': {'etc/hysteria-realm/config.json': '{}',
                       'etc/hysteria-realm/server.fullchain.pem': 'cert',
                       'etc/hysteria-realm/server.key': 'key'},
    'dns_morph_bridge': {'etc/dns-morph-bridge/dns-morph-bridge.yaml': 'synthetic',
                         'etc/unbound/unbound.conf.d/dns-morph-bridge-fwd.conf': 'synthetic'},
    'split_hop_ingress': {'etc/wireguard/owned-wg.conf': '[Interface]\n'},
    'split_hop_egress': {'etc/wireguard/owned-wg.conf': '[Interface]\n'},
    'cascade_ingress': {'etc/wireguard/owned-wg.conf': '[Interface]\n',
                         'etc/cascade/classifier-interface.json': '{}',
                         'etc/cascade/classifier-proxy.password': 'synthetic',
                         'etc/wireguard/cascade-ingress.nft': 'synthetic'},
    'cascade_egress': {'etc/wireguard/owned-wg.conf': '[Interface]\n'},
    'probe_matrix_target': {'etc/probe-matrix/xray.json': '{}',
                            'etc/probe-matrix/mtg.toml': 'synthetic',
                            'etc/probe-matrix/tls.crt': 'cert',
                            'etc/probe-matrix/tls.key': 'key',
                            'etc/nginx/sites-available/probe-matrix-tls.conf': 'server {}',
                            'etc/nginx/sites-enabled/probe-matrix-tls.conf': 'server {}'},
    'cdn_front': {'etc/nginx/sites-available/cdn-front.conf': 'server {}',
                   'etc/nginx/sites-enabled/cdn-front.conf': 'server {}',
                   'etc/nginx/tls/cdn.example.com.fullchain.pem': 'cert',
                   'etc/nginx/tls/cdn.example.com.key': 'key',
                   'etc/cdn-front/cloudflare.real_ip': 'synthetic',
                   'etc/cdn-front/cloudflare.v4': '192.0.2.0/24',
                   'etc/cdn-front/cloudflare.v6': '2001:db8::/32'},
    'watchdog': {'etc/vpn-watchdog.env': 'SYNTHETIC=1\n',
                 'etc/vpn-watchdog-notifications.json': '{}'},
}


def variables(profile: str, repository: Path) -> dict:
    values = merge_render_vars()
    values['vpn'] = {key: False for key in values['vpn']}
    values['backup']['remote']['enabled'] = False
    values['restic_repo_dir'] = str(repository)
    if profile == 'subscription-only':
        values['vpn_subscription_only'] = True
    else:
        values['vpn']['enable_' + profile] = True
    if profile in ('split_hop_ingress', 'split_hop_egress', 'cascade_ingress', 'cascade_egress'):
        values[profile] = {'wg_interface': 'owned-wg'}
    for key, path in [('naive', '/etc/naive'), ('hysteria_realm', '/etc/hysteria-realm'),
                      ('dns_morph_bridge', '/etc/dns-morph-bridge')]:
        values[key] = {'config_dir': path}
    values['subscription'] = {'subscription_dir': '/var/lib/vpn-subscription',
                              'revoked_file': '/var/lib/vpn-subscription/revoked'}
    values['cdn_front'] = {'server_name': 'cdn.example.com', 'cf_prefix_dir': '/etc/cdn-front'}
    return values


PASSWORD = 'synthetic-selected-profile-password\n'


@pytest.fixture(scope='module')
def empty_repository(tmp_path_factory) -> Path:
    """Initialize one real encrypted repository; each case backs up into its own copy.

    restic init spends most of a case's time on key derivation, and every copy keeps
    the same real key and format.
    """
    restic = shutil.which('restic')
    assert restic, 'real restic required for selected restore artifact coverage'
    root = tmp_path_factory.mktemp('restic-template')
    password = root / 'password'
    password.write_text(PASSWORD)
    password.chmod(0o600)
    env = {**os.environ, 'RESTIC_PASSWORD_FILE': str(password), 'RESTIC_CACHE_DIR': str(root / 'cache')}
    subprocess.run([restic, '-r', str(root / 'repository'), 'init'], env=env, check=True,
                   capture_output=True, timeout=45)
    return root / 'repository'


def run_drill(tmp_path: Path, template: Path, profile: str, *, missing: str | None = None,
              realm_link: str | None = None,
              malformed: str | None = None) -> tuple[subprocess.CompletedProcess, Path]:
    restic = shutil.which('restic')
    assert restic, 'real restic required for selected restore artifact coverage'
    tree = tmp_path / 'snapshot-source'
    for relative, content in {**BASELINE, **ARTIFACTS[profile]}.items():
        path = tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    if missing:
        (tree / missing).unlink()
    if malformed:
        (tree / malformed).write_text('{')
    sources = [str(tree)]
    if realm_link:
        external = tmp_path / 'external-tls'
        external.mkdir()
        for name in ('server.fullchain.pem', 'server.key'):
            target = external / name
            target.write_text('synthetic TLS bytes')
            link = tree / 'etc/hysteria-realm' / name
            link.unlink()
            link.symlink_to(target)
        if realm_link == 'captured':
            sources.append(str(external))
    repository = tmp_path / 'repository'
    shutil.copytree(template, repository)
    password = tmp_path / 'password'
    password.write_text(PASSWORD)
    password.chmod(0o600)
    runtime, state = tmp_path / 'runtime', tmp_path / 'state'
    runtime.mkdir(mode=0o700)
    state.mkdir(mode=0o700)
    marker = state / 'restore-drill-last-success.json'
    marker.write_text('{"prior":true}\n')
    env = {**os.environ, 'RESTIC_PASSWORD_FILE': str(password),
           'RESTIC_CACHE_DIR': str(tmp_path / 'cache'),
           'RUNTIME_DIRECTORY': str(runtime), 'STATE_DIRECTORY': str(state)}
    subprocess.run([restic, '-r', str(repository), 'backup', '--tag', 'vpn-stack', *sources],
                   env=env, check=True, capture_output=True, timeout=45)
    script = render_template(TEMPLATE, variables(profile, repository))
    script = script.replace('/etc/restic/password', str(password))
    prefix = str(tree).lstrip('/')
    for subtree in ('etc', 'var/lib/vpn-subscription'):
        script = script.replace('"' + subtree, '"' + prefix + '/' + subtree)
    result = subprocess.run(['bash', '-c', script], env=env, capture_output=True,
                            text=True, timeout=45)
    assert not (runtime / 'restore').exists()
    assert not list(runtime.iterdir())
    assert not list(state.glob('.restore-drill-last-success.json.*'))
    assert (tree / 'etc/nftables.conf').read_text() == BASELINE['etc/nftables.conf']
    return result, marker


@pytest.mark.parametrize('profile,missing', [
    (profile, artifact) for profile, artifacts in ARTIFACTS.items() for artifact in artifacts
])
def test_missing_selected_artifact_cannot_replace_success(tmp_path, empty_repository, profile, missing):
    result, marker = run_drill(tmp_path, empty_repository, profile, missing=missing)
    assert result.returncode != 0
    assert json.loads(marker.read_text()) == {'prior': True}


@pytest.mark.parametrize('profile', list(ARTIFACTS))
def test_complete_selected_profile_restores_and_cleans(tmp_path, empty_repository, profile):
    result, marker = run_drill(tmp_path, empty_repository, profile)
    assert result.returncode == 0, result.stderr
    assert json.loads(marker.read_text())['repository_source'] == 'local'


def test_malformed_snell_config_cannot_replace_success(tmp_path, empty_repository):
    result, marker = run_drill(tmp_path, empty_repository, 'snell', malformed='etc/snell/config.json')
    assert result.returncode != 0
    assert json.loads(marker.read_text()) == {'prior': True}


@pytest.mark.parametrize('mode', ['captured', 'live-only'])
def test_realm_absolute_tls_links_use_only_restored_targets(tmp_path, empty_repository, mode):
    result, marker = run_drill(tmp_path, empty_repository, 'hysteria_realm', realm_link=mode)
    if mode == 'captured':
        assert result.returncode == 0, result.stderr
        assert 'snapshot_id' in json.loads(marker.read_text())
    else:
        assert result.returncode != 0
        assert json.loads(marker.read_text()) == {'prior': True}
