#!/usr/bin/python3 -Es
"""Publish and verify the owned final recipient egress boundary."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from transport_destination_policy import IPV4_DENY, IPV6_DENY, normalize_address

TABLE = 'ripdpi_transport'
STATE = Path('/var/lib/ripdpi/transport-egress')
MAX_INPUT = 131072


class BoundaryError(ValueError):
    pass


def integer(value, low=1, high=65535):
    if type(value) is not int or not low <= value <= high:
        raise BoundaryError('invalid-policy-number')
    return value


def keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise BoundaryError('invalid-policy-shape')


def validate(raw):
    keys(raw, ['schema_version', 'normalizer_uid', 'gateway_uid', 'listeners', 'backends', 'resolver', 'policy'], ['warp_gateway_uid', 'warp', 'classifier_uid'])
    if raw['schema_version'] != 1 or type(raw['schema_version']) is not int:
        raise BoundaryError('invalid-policy-version')
    users = [integer(raw[key], high=2**32-2) for key in ('normalizer_uid', 'gateway_uid')]
    if 'warp' in raw:
        users.append(integer(raw.get('warp_gateway_uid'), high=2**32-2))
        keys(raw['warp'], ['namespace', 'host_interface', 'namespace_interface', 'host_address', 'namespace_address', 'tunnel_ifindex'])
        fixed = {'namespace': 'ripdpi-warp', 'host_interface': 'rpd-warp-host', 'namespace_interface': 'rpd-warp-ns', 'host_address': '10.250.254.1', 'namespace_address': '10.250.254.2'}
        if any(raw['warp'][key] != value for key, value in fixed.items()):
            raise BoundaryError('invalid-warp-authority')
        if raw['warp']['tunnel_ifindex'] is not None:
            integer(raw['warp']['tunnel_ifindex'], high=2**31-1)
    if 'classifier_uid' in raw:
        users.append(integer(raw['classifier_uid'], high=2**32-2))
    if len(set(users)) != len(users):
        raise BoundaryError('identity-not-separated')
    if not isinstance(raw['listeners'], list) or not 1 <= len(raw['listeners']) <= 3:
        raise BoundaryError('invalid-policy-listeners')
    pools, ports, names = [], [], set()
    for item in raw['listeners']:
        keys(item, ['name', 'address', 'port', 'frontend_uid', 'backend', 'udp_port_min', 'udp_port_max'])
        if item['name'] not in {'direct_xray', 'direct_hysteria', 'warp_xray'} or item['name'] in names or item['address'] != '127.0.0.1' or item['backend'] != ('warp' if item['name'] == 'warp_xray' else 'direct'):
            raise BoundaryError('invalid-policy-listener')
        names.add(item['name'])
        integer(item['frontend_uid'], high=2**32-2)
        if item['frontend_uid'] in users:
            raise BoundaryError('identity-not-separated')
        ports.append(integer(item['port']))
        pools.append((integer(item['udp_port_min']), integer(item['udp_port_max'])))
    if 'classifier_uid' in raw:
        if 'direct_xray' not in names:
            raise BoundaryError('classifier-frontend-absent')
        ports.append(10808)
    if not isinstance(raw['backends'], dict) or set(raw['backends']) != {item['backend'] for item in raw['listeners']}:
        raise BoundaryError('invalid-policy-backends')
    for name, item in raw['backends'].items():
        keys(item, ['address', 'port', 'udp_source_port_min', 'udp_source_port_max'])
        if item['address'] != ('127.0.0.1' if name == 'direct' else '10.250.254.2'):
            raise BoundaryError('invalid-policy-backend')
        ports.append(integer(item['port']))
        pools.append((integer(item['udp_source_port_min']), integer(item['udp_source_port_max'])))
    if len(set(ports)) != len(ports):
        raise BoundaryError('policy-port-collision')
    for index, (low, high) in enumerate(pools):
        if low > high or high-low > 8191 or any(low <= port <= high for port in ports) or any(low <= end and start <= high for start, end in pools[:index]):
            raise BoundaryError('policy-pool-collision')
    keys(raw['resolver'], ['nameservers'])
    if not isinstance(raw['resolver']['nameservers'], list) or not 1 <= len(raw['resolver']['nameservers']) <= 3:
        raise BoundaryError('invalid-policy-resolver')
    for value in raw['resolver']['nameservers']:
        if str(normalize_address(value)) != value:
            raise BoundaryError('invalid-policy-resolver')
    keys(raw['policy'], ['owned_addresses', 'management_tcp_ports', 'management_udp_ports'])
    if not isinstance(raw['policy']['owned_addresses'], list) or len(raw['policy']['owned_addresses']) > 256:
        raise BoundaryError('invalid-owned-addresses')
    for value in raw['policy']['owned_addresses']:
        if str(normalize_address(value)) != value:
            raise BoundaryError('invalid-owned-address')
    for field in ('management_tcp_ports', 'management_udp_ports'):
        if not isinstance(raw['policy'][field], list) or len(raw['policy'][field]) > 256:
            raise BoundaryError('invalid-management-ports')
        for value in raw['policy'][field]:
            integer(value)
    return raw


def intervals(raw):
    return ([(10808, 10808)] if 'classifier_uid' in raw else []) + [(item['port'], item['port']) for item in raw['listeners']] + [(item['port'], item['port']) for item in raw['backends'].values()] + [(item['udp_port_min'], item['udp_port_max']) for item in raw['listeners']] + [(item['udp_source_port_min'], item['udp_source_port_max']) for item in raw['backends'].values()]


def render(raw, namespace=False):
    validate(raw)
    if namespace and 'warp' not in raw:
        raise BoundaryError('warp-not-enabled')
    lines = [f'add table inet {TABLE}', f'flush table inet {TABLE}', f'table inet {TABLE} {{', ' chain admission { type filter hook output priority -5; policy accept;']
    normalizer = raw['normalizer_uid']
    if not namespace:
        for item in raw['listeners']:
            uid, port, lo, hi = item['frontend_uid'], item['port'], item['udp_port_min'], item['udp_port_max']
            lines += [f'  ip daddr 127.0.0.1 tcp dport {port} meta skuid != {uid} drop', f'  ip daddr 127.0.0.1 udp dport {lo}-{hi} meta skuid != {uid} drop']
        if 'classifier_uid' in raw:
            frontend = next(item['frontend_uid'] for item in raw['listeners'] if item['name'] == 'direct_xray')
            lines.append(f'  ip daddr 127.0.0.1 tcp dport 10808 meta skuid != {frontend} drop')
        for name, item in raw['backends'].items():
            address, port = item['address'], item['port']
            lines.append(f'  ip daddr {address} meta l4proto {{ tcp, udp }} th dport {port} meta skuid != {normalizer} drop')
            # Native SOCKS UDP BND is the same fixed inbound port.
        lines.append(' }')
        lines.append(' chain normalizer { type filter hook output priority 300; policy accept;')
        for item in raw['listeners']:
            port, lo, hi = item['port'], item['udp_port_min'], item['udp_port_max']
            for protocol, source in [('tcp', str(port)), ('udp', f'{lo}-{hi}')]:
                lines.append(f'  meta skuid {normalizer} oifname "lo" ip daddr 127.0.0.1 {protocol} sport {source} ct direction reply ct original proto-dst {source} accept')
        for name, item in raw['backends'].items():
            address, port = item['address'], item['port']
            ipc_interface = 'lo' if name == 'direct' else 'rpd-warp-host'
            lines.append(f'  meta skuid {normalizer} oifname "{ipc_interface}" ip daddr {address} tcp dport {port} accept')
            lines.append(f'  meta skuid {normalizer} oifname "{ipc_interface}" ip daddr {address} udp sport {item["udp_source_port_min"]}-{item["udp_source_port_max"]} udp dport {port} accept')
        for address in raw['resolver']['nameservers']:
            family = 'ip6' if ':' in address else 'ip'
            lines.append(f'  meta skuid {normalizer} {family} daddr {address} meta l4proto {{ tcp, udp }} th dport 53 accept')
        lines += [f'  meta skuid {normalizer} drop', ' }']
    else:
        lines += [' }']
    gateway_uid = raw['warp_gateway_uid'] if namespace else raw['gateway_uid']
    backend = raw['backends']['warp' if namespace else 'direct']
    address, port = backend['address'], backend['port']
    lines.append(' chain destination { type filter hook output priority 300; policy accept;')
    # TCP replies can only return to the admitted normalizer connection. UDP replies only to its reserved source pools.
    peer = '10.250.254.1' if namespace else '127.0.0.1'
    interface = 'rpd-warp-ns' if namespace else 'lo'
    lines.append(f'  meta skuid {gateway_uid} oifname "{interface}" ip daddr {peer} tcp sport {port} ct direction reply ct original proto-dst {port} accept')
    lines.append(f'  meta skuid {gateway_uid} oifname "{interface}" ip daddr {peer} udp dport {backend["udp_source_port_min"]}-{backend["udp_source_port_max"]} ct direction reply udp sport {port} ct original proto-src {backend["udp_source_port_min"]}-{backend["udp_source_port_max"]} ct original proto-dst {port} accept')
    guarded_uids = [gateway_uid]
    if not namespace and 'classifier_uid' in raw:
        classifier = raw['classifier_uid']
        lines.append(f'  meta skuid {classifier} oifname "lo" ip daddr 127.0.0.1 tcp sport 10808 ct direction reply ct original proto-dst 10808 accept')
        guarded_uids.append(classifier)
    for guarded_uid in guarded_uids:
        for family, prefixes in [('ip', IPV4_DENY), ('ip6', IPV6_DENY)]:
            lines.append(f'  meta skuid {guarded_uid} {family} daddr {{ {", ".join(prefixes)} }} drop')
        for network in ('tcp', 'udp'):
            management = raw['policy'][f'management_{network}_ports']
            if management:
                values = ', '.join(map(str, management))
                if not namespace:
                    lines.append(f'  meta skuid {guarded_uid} fib daddr type local {network} dport {{ {values} }} drop')
                for family in ('ip', 'ip6'):
                    owned = [value for value in raw['policy']['owned_addresses'] if (':' in value) == (family == 'ip6')]
                    if owned:
                        lines.append(f'  meta skuid {guarded_uid} {family} daddr {{ {", ".join(owned)} }} {network} dport {{ {values} }} drop')
    if namespace:
        index = raw['warp']['tunnel_ifindex']
        if index is not None:
            lines.append(f'  meta skuid {gateway_uid} meta oif {index} meta l4proto {{ tcp, udp }} accept')
        lines.append(f'  meta skuid {gateway_uid} drop')
    lines += [' }', '}']
    if namespace:
        # Remote or namespace-root processes cannot access the plaintext gateway.
        lines += [f'add chain inet {TABLE} input {{ type filter hook input priority -5; policy accept; }}', f'add rule inet {TABLE} input ip daddr {address} meta l4proto {{ tcp, udp }} th dport {port} ip saddr != 10.250.254.1 drop', f'add rule inet {TABLE} input ip daddr {address} iifname != "rpd-warp-ns" meta l4proto {{ tcp, udp }} th dport {port} drop']
    if not namespace and 'warp' in raw:
        backend = raw['backends']['warp']
        port, low, high = backend['port'], backend['udp_source_port_min'], backend['udp_source_port_max']
        lines += [f'add chain inet {TABLE} namespace_input {{ type filter hook input priority -5; policy accept; }}',
                  f'add rule inet {TABLE} namespace_input iifname "rpd-warp-host" ip saddr 10.250.254.2 ip daddr 10.250.254.1 tcp sport {port} ct direction reply ct original proto-dst {port} accept',
                  f'add rule inet {TABLE} namespace_input iifname "rpd-warp-host" ip saddr 10.250.254.2 ip daddr 10.250.254.1 udp sport {port} udp dport {low}-{high} ct direction reply ct original proto-dst {port} accept',
                  f'add rule inet {TABLE} namespace_input iifname "rpd-warp-host" fib daddr type local drop',
                  f'add chain inet {TABLE} namespace_forward {{ type filter hook forward priority 300; policy accept; }}']
        for family, prefixes in [('ip', IPV4_DENY), ('ip6', IPV6_DENY)]:
            lines.append(f'add rule inet {TABLE} namespace_forward iifname "rpd-warp-host" {family} daddr {{ {", ".join(prefixes)} }} drop')
        lines += [f'add chain inet {TABLE} namespace_nat {{ type nat hook postrouting priority 100; policy accept; }}',
                  f'add rule inet {TABLE} namespace_nat iifname "rpd-warp-host" ip saddr 10.250.254.2 masquerade']
    return '\n'.join(lines) + '\n'


def command(args, namespace=False, *, data=None):
    prefix = ['ip', 'netns', 'exec', 'ripdpi-warp'] if namespace else []
    result = subprocess.run(prefix+args, input=data, text=True, capture_output=True, timeout=15, check=False)
    if result.returncode:
        raise BoundaryError('kernel-command-failed')
    return result.stdout


def normalized(value, interface_ids=None):
    interface_ids = interface_ids or {}
    if isinstance(value, dict):
        # nft JSON resolves a numeric meta iif/oif to a current interface name,
        # then prints a numeric string after deletion. Canonicalize the same
        # wire matcher to its actual index before hashing owned authority.
        left = value.get('left')
        if isinstance(left, dict) and left.get('meta', {}).get('key') in {'iif', 'oif'} and 'right' in value:
            value = dict(value)
            right = value['right']
            if isinstance(right, str):
                if right.isdecimal():
                    if right in interface_ids and interface_ids[right] != int(right):
                        raise BoundaryError('ambiguous-interface-matcher')
                    value['right'] = int(right)
                elif right in interface_ids:
                    value['right'] = interface_ids[right]
                else:
                    raise BoundaryError('unresolved-interface-matcher')
        return {key: normalized(item, interface_ids) for key, item in value.items()
                if key not in {'handle', 'packets', 'bytes', 'metainfo'}}
    if isinstance(value, list):
        return [normalized(item, interface_ids) for item in value]
    return value


def digest(value, interface_ids=None):
    return hashlib.sha256(json.dumps(normalized(value, interface_ids), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def audit_authority(ruleset):
    chains, rules, edges = {}, {}, {}
    entries = ruleset.get('nftables', [])
    if len(entries) > 100000:
        raise BoundaryError('oversized-kernel-authority')
    for entry in entries:
        if 'flowtable' in entry:
            raise BoundaryError('unsupported-offload-authority')
        chain = entry.get('chain')
        if chain and chain.get('table') != TABLE:
            identity = (chain['family'], chain['table'], chain['name'])
            chains[identity] = chain
            if chain.get('family') == 'netdev' and chain.get('hook') == 'egress':
                raise BoundaryError('unsupported-netdev-authority')
            if chain.get('hook') == 'output' and chain.get('prio', 0) >= 300:
                raise BoundaryError('unsupported-late-output-authority')
    def transfers(value):
        result = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'jump', 'goto'}:
                    target = item.get('target') if isinstance(item, dict) else item
                    if not isinstance(target, str):
                        raise BoundaryError('unsupported-chain-transfer')
                    result.append(target)
                else:
                    result.extend(transfers(item))
        elif isinstance(value, list):
            for item in value:
                result.extend(transfers(item))
        return result
    for entry in entries:
        rule = entry.get('rule')
        if not rule or rule.get('table') == TABLE:
            continue
        identity = (rule['family'], rule['table'], rule['chain'])
        expression = rule.get('expr', [])
        rules.setdefault(identity, []).append(expression)
        edges.setdefault(identity, set()).update((rule['family'], rule['table'], target)
                                               for target in transfers(expression))
        text = json.dumps(expression)
        if any(f'"{key}"' in text for key in ('dup', 'fwd', 'queue', 'tproxy')):
            raise BoundaryError('unsupported-packet-redirection')
        if 'flow' in text and 'offload' in text:
            raise BoundaryError('unsupported-offload-authority')
    # A regular chain inherits every hook that can reach it. Earlier OUTPUT
    # checks cannot constrain destination mutations reached from POSTROUTING.
    pending = [identity for identity, chain in chains.items() if chain.get('hook') == 'postrouting']
    visited = set()
    while pending:
        identity = pending.pop()
        if identity in visited:
            continue
        visited.add(identity)
        if identity not in chains:
            raise BoundaryError('unresolved-chain-authority')
        for expression in rules.get(identity, []):
            text = json.dumps(expression)
            if any(f'"{key}"' in text for key in ('dnat', 'redirect', 'mangle', 'vmap')):
                raise BoundaryError('unsupported-postrouting-authority')
        pending.extend(edges.get(identity, set()) - visited)


def parse_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BoundaryError('ambiguous-policy')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def private_read(path):
    authority = Path(path).absolute()
    for parent in reversed(authority.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
            raise BoundaryError('invalid-private-ancestry')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o077:
            raise BoundaryError('invalid-private-authority')
        with os.fdopen(descriptor, 'rb', closefd=False) as source:
            data = source.read(MAX_INPUT+1)
        if len(data) > MAX_INPUT:
            raise BoundaryError('oversized-policy')
        return parse_json(data)
    finally:
        os.close(descriptor)


def write_private(path, value):
    descriptor, candidate = tempfile.mkstemp(prefix='.policy-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as target:
            json.dump(value, target, sort_keys=True)
            target.flush()
            os.fsync(target.fileno())
        os.replace(candidate, path)
    finally:
        if os.path.exists(candidate):
            os.unlink(candidate)


def admit_ports(raw, namespace=False):
    if namespace:
        ephemeral = command(['cat', '/proc/sys/net/ipv4/ip_local_port_range'], True)
        reserved = command(['cat', '/proc/sys/net/ipv4/ip_local_reserved_ports'], True).strip()
    else:
        ephemeral = Path('/proc/sys/net/ipv4/ip_local_port_range').read_text()
        reserved = Path('/proc/sys/net/ipv4/ip_local_reserved_ports').read_text().strip()
    ephemeral_low, ephemeral_high = map(int, ephemeral.split())
    covered = []
    for part in reserved.split(',') if reserved else []:
        pieces = part.split('-')
        covered.append((int(pieces[0]), int(pieces[-1])))
    for low, high in intervals(raw):
        overlap_low, overlap_high = max(low, ephemeral_low), min(high, ephemeral_high)
        if overlap_low <= overlap_high and not all(any(start <= port <= end for start, end in covered) for port in range(overlap_low, overlap_high+1)):
            raise BoundaryError('unreserved-ephemeral-pool')


def admit_links(raw, namespace=False):
    links = json.loads(command(['ip', '-j', '-d', 'link', 'show'], namespace))
    for link in links:
        if link['ifname'].split('@')[0].isdecimal():
            raise BoundaryError('ambiguous-interface-name')
        if link.get('xdp', {}).get('prog') or link.get('xdp', {}).get('attached') not in (None, 'off'):
            raise BoundaryError('unsupported-xdp-authority')
        for direction in ('ingress', 'egress'):
            filters = json.loads(command(['tc', '-j', 'filter', 'show', 'dev', link['ifname'].split('@')[0], direction], namespace))
            if filters:
                raise BoundaryError('unsupported-tc-authority')
    if namespace and raw['warp']['tunnel_ifindex'] is not None:
        selected = [link for link in links if link['ifindex'] == raw['warp']['tunnel_ifindex']]
        if len(selected) != 1 or selected[0].get('linkinfo', {}).get('info_kind') != 'tun' or selected[0].get('linkinfo', {}).get('info_data', {}).get('type') != 'tun' or 'UP' not in selected[0].get('flags', []):
            raise BoundaryError('tunnel-authority-unconfirmed')
    return {link['ifname'].split('@')[0]: link['ifindex'] for link in links}


def admit_owners(raw, namespace=False):
    expected = []
    if namespace:
        backend = raw['backends']['warp']
        expected.append((backend['port'], backend['port'], raw['warp_gateway_uid']))
    else:
        if 'classifier_uid' in raw:
            expected.append((10808, 10808, raw['classifier_uid']))
        for listener in raw['listeners']:
            expected += [(listener['port'], listener['port'], raw['normalizer_uid']),
                         (listener['udp_port_min'], listener['udp_port_max'], raw['normalizer_uid'])]
        for name, backend in raw['backends'].items():
            expected.append((backend['udp_source_port_min'], backend['udp_source_port_max'], raw['normalizer_uid']))
            if name == 'direct':
                expected.append((backend['port'], backend['port'], raw['gateway_uid']))
    for line in command(['ss', '-H', '-n', '-a', '-t', '-u', '-e'], namespace).splitlines():
        fields = line.split()
        if len(fields) < 6:
            raise BoundaryError('socket-authority-unavailable')
        try:
            port = int(fields[4].rsplit(':', 1)[1])
        except ValueError:
            continue
        for low, high, uid in expected:
            if low <= port <= high:
                match = re.search(r'(?:^| )uid:([0-9]+)(?: |$)', line)
                actual = int(match.group(1)) if match else 0
                if actual != uid:
                    raise BoundaryError('foreign-port-owner')


def run(mode, raw, namespace=False):
    validate(raw)
    nft = render(raw, namespace)
    if mode == 'render':
        return nft
    if os.geteuid() != 0:
        raise BoundaryError('root-required')
    if not STATE.is_dir() or STATE.is_symlink() or STATE.stat().st_uid != 0 or STATE.stat().st_mode & 0o022:
        raise BoundaryError('invalid-state-authority')
    receipt_path = STATE / ('policy-warp.json' if namespace else 'policy-host.json')
    lock = os.open(STATE/'policy.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        admit_ports(raw, namespace)
        admit_owners(raw, namespace)
        interface_ids = admit_links(raw, namespace)
        ruleset = json.loads(command(['nft', '-j', 'list', 'ruleset'], namespace))
        audit_authority(ruleset)
        owned = [entry for entry in ruleset['nftables'] if next(iter(entry), '') != 'metainfo' and next(iter(entry.values()), {}).get('table', next(iter(entry.values()), {}).get('name') if 'table' in entry else None) == TABLE]
        old = private_read(receipt_path) if receipt_path.exists() else None
        if old is not None:
            keys(old, ['schema_version', 'config_digest', 'kernel_digest', 'rules', 'rules_digest'])
            if old['schema_version'] != 1 or not isinstance(old['rules'], str) or hashlib.sha256(old['rules'].encode()).hexdigest() != old['rules_digest']:
                raise BoundaryError('invalid-policy-receipt')
        if owned and (old is None or digest(owned, interface_ids) != old.get('kernel_digest')):
            raise BoundaryError('foreign-or-drifted-boundary')
        if mode == 'verify':
            if not owned or old is None or old.get('config_digest') != digest(raw):
                raise BoundaryError('boundary-not-ready')
            return ''
        if owned and old is not None and old.get('config_digest') == digest(raw):
            return json.dumps({'changed': False}) + '\n'
        command(['nft', '-c', '-f', '-'], namespace, data=nft)
        try:
            command(['nft', '-f', '-'], namespace, data=nft)
            active = json.loads(command(['nft', '-j', 'list', 'table', 'inet', TABLE], namespace))
            write_private(receipt_path, {'schema_version': 1, 'config_digest': digest(raw),
                          'kernel_digest': digest([entry for entry in active['nftables'] if 'metainfo' not in entry], interface_ids),
                          'rules': nft, 'rules_digest': hashlib.sha256(nft.encode()).hexdigest()})
        except (BoundaryError, OSError, ValueError, subprocess.SubprocessError):
            # Kernel publication and its private receipt form one compensating transaction.
            # Consumers remain stopped until the caller confirms the accepted generation.
            if old is not None:
                command(['nft', '-f', '-'], namespace, data=old['rules'])
                if receipt_path.exists() and private_read(receipt_path) != old:
                    write_private(receipt_path, old)
            else:
                current = json.loads(command(['nft', '-j', 'list', 'ruleset'], namespace))
                if any(entry.get('table', {}).get('name') == TABLE for entry in current.get('nftables', [])):
                    command(['nft', 'delete', 'table', 'inet', TABLE], namespace)
            raise BoundaryError('policy-publication-refused') from None
        return json.dumps({'changed': True}) + '\n'
    finally:
        os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['render', 'apply', 'verify'])
    parser.add_argument('--config', required=True)
    parser.add_argument('--namespace', choices=['ripdpi-warp'])
    args = parser.parse_args()
    try:
        data = sys.stdin.buffer.read(MAX_INPUT+1) if args.config == '-' else None
        if data is not None and len(data) > MAX_INPUT:
            raise BoundaryError('oversized-policy')
        raw = parse_json(data) if data is not None else private_read(args.config)
        sys.stdout.write(run(args.mode, raw, args.namespace is not None))
        return 0
    except (BoundaryError, ValueError, OSError, subprocess.SubprocessError):
        print('transport-egress-boundary-refused', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
