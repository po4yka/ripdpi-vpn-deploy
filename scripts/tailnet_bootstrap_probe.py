"""Read-only bootstrap preflight, sent on pinned SSH stdin before installation."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess


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
    """No foreign tables or chains may be adopted as repository policy."""
    _, owned = split_inert_tables(entries)
    for entry in owned:
        table, chain = entry.get("table"), entry.get("chain")
        if table and (table.get("family"), table.get("name")) not in {("inet", "filter"), ("inet", "nat")}:
            raise ProbeError("foreign-firewall")
        if chain and (chain.get("family") != "inet" or
                (chain.get("table"), chain.get("name")) not in {
                    ("filter", "input"), ("filter", "forward"),
                    ("filter", "output"), ("nat", "postrouting")}):
            raise ProbeError("foreign-firewall")


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


def probe(binding, user, address, *, fragment_parser, preinstall=False):
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
            validate_owned_firewall(binding, fragment_parser=fragment_parser)
        elif os.path.lexists("/etc/nftables.conf"):
            main = read(Path("/etc/nftables.conf"))
            metadata = command(["dpkg-query", "-W", "-f=${Conffiles}", "nftables"]).decode().splitlines()
            digests = [line.split()[1] for line in metadata if len(line.split()) == 2 and line.split()[0] == "/etc/nftables.conf"]
            if len(digests) != 1 or hashlib.md5(main, usedforsecurity=False).hexdigest() != digests[0]:
                raise ProbeError("unowned-firewall-configuration")
            if _firewall_service() != {"ActiveState": "inactive", "UnitFileState": "disabled"}:
                raise ProbeError("unowned-empty-firewall-service")
        for executable in (Path("/usr/bin/tailscale"), Path("/usr/local/bin/tailscale")):
            if executable.exists():
                info = executable.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                    raise ProbeError("unsafe-tailnet-command")
                value = json.loads(command([str(executable), "status", "--json"]))
                if value.get("BackendState") != "NeedsLogin":
                    raise ProbeError("existing-tailnet-identity")
    return {"user": user, "host": peer, "addr": peer, "laddr": local, "lport": port}
