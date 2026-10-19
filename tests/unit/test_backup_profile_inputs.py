"""Exercise profile-selected backup, retention and integrity with real restic."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / 'ansible/roles/backup/templates/vpn-backup.sh.j2'


def rendered_profile(profile, tmp_path):
    variables = merge_render_vars()
    variables["xray_etc_dir"] = variables["xray_config_dir"]
    selected = 'vpn-device-full' if profile == 'subscription-only' else profile
    variables['vpn'] = yaml.safe_load((ROOT / f'ansible/group_vars/{selected}.yml').read_text())['vpn']
    if profile == 'subscription-only':
        variables['vpn_subscription_only'] = True
    variables['backup']['remote']['enabled'] = False
    variables['restic_repo_dir'] = str(tmp_path / 'repository')
    text = render_template(TEMPLATE, variables)
    # Isolate every production input under this fixture, retaining exact shape.
    text = text.replace('/etc/', str(tmp_path / 'etc') + '/')
    text = text.replace('/var/lib/vpn-subscription', str(tmp_path / 'subscription'))
    return text


def entries(text, name):
    result = []
    for entry in shlex.split(re.search(rf'{name}=\((.*?)\)', text, re.S)[1]):
        if entry == '${REALM_TLS_INPUTS[@]}':
            result.extend(entries(text, 'REALM_TLS_INPUTS'))
        else:
            result.append(Path(entry))
    return result


def provision(text):
    required_files = set(entries(text, 'REQUIRED_FILES'))
    for entry in entries(text, 'INCLUDES'):
        entry.parent.mkdir(parents=True, exist_ok=True)
        if entry in required_files or entry.name == 'nftables.conf' or entry.name.startswith('vpn-watchdog') or entry.name == 'revoked':
            entry.write_text('synthetic nonempty configuration\n')
        else:
            entry.mkdir(exist_ok=True)
    for entry in entries(text, 'REQUIRED_FILES'):
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text('synthetic required configuration\n')


@pytest.mark.parametrize('profile', ['vpn-p0-minimal', 'vpn-family-standard', 'vpn-device-full', 'subscription-only'])
@pytest.mark.parametrize('missing', [False, True])
def test_real_restic_selected_profile_pipeline(tmp_path, profile, missing):
    restic = shutil.which('restic')
    assert restic, 'real restic required for profile backup regression'
    text = rendered_profile(profile, tmp_path)
    provision(text)
    script = tmp_path / 'backup.sh'
    script.write_text(text)
    password = tmp_path / 'etc/restic/password'
    password.parent.mkdir(parents=True, exist_ok=True)
    password.write_text('synthetic-local-repository-password\n')
    password.chmod(0o600)
    state = tmp_path / 'state'
    state.mkdir(mode=0o700)
    env = {**os.environ, 'RESTIC_PASSWORD_FILE': str(password), 'STATE_DIRECTORY': str(state), 'RESTIC_CACHE_DIR': str(tmp_path / 'cache')}
    repo = tmp_path / 'repository'
    subprocess.run([restic, '-r', str(repo), 'init'], env=env, capture_output=True, check=True, timeout=30)
    required = entries(text, 'REQUIRED_FILES')
    if missing:
        required[-1].unlink()
    result = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True, timeout=60)
    marker = json.loads((state / 'backup-stage-status.json').read_text())
    if missing:
        assert result.returncode != 0
        assert marker['local_backup']['result'] == 'failed'
        assert marker['integrity']['result'] == 'pending'
        assert marker['remote_copy']['result'] == 'disabled'
    else:
        assert result.returncode == 0, result.stderr
        assert marker['local_backup']['result'] == 'success'
        assert marker['integrity']['result'] == 'success'
        listing = subprocess.run([restic, '-r', str(repo), 'ls', 'latest', '--json'], env=env, capture_output=True, text=True, check=True, timeout=30)
        saved = {item.get('path') for line in listing.stdout.splitlines() if (item := json.loads(line)).get('struct_type') == 'node'}
        assert all(str(path) in saved for path in required)
    for disabled in ['snell', 'naive', 'dns-morph-bridge']:
        assert not (tmp_path / 'etc' / disabled).exists()
    if profile == 'vpn-p0-minimal':
        assert not (tmp_path / 'etc/hysteria').exists()
        assert not (tmp_path / 'etc/nginx').exists()
    if profile == 'subscription-only':
        assert not (tmp_path / 'etc/xray').exists()
        assert not (tmp_path / 'etc/hysteria').exists()
        assert not (tmp_path / 'etc/vpn-watchdog-reality.json').exists()


def test_xhttp_only_selects_xray_and_disabled_watchdog_is_absent():
    variables = merge_render_vars()
    variables["xray_etc_dir"] = "/etc/xray-custom"
    variables["vpn"] = {"enable_xray_reality": False, "enable_nginx_xhttp": True,
                        "enable_hysteria": False, "enable_amneziawg": False,
                        "enable_watchdog": False}
    text = render_template(TEMPLATE, variables)
    assert Path("/etc/xray-custom") in entries(text, "INCLUDES")
    assert Path("/etc/xray-custom/config.json") in entries(text, "REQUIRED_FILES")
    assert Path("/etc/nginx") in entries(text, "INCLUDES")
    assert all("watchdog" not in str(item) for item in entries(text, "INCLUDES"))


def test_explicit_xray_etc_override_survives_real_backup_and_restore_drill(tmp_path):
    restic = shutil.which('restic')
    assert restic, 'real restic required for explicit Xray directory regression'
    variables = merge_render_vars()
    authoritative = tmp_path / 'authoritative-xray'
    legacy = tmp_path / 'unused-xray-alias'
    variables.update({
        'xray_etc_dir': str(authoritative), 'xray_config_dir': str(legacy),
        'restic_repo_dir': str(tmp_path / 'repository'),
        'vpn': {'enable_xray_reality': True, 'enable_nginx_xhttp': False,
                'enable_hysteria': False, 'enable_amneziawg': False,
                'enable_watchdog': False},
    })
    variables['backup']['remote']['enabled'] = False
    backup = render_template(TEMPLATE, variables).replace('/etc/', str(tmp_path / 'etc') + '/')
    provision(backup)
    config = authoritative / 'config.json'
    config.write_text('{"synthetic":true}\n')
    units = tmp_path / 'etc/systemd/system'
    (units / 'synthetic.service').write_text('[Service]\nExecStart=/bin/true\n')
    assert authoritative in entries(backup, 'INCLUDES')
    assert config in entries(backup, 'REQUIRED_FILES')
    assert not legacy.exists()

    password = tmp_path / 'etc/restic/password'
    password.parent.mkdir(parents=True, exist_ok=True)
    password.write_text('synthetic-override-repository-password\n')
    password.chmod(0o600)
    state = tmp_path / 'state'
    runtime = tmp_path / 'runtime'
    state.mkdir(mode=0o700)
    runtime.mkdir(mode=0o700)
    env = {**os.environ, 'RESTIC_PASSWORD_FILE': str(password),
           'STATE_DIRECTORY': str(state), 'RUNTIME_DIRECTORY': str(runtime),
           'RESTIC_CACHE_DIR': str(tmp_path / 'cache')}
    repo = tmp_path / 'repository'
    subprocess.run([restic, '-r', str(repo), 'init'], env=env, capture_output=True, check=True, timeout=30)
    script = tmp_path / 'backup.sh'
    script.write_text(backup)
    result = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr

    drill = render_template(TEMPLATE.parent / 'vpn-backup-restore-drill.sh.j2', variables)
    relative = str(tmp_path).lstrip('/')
    # restic preserves absolute snapshot input paths. Redirect only the fixed
    # baseline fixture paths to that sandbox hierarchy; keep Xray's rendered
    # authoritative selector intact and exercise its real JSON validation.
    drill = drill.replace('/etc/restic/password', str(password))
    drill = drill.replace('require_file "etc/', f'require_file "{relative}/etc/')
    drill = drill.replace('require_nonempty_directory "etc/', f'require_nonempty_directory "{relative}/etc/')
    assert f'require_file "{str(config).lstrip("/")}"' in drill
    assert str(legacy) not in drill
    script.write_text(drill)
    result = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    marker = json.loads((state / 'restore-drill-last-success.json').read_text())
    assert marker['repository_source'] == 'local'
    assert marker['snapshot_id']
    assert not (runtime / 'restore').exists()
    assert config.read_text() == '{"synthetic":true}\n'
    assert not legacy.exists()


@pytest.mark.parametrize('feature,missing', [
    ('hysteria_realm', 'cert'), ('hysteria_realm', 'key'),
    ('cascade_ingress', 'wireguard'), ('cascade_egress', 'wireguard'),
    ('split_hop_ingress', 'wireguard'), ('split_hop_egress', 'wireguard'),
    ('dns_morph_bridge', 'forwarding'),
])
def test_enabled_auxiliary_inputs_cannot_publish_success_when_missing(tmp_path, feature, missing):
    variables = merge_render_vars()
    variables['xray_etc_dir'] = '/etc/xray'
    variables['vpn'] = {'enable_xray_reality': False, 'enable_nginx_xhttp': False,
                        'enable_hysteria': False, 'enable_amneziawg': False,
                        'enable_watchdog': False, 'enable_' + feature: True}
    variables['backup']['remote']['enabled'] = False
    variables['hysteria_realm'] = {'config_dir': str(tmp_path / 'realm'),
                                 'tls_cert_path': str(tmp_path / 'tls/cert.pem'),
                                 'tls_key_path': str(tmp_path / 'tls/key.pem')}
    if feature in ('cascade_ingress', 'cascade_egress', 'split_hop_ingress', 'split_hop_egress'):
        variables[feature] = {'wg_interface': 'explicit-test-wg'}
    variables['dns_morph_bridge'] = {'config_dir': str(tmp_path / 'bridge')}
    text = render_template(TEMPLATE, variables).replace('/etc/', str(tmp_path / 'etc') + '/')
    provision(text)
    if missing == 'cert':
        absent = Path(variables['hysteria_realm']['tls_cert_path'])
    elif missing == 'key':
        absent = Path(variables['hysteria_realm']['tls_key_path'])
    elif missing == 'wireguard':
        absent = tmp_path / 'etc/wireguard/explicit-test-wg.conf'
    else:
        absent = tmp_path / 'etc/unbound/unbound.conf.d/dns-morph-bridge-fwd.conf'
    assert absent in entries(text, 'REQUIRED_FILES')
    absent.unlink()
    state = tmp_path / 'state'
    state.mkdir(mode=0o700)
    result = subprocess.run(['bash', '-c', text], env={**os.environ, 'STATE_DIRECTORY': str(state)},
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    marker = json.loads((state / 'backup-stage-status.json').read_text())
    assert marker['local_backup']['result'] == 'failed'
    assert marker['integrity']['result'] == 'pending'
    assert marker['remote_copy']['result'] == 'disabled'
    assert 'restic' not in result.stderr.lower()


def test_real_restic_realm_tls_symlink_dependencies_are_captured(tmp_path):
    restic = shutil.which('restic')
    assert restic, 'real restic required for Realm TLS dependency regression'
    variables = merge_render_vars()
    variables['vpn'] = {'enable_xray_reality': False, 'enable_nginx_xhttp': False,
                        'enable_hysteria': False, 'enable_amneziawg': False,
                        'enable_watchdog': False, 'enable_hysteria_realm': True}
    realm = tmp_path / 'realm'
    variables['hysteria_realm'] = {'config_dir': str(realm), 'tls_cert_path': str(realm / 'cert.pem'),
                                 'tls_key_path': str(realm / 'key.pem')}
    variables['restic_repo_dir'] = str(tmp_path / 'repository')
    variables['backup']['remote']['enabled'] = False
    text = render_template(TEMPLATE, variables).replace('/etc/', str(tmp_path / 'etc') + '/')
    provision(text)
    dependencies = tmp_path / 'external-tls'
    dependencies.mkdir()
    for entry in entries(text, 'REALM_TLS_INPUTS'):
        target = dependencies / entry.name
        target.write_text('synthetic TLS authority bytes\n')
        entry.unlink()
        entry.symlink_to(target)
    password = tmp_path / 'etc/restic/password'
    password.parent.mkdir(parents=True, exist_ok=True)
    password.write_text('synthetic-realm-repository-password\n')
    password.chmod(0o600)
    state = tmp_path / 'state'
    state.mkdir(mode=0o700)
    env = {**os.environ, 'STATE_DIRECTORY': str(state), 'RESTIC_PASSWORD_FILE': str(password),
           'RESTIC_CACHE_DIR': str(tmp_path / 'cache')}
    subprocess.run([restic, '-r', variables['restic_repo_dir'], 'init'], env=env, capture_output=True, check=True, timeout=30)
    result = subprocess.run(['bash', '-c', text], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    restored = tmp_path / 'restored'
    subprocess.run([restic, '-r', variables['restic_repo_dir'], 'restore', 'latest', '--target', str(restored)],
                   env=env, capture_output=True, check=True, timeout=30)
    for entry in entries(text, 'REALM_TLS_INPUTS'):
        assert (restored / str(entry).lstrip('/')).is_symlink()
        captured_target = restored / str(entry.resolve()).lstrip('/')
        assert captured_target.read_bytes() == entry.resolve().read_bytes()


@pytest.mark.parametrize('profile', ['cdn_front', 'hysteria_realm'])
@pytest.mark.parametrize('parent_link', [False, True])
@pytest.mark.parametrize('fault', [None, 'cycle', 'missing', 'too-many-links'])
def test_real_restic_tls_multihop_dependencies_survive_restore(tmp_path, profile, parent_link, fault):
    restic = shutil.which('restic')
    assert restic, 'real restic required for complete TLS symlink recovery'
    variables = merge_render_vars()
    variables['vpn'] = {key: False for key in variables['vpn']}
    variables['vpn']['enable_' + profile] = True
    variables['backup']['remote']['enabled'] = False
    variables['restic_repo_dir'] = str(tmp_path / 'repository')
    variables['hysteria_realm'] = {'config_dir': str(tmp_path / 'realm'),
                                 'tls_cert_path': str(tmp_path / 'realm/cert.pem'),
                                 'tls_key_path': str(tmp_path / 'realm/key.pem')}
    variables['cdn_front']['aop_cert_path'] = '/etc/nginx/aop.pem'
    variables['cdn_front']['server_name'] = 'cdn.example.com'
    text = render_template(TEMPLATE, variables).replace('/etc/', str(tmp_path / 'etc') + '/')
    assert all(path.is_absolute() for path in entries(text, 'REQUIRED_FILES'))
    provision(text)
    configured = (entries(text, 'REALM_TLS_INPUTS') if profile == 'hysteria_realm'
                  else [tmp_path / 'etc/nginx/aop.pem'])
    outside = tmp_path / 'outside-authority'
    authority = outside / 'authority'
    authority.mkdir(parents=True)
    unrelated = authority / 'unrelated-private-input'
    unrelated.write_text('unselected private fixture\n')
    alias = outside / 'active'
    if parent_link:
        alias.symlink_to('authority', target_is_directory=True)
    captured_links = [alias] if parent_link else []
    for entry in configured:
        target = outside / ('final-' + entry.name)
        target.write_bytes(b'synthetic complete TLS authority\n')
        middle = authority / ('current-' + entry.name)
        middle.symlink_to('../' + target.name)
        entry.unlink(missing_ok=True)
        entry.symlink_to((alias if parent_link else authority) / middle.name)
        captured_links.extend([entry, middle])
    if fault:
        middle = authority / ('current-' + configured[0].name)
        middle.unlink()
        if fault == 'cycle':
            middle.symlink_to(middle.name)
        elif fault == 'missing':
            middle.symlink_to('private-canary-missing.pem')
        else:
            middle.symlink_to('hop-0')
            for index in range(40):
                (authority / ('hop-' + str(index))).symlink_to(
                    'hop-' + str(index + 1) if index < 39 else '../final-' + configured[0].name)
    password = tmp_path / 'etc/restic/password'
    password.parent.mkdir(parents=True, exist_ok=True)
    password.write_text('synthetic-multihop-repository-password\n')
    password.chmod(0o600)
    state = tmp_path / 'state'
    state.mkdir(mode=0o700)
    env = {**os.environ, 'STATE_DIRECTORY': str(state), 'RESTIC_PASSWORD_FILE': str(password),
           'RESTIC_CACHE_DIR': str(tmp_path / 'cache')}
    if not fault:
        subprocess.run([restic, '-r', variables['restic_repo_dir'], 'init'], env=env,
                       capture_output=True, check=True, timeout=30)
    result = subprocess.run(['bash', '-c', text], env=env, capture_output=True, text=True, timeout=60, check=False)
    marker = json.loads((state / 'backup-stage-status.json').read_text())
    if fault:
        assert result.returncode != 0
        assert marker['local_backup']['result'] == 'failed'
        assert marker['integrity']['result'] == 'pending'
        assert marker['remote_copy']['result'] == 'disabled'
        assert 'private-canary' not in result.stderr
        assert result.stderr.strip() == 'backup: required enabled TLS authority is absent'
        assert not Path(variables['restic_repo_dir']).exists()
        return
    assert result.returncode == 0, result.stderr
    assert marker['local_backup']['result'] == marker['integrity']['result'] == 'success'
    restored = tmp_path / 'restored'
    subprocess.run([restic, '-r', variables['restic_repo_dir'], 'restore', 'latest', '--target', str(restored)],
                   env=env, capture_output=True, check=True, timeout=30)
    for link in captured_links:
        archived = restored / str(link).lstrip('/')
        assert archived.is_symlink(), f'missing archived TLS link: {link.name}'
        assert os.readlink(archived) == os.readlink(link)
    assert not (restored / str(unrelated).lstrip('/')).exists()
    drill = (ROOT / 'ansible/roles/backup/templates/vpn-backup-restore-drill.sh.j2').read_text()
    resolver = re.search(r'restored_path\(\) \{.*?\n\}', drill, re.DOTALL)[0]
    for entry in configured:
        expected = entry.read_bytes()
        resolved = subprocess.run(['bash', '-c', 'restore_target=$1\n' + resolver + '\nrestored_path "$2"',
                                   'restored-tls', str(restored), str(entry).lstrip('/')],
                                  capture_output=True, text=True, timeout=15, check=False)
        assert resolved.returncode == 0, resolved.stderr
        recovered = Path(resolved.stdout.strip())
        assert recovered.is_relative_to(restored)
        assert recovered.read_bytes() == expected
