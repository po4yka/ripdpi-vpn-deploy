"""Read-only bootstrap preflight, sent on pinned SSH stdin before installation."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
import time
from uuid import UUID


class ProbeError(ValueError):
    pass


def read(path, limit=262144):
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ProbeError("unsafe-input-parent")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ProbeError("unsafe-input")
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ProbeError("oversized-input")
    return content


def command(argv, *, input_data=None):
    result = subprocess.run(argv, capture_output=True, timeout=15,
                            input=input_data,
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"}, check=False)
    if result.returncode or len(result.stdout) > 262144:
        raise ProbeError("probe-command-failed")
    return result.stdout


def validate_build_environment(expected):
    """Bind the canonical build label to the immutable cloud-init marker."""
    if not isinstance(expected, str) or not 1 <= len(expected) <= 128:
        raise ProbeError("build-environment-invalid")
    document = read(Path("/etc/vpn-build-id"), 4096).decode("utf-8")
    values = [line.partition("=")[2] for line in document.splitlines()
              if line.partition("=")[0] == "build_env"]
    if values != [expected]:
        raise ProbeError("build-environment-mismatch")


def preflight_tailnet_command(executable: Path, package_version: str) -> None:
    info = executable.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ProbeError("unsafe-tailnet-command")
    result = subprocess.run([str(executable), "status", "--json"], capture_output=True,
                            timeout=15, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"}, check=False)
    # A NeedsLogin daemon or an inactive partial install is resumable only for
    # the dpkg-owned pinned package; package installation would overwrite it.
    logged_out = result.returncode == 0
    if logged_out and (len(result.stdout) > 262144
                       or json.loads(result.stdout).get("BackendState") != "NeedsLogin"):
        raise ProbeError("existing-tailnet-identity")
    if (executable != Path("/usr/bin/tailscale") or not isinstance(package_version, str)
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", package_version)):
        raise ProbeError("existing-tailnet-identity")
    owner = command(["dpkg-query", "-S", "/usr/bin/tailscale"]).decode().strip()
    version = command(["dpkg-query", "-W", "-f=${Version}", "tailscale"]).decode().strip()
    if owner != "tailscale: /usr/bin/tailscale" or version != package_version:
        raise ProbeError("existing-tailnet-identity")
    if logged_out:
        return
    daemon = command(["systemctl", "show", "--value", "-p", "ActiveState", "tailscaled.service"]).decode().strip()
    if os.path.lexists("/var/lib/tailscale/tailscaled.state") or daemon != "inactive":
        raise ProbeError("existing-tailnet-identity")


def preflight_tailnet_commands(package_version):
    present = [executable for executable in (Path("/usr/bin/tailscale"), Path("/usr/local/bin/tailscale"))
               if os.path.lexists(executable)]
    for executable in present:
        preflight_tailnet_command(executable, package_version)
    # Installing the package would start tailscaled on a leftover identity.
    if not present and os.path.lexists("/var/lib/tailscale/tailscaled.state"):
        raise ProbeError("existing-tailnet-identity")


def nftables_empty():
    """Dump table existence through Linux UAPI; no nft binary or guest file needed.

    Only GETTABLE is sent. Unknown, interrupted, truncated, or error replies
    refuse; an ACK is never mistaken for a complete empty dump.
    """
    sequence = int.from_bytes(os.urandom(4), "little") or 1
    with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 12) as channel:
        channel.settimeout(3)
        channel.bind((0, 0))
        request = struct.pack("=IHHII", 20, (10 << 8) | 1, 0x301, sequence, channel.getsockname()[0]) + bytes(4)
        channel.sendto(request, (0, 0))
        for _ in range(32):
            packet, _, flags, sender = channel.recvmsg(65536)
            if flags & socket.MSG_TRUNC or sender[0] != 0:
                raise ProbeError("netfilter-dump-invalid")
            offset = 0
            while offset < len(packet):
                if len(packet) - offset < 16:
                    raise ProbeError("netfilter-dump-invalid")
                length, kind, message_flags, reply, _pid = struct.unpack_from("=IHHII", packet, offset)
                if length < 16 or offset + length > len(packet) or reply != sequence or message_flags & 0x10:
                    raise ProbeError("netfilter-dump-invalid")
                body = packet[offset + 16:offset + length]
                if kind == 3:  # NLMSG_DONE carries dump status.
                    if body not in (b"", bytes(4)) or offset + ((length + 3) & ~3) != len(packet):
                        raise ProbeError("netfilter-dump-invalid")
                    return True
                if kind == 10 << 8:  # NFT_MSG_NEWTABLE response to GETTABLE.
                    return False
                raise ProbeError("netfilter-dump-invalid")
        raise ProbeError("netfilter-dump-incomplete")


def split_inert_tables(entries):
    """Separate only the complete four-table, object-free daemon baseline.

    Keep other entries visible to the caller's ownership validator. A chain,
    set, rule, duplicate or extra table attribute invalidates this exception.
    Kernel handles are identifiers only; they never authorize table contents.
    """
    identities = {(family, name) for family in ("ip", "ip6")
                  for name in ("filter", "nat")}
    tables, remaining, seen = [], [], set()
    for entry in entries:
        if not isinstance(entry, dict) or len(entry) != 1:
            return [], entries
        value = next(iter(entry.values()))
        if not isinstance(value, dict):
            return [], entries
        identity = (value.get("family"), value.get("name"))
        if "table" in entry and identity in identities:
            if (set(value) - {"family", "name", "handle"}
                    or ("handle" in value and
                        (type(value["handle"]) is not int or value["handle"] < 1))
                    or identity in seen):
                return [], entries
            tables.append(entry)
            seen.add(identity)
        else:
            if (value.get("family"), value.get("table")) in identities:
                return [], entries
            remaining.append(entry)
    if seen != identities:
        return [], entries
    return sorted(tables, key=lambda item: (item["table"]["family"], item["table"]["name"])), remaining


def empty_firewall_baseline():
    if nftables_empty():
        return True
    document = json.loads(command(["nft", "-j", "list", "ruleset"]))
    if not isinstance(document, dict) or set(document) != {"nftables"}:
        raise ProbeError("netfilter-dump-invalid")
    entries = [item for item in document["nftables"] if "metainfo" not in item]
    tables, remaining = split_inert_tables(entries)
    return bool(tables) and not remaining


def stable_rules(document):
    """Canonical kernel readback, shared with the snapshot/recovery adapter."""
    if not isinstance(document, dict) or set(document) != {"nftables"} or not isinstance(document["nftables"], list):
        raise ProbeError("netfilter-dump-invalid")
    def clean(value):
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == "handle":
                    continue
                if key == "counter" and isinstance(item, dict):
                    item = {k: v for k, v in item.items() if k not in {"packets", "bytes"}}
                result[key] = clean(item)
            return result
        return value
    entries = [clean(item) for item in document["nftables"] if "metainfo" not in item]
    inert, remaining = split_inert_tables(entries)
    return inert + remaining


def validate_owned_rules(entries):
    """Every object belongs to a declared repository table and chain."""
    _, owned = split_inert_tables(entries)
    tables = {('inet', 'filter'), ('inet', 'nat')}
    chains = {('filter', 'input'), ('filter', 'forward'), ('filter', 'output'), ('nat', 'postrouting')}
    sets = {'vpn_tailnet_ssh_v4', 'vpn_tailnet_ssh_v6', 'f2b_sshd4', 'f2b_sshd6',
            'policy_offenders', 'policy_offenders6', 'cdn_front_origins', 'cdn_front_origins_v6'}
    for entry in owned:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise ProbeError('foreign-firewall')
        kind, value = next(iter(entry.items()))
        if not isinstance(value, dict) or value.get('family') != 'inet':
            raise ProbeError('foreign-firewall')
        if kind == 'table':
            valid = (value['family'], value.get('name')) in tables
        elif kind == 'chain':
            valid = (value.get('table'), value.get('name')) in chains
        elif kind == 'rule':
            valid = (value.get('table'), value.get('chain')) in chains and isinstance(value.get('expr'), list)
        elif kind == 'set':
            valid = value.get('table') == 'filter' and value.get('name') in sets
        else:
            valid = False
        if not valid:
            raise ProbeError('foreign-firewall')


def policy_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse_policy(content):
    program = ("import subprocess,sys; "
               "subprocess.run(['/usr/sbin/nft','-f','-'],input=sys.stdin.buffer.read(),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
               "subprocess.run(['/usr/sbin/nft','-j','list','ruleset'],check=True)")
    return stable_rules(json.loads(command(["unshare", "--net", "/usr/bin/python3", "-I", "-B", "-c", program], input_data=content)))


def legacy_candidate(main, binding):
    """One pre-Tailnet managed layout; every original byte remains in order."""
    if (not main.startswith(b"#!/usr/sbin/nft -f\n# Managed by Ansible role `firewall`.")
            or re.search(rb'\binclude\b|tailscale0|vpn_tailnet_ssh_|vpn-bootstrap-', main)):
        raise ProbeError("legacy-layout-unsupported")
    table = b'table inet filter {'
    chain = re.compile(rb'(  chain input \{\n    type filter hook input priority 0;\n    policy drop;\n)')
    if main.count(table) != 1 or len(chain.findall(main)) != 1:
        raise ProbeError("legacy-layout-unsupported")
    port = binding['ssh_port']
    lines = [f'    iifname "tailscale0" tcp dport {port} ip saddr @vpn_tailnet_ssh_v4 accept comment "vpn-bootstrap-overlay-v4"',
             f'    iifname "tailscale0" tcp dport {port} ip6 saddr @vpn_tailnet_ssh_v6 accept comment "vpn-bootstrap-overlay-v6"',
             f'    iifname "tailscale0" tcp dport {port} drop comment "vpn-bootstrap-overlay-drop"']
    lines.extend(f'    {"ip6" if ":" in source else "ip"} saddr {source} tcp dport {port} accept comment "vpn-bootstrap-public-{index}"'
                 for index, source in enumerate(binding['public_sources']))
    value = main.replace(table, table+b'\n  include "/etc/nftables.d/vpn-tailnet-ssh-sets.nft"', 1)
    start = chain.search(value).end()
    end = value.find(b'\n  }', start)
    if end < 0:
        raise ProbeError('legacy-layout-unsupported')
    block = value[start:end]
    ssh = re.search(rb'^    (?:tcp dport '+str(port).encode()+rb' ip6? saddr .+|ip6? saddr .+ tcp dport '+str(port).encode()+rb') accept(?: comment \"[^\"]*\")?$', block, re.M)
    if ssh is not None:
        offset = start+ssh.start()
    else:
        # A source-restricted managed policy may have no SSH allowances yet.
        # Insert only at its final input drop, after all existing controls.
        drops = list(re.finditer(rb'^    counter drop$', block, re.M))
        if len(drops) != 1 or block[drops[0].end():].strip():
            raise ProbeError('legacy-ssh-anchor-unsupported')
        offset = start+drops[0].start()
    return value[:offset]+('\n'.join(lines)+'\n').encode()+value[offset:]


def lease_active(lease, *, boot_id, wall, monotonic, margin=0):
    return (lease['boot_id'] == boot_id
            and lease['monotonic_started'] <= monotonic
            and wall >= lease['wall_started']
            and lease['request']['expires_at']-wall > margin
            and lease['monotonic_deadline']-monotonic > margin)



def validate_console_receipt(value):
    fields = {'schema_version', 'request', 'boot_id', 'monotonic_started', 'wall_started',
              'monotonic_deadline', 'before_rules', 'before_sha256', 'main_sha256',
              'before_text_b64', 'request_sha256', 'leased_rules', 'leased_sha256'}
    request_fields = {'schema_version', 'nonce', 'hostname', 'root_filesystem_uuid', 'host_key_sha256',
                      'inventory_alias', 'public_address', 'ssh_port', 'public_sources',
                      'source_revision', 'deployable_digest', 'expires_at'}
    if (not isinstance(value, dict) or set(value) != fields
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or not isinstance(value['request'], dict) or set(value['request']) != request_fields):
        raise ProbeError('legacy-lease-receipt-invalid')
    request = value['request']
    if type(request['schema_version']) is not int or request['schema_version'] != 1 or type(request['expires_at']) is not int:
        raise ProbeError('legacy-lease-receipt-invalid')
    for key in ('before_sha256', 'main_sha256', 'request_sha256', 'leased_sha256'):
        if not isinstance(value[key], str) or not re.fullmatch('[0-9a-f]{64}', value[key]):
            raise ProbeError('legacy-lease-receipt-invalid')
    for key in ('monotonic_started', 'wall_started', 'monotonic_deadline'):
        if type(value[key]) not in (int, float) or not math.isfinite(value[key]) or value[key] < 0:
            raise ProbeError('legacy-lease-receipt-invalid')
    duration = request['expires_at']-value['wall_started']
    if (not 0 < duration <= 900 or abs(value['monotonic_deadline']-value['monotonic_started']-duration) > 1
            or not isinstance(value['boot_id'], str) or str(UUID(value['boot_id'])) != value['boot_id']
            or not isinstance(request['root_filesystem_uuid'], str) or str(UUID(request['root_filesystem_uuid'])) != request['root_filesystem_uuid']
            or not isinstance(request['hostname'], str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', request['hostname'])
            or not isinstance(value['before_rules'], list) or not isinstance(value['leased_rules'], list)
            or not 1 <= len(value['leased_rules']) <= 8
            or not isinstance(value['before_text_b64'], str)):
        raise ProbeError('legacy-lease-receipt-invalid')
    if len(base64.b64decode(value['before_text_b64'], validate=True)) > 262144:
        raise ProbeError('legacy-lease-receipt-invalid')

def inspect_legacy_policy(binding, fragment, *, root=Path('/'), parser=parse_policy):
    """Read-only witness; the caller must independently approve its exact digest."""
    for name in ('ip_tables_names', 'ip6_tables_names', 'eb_tables_names'):
        path = root/'proc/net'/name
        if path.exists() and path.read_bytes().strip():
            raise ProbeError('legacy-firewall-present')
    for unit in ('ufw.service', 'firewalld.service', 'netfilter-persistent.service'):
        state = command(['systemctl', 'show', unit, '--property=ActiveState', '--value']).decode().strip()
        if state not in {'inactive', ''}:
            raise ProbeError('foreign-firewall')
    for relative in ('var/lib/vpn-tailnet-management/transaction.json', 'var/lib/vpn-tailnet-network', 'var/lib/vpn-network-promotion'):
        path = root/relative
        if os.path.lexists(path) and (not path.is_dir() or any(path.iterdir())):
            raise ProbeError('pending-access-state')
    main = read(root/'etc/nftables.conf')
    if os.path.lexists(root/'etc/nftables.d/vpn-tailnet-ssh-sets.nft'):
        raise ProbeError('legacy-layout-unsupported')
    current = stable_rules(json.loads(command(['nft', '-j', 'list', 'ruleset'])))
    validate_owned_rules(current)
    inert, _ = split_inert_tables(current)
    seed = ('\n'+''.join(f"table {item['table']['family']} {item['table']['name']} {{}}\n" for item in inert)).encode()
    base = parser(main+seed)
    lease = None
    base_text = command(['nft', '-s', 'list', 'ruleset'])
    if current != base:
        path = root/'run/vpn-console-bootstrap/receipt.json'
        info = path.parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
            raise ProbeError('legacy-lease-unsafe')
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ProbeError('legacy-lease-unsafe')
        lease = json.loads(read(path))
        validate_console_receipt(lease)
        request = lease['request']
        if (lease['schema_version'] != 1 or lease['request_sha256'] != policy_digest(request)
                or not isinstance(request.get('nonce'), str) or not re.fullmatch('[0-9a-f]{32}', request['nonce'])
                or any(request.get(key) != binding[key] for key in ('inventory_alias', 'public_address', 'ssh_port', 'public_sources', 'host_key_sha256', 'source_revision', 'deployable_digest'))
                or lease['before_sha256'] != policy_digest(lease['before_rules'])
                or lease['main_sha256'] != hashlib.sha256(main).hexdigest()
                or request['hostname'] != command(['hostname']).decode().strip()):
            raise ProbeError('legacy-lease-mismatch')
        receipt_inert, receipt_base = split_inert_tables(lease['before_rules'])
        _, owned_base = split_inert_tables(base)
        if receipt_base != owned_base or (receipt_inert and receipt_inert != inert):
            raise ProbeError('legacy-lease-mismatch')
        marker = 'vpn-console-lease:'+request['nonce']
        without = [entry for entry in current if entry.get('rule', {}).get('comment') != marker]
        marked = [entry['rule'] for entry in current if entry.get('rule', {}).get('comment') == marker]
        _, current_owned = split_inert_tables(current)
        if (lease['leased_sha256'] != policy_digest(receipt_inert+current_owned)
                or without != base or marked != lease['leased_rules'] or len(marked) != len(binding['public_sources'])):
            raise ProbeError('legacy-lease-delta-invalid')
        # Receipt data alone is not authorization: prove every effective rule.
        expected = []
        for source in reversed(binding['public_sources']):
            expected.append({'family': 'inet', 'table': 'filter', 'chain': 'input', 'comment': marker,
                'expr': [{'match': {'op': '==', 'left': {'payload': {'protocol': 'ip6' if ':' in source else 'ip', 'field': 'saddr'}}, 'right': source}},
                         {'match': {'op': '==', 'left': {'payload': {'protocol': 'tcp', 'field': 'dport'}}, 'right': binding['ssh_port']}}, {'counter': {}}, {'accept': None}]})
        if marked != expected:
            raise ProbeError('legacy-lease-delta-invalid')
        boot_id = read(root/'proc/sys/kernel/random/boot_id', 128).decode().strip()
        if not lease_active(lease, boot_id=boot_id, wall=time.time(), monotonic=time.monotonic(), margin=360):
            raise ProbeError('legacy-lease-insufficient')
        if str(UUID(request['root_filesystem_uuid'])) != command(['findmnt', '-n', '-o', 'UUID', '-T', '/']).decode().strip():
            raise ProbeError('legacy-root-mismatch')
        base_text = base64.b64decode(lease['before_text_b64'], validate=True)
        if parser(base_text) != lease['before_rules']:
            raise ProbeError('legacy-replay-mismatch')
        if inert and not receipt_inert:
            base_text += seed
    if parser(base_text) != base:
        raise ProbeError('legacy-replay-mismatch')
    candidate = legacy_candidate(main, binding)
    include = b'include "/etc/nftables.d/vpn-tailnet-ssh-sets.nft"'
    after = parser(candidate.replace(include, fragment)+seed)
    validate_owned_rules(after)
    trimmed = [entry for entry in after if not (
        entry.get('set', {}).get('name') in {'vpn_tailnet_ssh_v4', 'vpn_tailnet_ssh_v6'}
        or entry.get('rule', {}).get('comment', '').startswith('vpn-bootstrap-'))]
    if trimmed != base:
        raise ProbeError('legacy-candidate-changed-original')
    value = {'schema_version': 1, 'binding_sha256': policy_digest(binding),
             'main_sha256': hashlib.sha256(main).hexdigest(), 'base_rules': base,
             'observed_rules': current, 'base_text_b64': base64.b64encode(base_text).decode(),
             'candidate_main_b64': base64.b64encode(candidate).decode(),
             'candidate_fragment_sha256': hashlib.sha256(fragment).hexdigest(),
             'candidate_rules': after, 'service': _firewall_service(), 'console_lease': lease}
    value['plan_sha256'] = review_digest(value)
    return value


def review_digest(plan):
    # The already-supported exact object-free daemon quartet may appear during
    # pinned package installation. Bind every effective object; ignore only
    # that inert addition, never an object, expression, include or service.
    projection = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    for key in ('base_rules', 'observed_rules', 'candidate_rules'):
        _, projection[key] = split_inert_tables(projection[key])
    projection['base_text_b64'] = policy_digest(projection['base_rules'])
    return policy_digest(projection)

def firewall_service_state(raw):
    values = dict(line.split("=", 1) for line in raw.decode().splitlines())
    if (set(values) != {"ActiveState", "UnitFileState"}
            or values["ActiveState"] not in {"active", "inactive"}
            or values["UnitFileState"] not in {"enabled", "disabled"}):
        raise ProbeError("firewall-service-unsupported")
    return values


def _firewall_service():
    return firewall_service_state(command(["systemctl", "show", "nftables.service",
        "--property=ActiveState", "--property=UnitFileState", "--no-pager"]))


def validate_owned_firewall(binding, *, fragment_parser):
    """Prove owned files match the kernel before installation, without file writes.

    The controller supplies the existing firewall fragment parser from its
    source-bound helper. Parsing runs only in a new network namespace; the
    candidate arrives on stdin and never needs a guest temporary file.
    """
    main = read(Path("/etc/nftables.conf"))
    include = b'include "/etc/nftables.d/vpn-tailnet-ssh-sets.nft"'
    if (not main.startswith(b"#!/usr/sbin/nft -f\n# Managed by Ansible role `firewall`.")
            or re.findall(rb'\binclude\b[^\n]*', main) != [include]):
        raise ProbeError("unowned-firewall-configuration")
    fragment = read(Path("/etc/nftables.d/vpn-tailnet-ssh-sets.nft"))
    try:
        fragment_parser(fragment)
    except (TypeError, ValueError, RuntimeError) as error:
        raise ProbeError("unowned-firewall-fragment") from error
    port = binding["ssh_port"]
    lines = [f'iifname "tailscale0" tcp dport {port} ip saddr @vpn_tailnet_ssh_v4 accept',
             f'iifname "tailscale0" tcp dport {port} ip6 saddr @vpn_tailnet_ssh_v6 accept',
             f'iifname "tailscale0" tcp dport {port} drop']
    try:
        positions = [main.index(line.encode()) for line in lines]
    except ValueError as error:
        raise ProbeError("firewall-source-order") from error
    if positions != sorted(positions):
        raise ProbeError("firewall-source-order")
    _firewall_service()
    original = stable_rules(json.loads(command(["nft", "-j", "list", "ruleset"])))
    validate_owned_rules(original)
    inert, _ = split_inert_tables(original)
    seed = ("\n" + "".join(f"table {entry['table']['family']} {entry['table']['name']} {{}}\n" for entry in inert)).encode()
    program = (
        "import subprocess,sys; "
        "subprocess.run(['/usr/sbin/nft','-f','-'],input=sys.stdin.buffer.read(),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        "subprocess.run(['/usr/sbin/nft','-j','list','ruleset'],check=True)"
    )
    candidate = command(["unshare", "--net", "/usr/bin/python3", "-I", "-B", "-c", program],
                        input_data=main.replace(include, fragment) + seed)
    if stable_rules(json.loads(candidate)) != original:
        raise ProbeError("firewall-runtime-drift")


def decode_endpoint(value):
    address, port = value.split(":")
    raw = bytes.fromhex(address)
    if len(raw) not in (4, 16):
        raise ProbeError("socket-invalid")
    # proc renders each native-endian 32-bit word as hexadecimal.
    raw = b"".join(struct.pack("=I", int(address[i:i + 8], 16)) for i in range(0, len(address), 8))
    decoded = ipaddress.ip_address(raw)
    if isinstance(decoded, ipaddress.IPv6Address) and decoded.ipv4_mapped is not None:
        decoded = decoded.ipv4_mapped
    return str(decoded), int(port, 16)


def ssh_socket():
    inodes = set()
    process = os.getppid()
    for _ in range(32):
        base = Path("/proc") / str(process)
        executable = os.readlink(base / "exe")
        if executable in {"/usr/sbin/sshd", "/usr/lib/openssh/sshd-session", "/usr/libexec/sshd-session"}:
            for entry in (base / "fd").iterdir():
                try:
                    target = os.readlink(entry)
                except FileNotFoundError:
                    continue
                found = re.fullmatch(r"socket:\[(\d+)\]", target)
                if found:
                    inodes.add(found[1])
        fields = (base / "stat").read_text().rsplit(")", 1)[1].split()
        process = int(fields[1])
        if process <= 1:
            break
    found = set()
    for family in ("tcp", "tcp6"):
        for line in (Path("/proc/net") / family).read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 10 and fields[3] == "01" and fields[9] in inodes:
                found.add((*decode_endpoint(fields[1]), *decode_endpoint(fields[2])))
    if len(found) != 1:
        raise ProbeError("ssh-socket-ambiguous")
    return next(iter(found))


def probe(binding, user, address, *, fragment_parser, policy_approval=None, candidate_fragment=None, preinstall=False, package_version=None):
    local, port, peer, _peer_port = ssh_socket()
    sources = binding["public_sources"] if address == binding["public_address"] else binding["approved_sources"]
    if local != address or port != binding["ssh_port"] or peer not in sources:
        raise ProbeError("ssh-socket-mismatch")
    policy = command(["/usr/sbin/sshd", "-T"]).decode().splitlines()
    if [line for line in policy if line.startswith("port ")] != [f"port {port}"] or "usedns no" not in policy:
        raise ProbeError("ssh-policy-unsupported")
    if "hostkey /etc/ssh/ssh_host_ed25519_key" not in policy:
        raise ProbeError("ssh-host-key-unsupported")
    fields = read(Path("/etc/ssh/ssh_host_ed25519_key.pub"), 4096).decode().split()
    if len(fields) < 2 or fields[0] != "ssh-ed25519" or hashlib.sha256(base64.b64decode(fields[1], validate=True)).hexdigest() != binding["host_key_sha256"]:
        raise ProbeError("ssh-host-key-mismatch")
    if preinstall:
        for name in ("ip_tables_names", "ip6_tables_names", "eb_tables_names"):
            path = Path("/proc/net") / name
            if path.exists() and path.read_bytes().strip():
                raise ProbeError("legacy-firewall-present")
        for name in ("ufw.service", "firewalld.service", "netfilter-persistent.service"):
            state = command(["systemctl", "show", name, "--property=ActiveState", "--value"]).decode().strip()
            if state not in {"inactive", ""}:
                raise ProbeError("foreign-firewall")
        for relative in ("var/lib/vpn-tailnet-management/transaction.json", "var/lib/vpn-tailnet-network", "var/lib/vpn-network-promotion"):
            path = Path("/") / relative
            if os.path.lexists(path) and (not path.is_dir() or any(path.iterdir())):
                raise ProbeError("pending-access-state")
        if not empty_firewall_baseline():
            if policy_approval is None:
                validate_owned_firewall(binding, fragment_parser=fragment_parser)
            else:
                plan = inspect_legacy_policy(binding, candidate_fragment)
                if policy_approval != {'schema_version': 1, 'decision': 'approve-managed-legacy-v1', 'plan_sha256': plan['plan_sha256']}:
                    raise ProbeError('legacy-approval-mismatch')
        elif os.path.lexists("/etc/nftables.conf"):
            main = read(Path("/etc/nftables.conf"))
            metadata = command(["dpkg-query", "-W", "-f=${Conffiles}", "nftables"]).decode().splitlines()
            digests = [line.split()[1] for line in metadata if len(line.split()) == 2 and line.split()[0] == "/etc/nftables.conf"]
            if len(digests) != 1 or hashlib.md5(main, usedforsecurity=False).hexdigest() != digests[0]:
                raise ProbeError("unowned-firewall-configuration")
            if _firewall_service() != {"ActiveState": "inactive", "UnitFileState": "disabled"}:
                raise ProbeError("unowned-empty-firewall-service")
        preflight_tailnet_commands(package_version)
    return {"user": user, "host": peer, "addr": peer, "laddr": local, "lport": port}
