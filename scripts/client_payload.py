"""Canonical in-memory client materialization shared by delivery and inspection."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import time

import yaml

from awg_client import export as awg_export, host_context
from awg_device_binding import resolve_binding
from encrypted_client_document import MAX_BYTES, private_file, identity
from transport_semantics import hysteria_client_bandwidth, transport_errors, xhttp_endpoints, xhttp_tuning
from fleet_inspection import bounded_command, InspectionError
from payload_failover_policy import validate_policy

ROOT = Path(__file__).resolve().parents[1]
DEADLINE = None

HOST = re.compile(r'[a-z0-9][a-z0-9_-]*:[a-z0-9][a-z0-9_-]*')


def command(argv, *, env=None, data=None):
    remaining = 30 if DEADLINE is None else min(30, DEADLINE - time.monotonic())
    if remaining <= 0:
        raise ValueError('payload-deadline-exceeded')
    try:
        return bounded_command(argv, input_bytes=data or b'', input_limit=MAX_BYTES, environment=env if env is not None else os.environ.copy(), timeout=remaining, limit=MAX_BYTES)
    except InspectionError:
        raise ValueError('payload-input-unavailable') from None



def read_document(path, *, plaintext=False):
    parent_info = Path(path).absolute().parent.stat()
    if parent_info.st_uid != os.getuid() or parent_info.st_mode & 0o022:
        raise ValueError('unsafe-private-document-directory')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(descriptor, 'rb') as handle:
        before = os.fstat(handle.fileno()) if plaintext else private_file(handle.fileno())
        if plaintext and (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1 or before.st_mode & 0o077):
            raise ValueError('unsafe-plaintext-input')
        if before.st_size > MAX_BYTES:
            raise ValueError('private-document-too-large')
        data = handle.read(MAX_BYTES + 1)
        if identity(before) != identity(os.fstat(handle.fileno())):
            raise ValueError('private-document-changed')
    if not plaintext:
        data = command(['sops', '--decrypt', '--input-type', 'json' if Path(path).suffix == '.json' else 'yaml',
                         '--output-type', 'json', '/dev/stdin'], data=data)
    doc = yaml.safe_load(data) if plaintext else json.loads(data)
    if not isinstance(doc, dict):
        raise ValueError('invalid-private-document')
    return doc


def paths(hosts):
    per_host = os.environ.get('SOPS_FILES', '').split(',') if os.environ.get('SOPS_FILES') else []
    if per_host and len(per_host) != len(hosts):
        raise ValueError('invalid-private-input-selection')
    if 'VPN_SECRETS_FILE' in os.environ:
        if per_host:
            raise ValueError('plaintext secrets cannot be combined with SOPS_FILES')
        return [os.environ['VPN_SECRETS_FILE']] * len(hosts)
    return per_host or [os.environ.get('SOPS_FILE') or str(Path.home() / '.config/vpn-provision' / (h.split(':')[1] + '.secrets.sops.yaml')) for h in hosts]


def options(format, *, hosts=None, cohorts=None, awg_host=None, expires='', utls=None):
    result = dict(format=format, hosts=hosts if hosts is not None else (os.environ.get('HOSTS') or os.environ.get('PROVIDER', 'upcloud') + ':' + os.environ.get('ENV', 'prod')).split(','),
                  cohorts=cohorts if cohorts is not None else list(filter(None, os.environ.get('COHORTS', '').split(','))),
                  awg_host=awg_host if awg_host is not None else os.environ.get('AWG_HOST', ''),
                  expires=expires, utls=utls if utls is not None else os.environ.get('UTLS_FINGERPRINT', ''))
    validate_options(result)
    return result


def validate_options(o):
    if (not isinstance(o, dict) or set(o) != {'format', 'hosts', 'cohorts', 'awg_host', 'expires', 'utls'}
            or o['format'] not in ('singbox', 'ripdpi', 'xray') or not isinstance(o['hosts'], list) or not o['hosts']
            or any(not isinstance(h, str) or not HOST.fullmatch(h) for h in o['hosts'])
            or not isinstance(o['cohorts'], list) or (o['cohorts'] and len(o['cohorts']) != len(o['hosts']))
            or any(not isinstance(c, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,62}', c) for c in o['cohorts'])
            or not isinstance(o['awg_host'], str) or (o['awg_host'] and o['awg_host'] not in o['hosts'])
            or not isinstance(o['expires'], str) or not isinstance(o['utls'], str)):
        raise ValueError('invalid-delivery-options')


def required_text(value):
    if not isinstance(value, str) or not value:
        raise ValueError('missing-consumed-authority')
    return value


def context(cohort):
    merged = yaml.safe_load((ROOT / 'ansible/roles/snell/defaults/main.yml').read_text()) or {}
    def merge(base, extra):
        for k, v in extra.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                merge(base[k], v)
            else:
                base[k] = copy.deepcopy(v)
    for name in ('all', 'vpn', *(['vpn-' + cohort] if cohort else [])):
        path = ROOT / 'ansible/group_vars' / (name + '.yml')
        if path.exists():
            merge(merged, yaml.safe_load(path.read_text()) or {})
        elif cohort:
            raise ValueError('missing-profile-cohort')
    merged.pop('public_site_canonical_url', None)
    return merged


def inventory_cohort(hostname):
    path = ROOT / 'ansible/inventory/generated.ini'
    section = ''
    for line in path.read_text().splitlines() if path.exists() else []:
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
        elif line and not line.startswith('#') and line.split()[0] == hostname and section.startswith('vpn-') and ':' not in section:
            return section[4:]
    return ''


def materialize(client, o, **kwargs):
    global DEADLINE
    previous = DEADLINE
    DEADLINE = min(previous if previous is not None else float('inf'), time.monotonic() + 60)
    try:
        return _materialize(client, o, **kwargs)
    finally:
        DEADLINE = previous


def _materialize(client, o, *, documents=None, source_paths=None, private_only=False, per_app_bypass='', per_app_via_tun='', extended=False, xhttp_only=False, endpoints=None):
    validate_options(o)
    if o['format'] == 'xray' and (per_app_bypass or per_app_via_tun or o['expires']):
        raise ValueError('unsupported-native-xhttp-options')
    if extended and o['format'] != 'ripdpi':
        raise ValueError('bundle requires RIPDPI format')
    if xhttp_only and (o['format'] != 'ripdpi' or extended):
        raise ValueError('--xhttp-only requires --profile-format ripdpi')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', client):
        raise ValueError('invalid-client')
    sources = source_paths if source_paths is not None else paths(o['hosts'])
    if not isinstance(sources, list) or len(sources) != len(o['hosts']) or any(not isinstance(p, str) or not p for p in sources):
        raise ValueError('invalid-private-input-selection')
    loaded = {} if documents is None else dict(documents)
    out, snell, awg, extras = [], [], [], {}
    topology = {'split_hop_egress': False, 'hysteria_realm': None}
    awg_enabled = False
    bindings = []
    failover_policies = []
    for i, host in enumerate(o['hosts']):
        source = str(Path(sources[i]).absolute())
        if source not in loaded:
            loaded[source] = read_document(source, plaintext=not private_only and 'VPN_SECRETS_FILE' in os.environ)
        d = loaded[source]
        provider, environment = host.split(':')
        env = dict(os.environ, PROVIDER=provider, ENV=environment)
        ip = (endpoints[host] if endpoints is not None else command([str(ROOT / 'scripts/terraform-env.sh'), 'output', '-raw', 'server_ipv4'], env=env).decode().strip())
        cohort = o['cohorts'][i] if o['cohorts'] else inventory_cohort(command(
            [str(ROOT / 'scripts/terraform-env.sh'), 'output', '-raw', 'server_hostname'], env=env).decode().strip())
        c = context(cohort)
        if extended:
            failover_policies.append(validate_policy(c.get('client_payload_failover')))
        errors = transport_errors(d, c)
        if errors:
            raise ValueError('invalid-transport-input')
        vpn = c.get('vpn', {})
        enabled = lambda key, default=False: vpn.get(key, default) and (not (xhttp_only or o['format'] == 'xray') or key == 'enable_nginx_xhttp')
        awg_enabled |= enabled('enable_amneziawg')
        tag = provider + '-' + environment
        fp = o['utls'] or c.get('xray_utls_fingerprint', 'chrome')
        x = d.get('xray', {})
        selected = [v for v in x.get('clients', []) if v.get('name') == client]
        if enabled('enable_xray_reality', True) or (o['format'] in ('ripdpi', 'xray') and enabled('enable_nginx_xhttp', True)):
            if len(selected) != 1:
                raise ValueError('missing-selected-xray-client')
        credential = selected[0] if selected else {}
        if enabled('enable_xray_reality', True):
            server_names = x.get('server_names')
            reality_key = x.get('reality_public_key')
            if (not isinstance(server_names, list) or not server_names
                    or not isinstance(server_names[0], str) or not server_names[0]
                    or not isinstance(reality_key, str) or not reality_key):
                raise ValueError('missing-selected-reality-authority')
            flow = vpn.get('xray_flow_mode') or c.get('p0_reality_flow_mode', 'vision')
            shapes = c.get('p0_reality_shapes', {})
            finalmask = vpn.get('xray_finalmask', shapes[flow]['finalmask'])
            cohorts = x.get('cohorts', [])
            members = [v for v in cohorts if client in v['clients']]
            if cohorts and not members:
                raise ValueError('missing-client-cohort')
            if not cohorts:
                members = [dict(name='', port=c.get('xray_port', 443), flow_mode=flow, finalmask=finalmask)]
                fallback = c.get('xray_fallback_port', 0)
                if fallback and fallback != c.get('xray_port', 443):
                    members.append(dict(name='fallback', port=fallback, flow_mode=flow, finalmask=finalmask))
            for member in members:
                shape = shapes[member.get('flow_mode', flow)]
                if member.get('finalmask', finalmask):
                    raise ValueError('P0 REALITY finalmask requires an Xray client')
                if shape['client_mux']:
                    raise ValueError('P0 REALITY Mux.Cool requires an Xray client; sing-mux is incompatible')
                reality = dict(type='vless', tag='p0-reality-' + tag + ('-' + member['name'] if member['name'] else ''), server=ip,
                               server_port=member['port'], uuid=credential['uuid'],
                               tls=dict(enabled=True, server_name=server_names[0], utls=dict(enabled=True, fingerprint=fp),
                                        reality=dict(enabled=True, public_key=reality_key, short_id=credential['short_id'])))
                if shape['client_flow']:
                    reality['flow'] = shape['client_flow']
                out.append(reality)
        if o['format'] in ('ripdpi', 'xray') and enabled('enable_nginx_xhttp', True):
            mode = x.get('xhttp_mode', 'auto')
            tuning = xhttp_tuning(x)
            native = o['format'] == 'xray' or xhttp_only
            if native and x.get('version') != 'v26.3.27':
                raise ValueError('unsupported-native-xhttp-version')
            # No unsupported field may silently disappear in a recipient importer.
            if not native and (mode not in ('auto', 'stream-up') or tuning):
                raise ValueError('unsupported-recipient-xhttp-mode')
            for endpoint in xhttp_endpoints(d, c):
                server_name = endpoint['host']
                suffix = ':alternate' if endpoint['name'] == 'alternate' else ''
                out.append(dict(type='vless', tag='p1-xhttp-' + tag + suffix, server=ip,
                                server_port=endpoint['port'], uuid=credential['uuid'],
                                tls=dict(enabled=True, server_name=server_name, utls=dict(enabled=True, fingerprint=fp)),
                                transport=dict(type='xhttp', host=server_name, path=x.get('xhttp_path', '/app-sync'), mode=mode,
                                               **({'xmux': tuning} if tuning else {}))))
        if enabled('enable_hysteria'):
            hy = d['hysteria']
            if o['format'] == 'ripdpi' and c.get('hysteria_port_range'):
                raise ValueError('RIPDPI Hysteria port hopping requires a qualified client')
            ech = hy.get('ech')
            resource = hy.get('resource_profile', 'bandwidth-capped')
            if ech and o['format'] != 'singbox':
                raise ValueError('ECH requires the verified official sing-box engine; RIPDPI export is unsupported')
            if resource != 'bandwidth-capped' and o['format'] != 'singbox':
                raise ValueError('BBR resource profiles require the verified official sing-box engine; RIPDPI export is unsupported')
            matches = [v for v in hy.get('clients', []) if v['name'] == client]
            if len(matches) != 1:
                raise ValueError('missing-selected-hysteria-client')
            hyout = dict(type='hysteria2', tag='p2-hysteria2-' + tag, server=ip, server_port=c.get('hysteria_port', 443),
                         password=client + ':' + required_text(matches[0].get('password')), tls=dict(enabled=True, server_name=required_text(hy.get('server_name') or (ech or {}).get('inner_name') or (d.get('nginx_xhttp') or {}).get('server_name'))))
            hyout.update(hysteria_client_bandwidth(hy))
            if ech:
                hyout['tls']['ech'] = dict(enabled=True, config=[
                    '-----BEGIN ECH CONFIGS-----', ech['config_list'], '-----END ECH CONFIGS-----'])
            if resource != 'bandwidth-capped':
                hyout['bbr_profile'] = resource.removeprefix('bbr-')
            extra = dict(insecure=False)
            if hy.get('salamander_enabled') and hy.get('salamander_password'):
                hyout['obfs'] = dict(type='salamander', password=hy['salamander_password'])
                extra['obfs'] = hyout['obfs']
                if hy.get('version') and not hy['version'].startswith('REPLACE_WITH_'):
                    extra['salamander_upstream_tag'] = hy['version']
            if c.get('hysteria_port_range'):
                ports = c['hysteria_port_range'].replace('-', ':')
                interval = c.get('hysteria_hop_interval', '30s')
                hyout.update(server_ports=[ports], hop_interval=interval)
                extra['port_hopping'] = dict(ports=ports, interval=interval)
            out.append(hyout)
            extras[hyout['tag']] = extra
        if enabled('enable_snell'):
            for variant in c['snell']['variants']:
                secret = next((v for v in d['snell_secrets']['variants'] if v['id'] == variant['id']), None)
                if secret is None:
                    raise ValueError('missing-snell-variant')
                user = next(v for v in secret['users'] if v['name'] == client)
                for reuse in (False, True):
                    snell_tag = 'p3-snell-' + variant['id'] + ('-reuse-' if reuse else '-fresh-') + tag
                    entry = dict(type='snell', tag=snell_tag, server=ip, server_port=variant['listen_port'], version=variant['client_version'],
                                 psk=required_text(secret.get('psk')), userkey=required_text(user.get('userkey')), reuse=reuse, network='tcp')
                    entry.update(dict(obfs_mode='none') if variant['client_version'] == 4 else dict(mode=variant.get('mode', 'default')))
                    out.append(entry)
                    snell.append(snell_tag)
        if extended:
            topology['split_hop_egress'] |= vpn.get('enable_split_hop_ingress', False)
            realm = vpn.get('hysteria_realm')
            if realm and topology['hysteria_realm'] and realm != topology['hysteria_realm']:
                raise ValueError('conflicting vpn.hysteria_realm values across HOSTS')
            topology['hysteria_realm'] = topology['hysteria_realm'] or realm
            if enabled('enable_amneziawg') and (not o['awg_host'] or o['awg_host'] == host):
                awg_context = host_context(cohort)
                awg.append(awg_export(d, awg_context, client, host, None, ip))
                binding = resolve_binding(d, awg_context, client, host)
                # A placeholder export still consumes the enrolled peer identity.
                bindings.append({**binding.identity, 'peer_public_key': binding.peer['public_key']})
    if not out and not (o['format'] == 'ripdpi' and awg_enabled):
        raise ValueError('no enabled outbounds resolved from Ansible profile toggles')
    if o['format'] == 'xray':
        # Each endpoint has its own local SOCKS listener. Native Xray has no
        # recipient UI selector; routing pins each listener to exactly one path.
        if len(out) > 16 or len({v['tag'] for v in out}) != len(out):
            raise ValueError('invalid-native-xhttp-endpoint-set')
        native_out, inbounds, rules = [], [], []
        for index, outbound in enumerate(out):
            transport, tls = outbound['transport'], outbound['tls']
            tag = outbound['tag']
            native_out.append(dict(protocol='vless', tag=tag, settings=dict(vnext=[dict(
                address=outbound['server'], port=outbound['server_port'],
                users=[dict(id=outbound['uuid'], encryption='none')])]), streamSettings=dict(
                    network='xhttp', security='tls', tlsSettings=dict(serverName=tls['server_name'],
                    allowInsecure=False, fingerprint=tls['utls']['fingerprint']),
                    xhttpSettings={key: value for key, value in transport.items() if key != 'type'})))
            inbounds.append(dict(tag=tag, listen='127.0.0.1', port=1080 + index,
                                 protocol='socks', settings=dict(udp=False)))
            rules.append(dict(type='field', inboundTag=[tag], outboundTag=tag))
        return dict(log=dict(loglevel='warning'), inbounds=inbounds,
                    outbounds=[dict(protocol='blackhole', tag='block'), *native_out],
                    routing=dict(rules=rules)), []
    automatic = [v['tag'] for v in out if v['tag'] not in snell]
    if snell:
        out.append(dict(type='selector', tag='snell-evaluation', outbounds=snell, default=snell[0], interrupt_exist_connections=False))
    out.append(dict(type='selector', tag='select', outbounds=automatic + (['auto'] if automatic else ['direct']) + (['snell-evaluation'] if snell else []), default='auto' if automatic else 'direct', interrupt_exist_connections=False))
    if automatic:
        out.append(dict(type='urltest', tag='auto', outbounds=automatic, url='https://www.gstatic.com/generate_204', interval='5m', tolerance=50))
    out += [dict(type='direct', tag='direct'), dict(type='block', tag='block')]
    rules = [dict(package_name=list(filter(None, value.split(','))), action='route', outbound=target)
             for value, target in ((per_app_bypass, 'direct'), (per_app_via_tun, 'select')) if value]
    payload = dict(log=dict(level='warn', timestamp=True), dns=dict(servers=[dict(type='https', tag='remote', server='1.1.1.1', detour='select')]),
                   inbounds=[dict(type='tun', tag='tun-in', interface_name='tun0', address=['172.19.0.1/30', 'fdfe:dcba:9876::1/126'], auto_route=True, strict_route=True, stack='system')],
                   outbounds=out, route=dict(rules=rules + [dict(action='sniff'), dict(protocol='dns', action='hijack-dns')], final='select', auto_detect_interface=True))
    if extended:
        policy = failover_policies[0]
        if any(value != policy for value in failover_policies):
            raise ValueError('conflicting-payload-failover-policy')
        if policy is not None and not automatic:
            raise ValueError('payload-failover-requires-proxy-candidates')
        if len(awg) > 1:
            raise ValueError('ambiguous-device-binding')
        if o['awg_host'] and not awg:
            raise ValueError('missing-device-binding')
        payload['ripdpi'] = dict(schema_version=1, amneziawg=awg, hysteria_extras=extras, topology=topology)
        if policy is not None:
            payload['ripdpi']['payload_failover'] = policy
        if o['expires']:
            payload['ripdpi']['expires'] = o['expires']
    return payload, bindings


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('client')
    parser.add_argument('--profile-format', choices=['sing-box', 'ripdpi', 'xray'], default='sing-box')
    parser.add_argument('--bundle', action='store_true')
    parser.add_argument('--xhttp-only', action='store_true')
    parser.add_argument('--per-app-bypass', default='')
    parser.add_argument('--per-app-via-tun', default='')
    args = parser.parse_args()
    try:
        if args.bundle and args.profile_format == 'xray':
            raise ValueError('bundle requires RIPDPI format')
        selected_format = 'ripdpi' if args.bundle else {'sing-box': 'singbox', 'ripdpi': 'ripdpi', 'xray': 'xray'}[args.profile_format]
        o = options(selected_format, expires=os.environ.get('BUNDLE_EXPIRES', ''))
        payload, _ = materialize(args.client, o, per_app_bypass=args.per_app_bypass, per_app_via_tun=args.per_app_via_tun, extended=args.bundle, xhttp_only=args.xhttp_only)
        print(json.dumps(payload, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, StopIteration, subprocess.SubprocessError, yaml.YAMLError) as error:
        safe = {'--xhttp-only requires --profile-format ripdpi', 'ECH requires the verified official sing-box engine; RIPDPI export is unsupported', 'BBR resource profiles require the verified official sing-box engine; RIPDPI export is unsupported', 'RIPDPI Hysteria port hopping requires a qualified client', 'P0 REALITY finalmask requires an Xray client', 'P0 REALITY Mux.Cool requires an Xray client; sing-mux is incompatible', 'conflicting vpn.hysteria_realm values across HOSTS', 'ambiguous-device-binding', 'missing-device-binding', 'plaintext secrets cannot be combined with SOPS_FILES', 'missing-snell-variant'}
        detail = str(error) if isinstance(error, ValueError) and str(error) in safe else ('plaintext secrets unavailable' if 'VPN_SECRETS_FILE' in os.environ else 'materialization refused')
        print('client-payload: ' + detail, file=__import__('sys').stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
