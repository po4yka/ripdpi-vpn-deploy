"""Firewall-owned adapter for the single Tailnet bootstrap transaction.

The caller holds the access transaction lock. This adapter never acquires that
lock, creates another journal, or confirms enrollment. Early boot uses only
files and netlink; all systemctl operations belong to the online phase.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat

import tailnet_management as domain
from tailnet_bootstrap_probe import ProbeError, firewall_service_state, split_inert_tables, stable_rules, validate_owned_rules

_spec = importlib.util.spec_from_file_location("tailnet_network_files", Path(__file__).with_name("tailnet-network-guest.py"))
files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(files)

INCLUDE = 'include "/etc/nftables.d/vpn-tailnet-ssh-sets.nft"'
HEADER = '# Managed by Ansible role `firewall`.'


def foundation(binding):
    domain.validate_binding(binding)
    port = binding["ssh_port"]
    public = "\n".join(
        f'    {"ip6" if ":" in address else "ip"} saddr {address} tcp dport {port} accept'
        for address in binding["public_sources"]
    )
    return f'''#!/usr/sbin/nft -f
{HEADER} Bootstrap access foundation; ordinary deploy replaces it.
destroy table inet filter
table inet filter {{
  {INCLUDE}
  chain input {{
    type filter hook input priority 0; policy drop;
    iifname "lo" accept
    iifname "tailscale0" tcp dport {port} ip saddr @vpn_tailnet_ssh_v4 accept
    iifname "tailscale0" tcp dport {port} ip6 saddr @vpn_tailnet_ssh_v6 accept
    iifname "tailscale0" tcp dport {port} drop
{public}
    tcp dport {port} drop
    ct state established,related accept
    ct state invalid drop
    ip protocol icmp accept
    meta l4proto ipv6-icmp accept
    udp sport 67 udp dport 68 accept
    udp sport 547 udp dport 546 accept
  }}
  chain forward {{ type filter hook forward priority 0; policy drop; }}
  chain output {{ type filter hook output priority 0; policy accept; }}
}}
'''.encode()


def _stable(document):
    """Ignore kernel identifiers and packet counts, never rule expressions."""
    try:
        return stable_rules(document)
    except ProbeError as error:
        raise domain.Refusal("bootstrap-firewall-rules-invalid") from error


def _record(data, *, mode=0o644):
    return {"data_b64": base64.b64encode(data).decode(), "sha256": hashlib.sha256(data).hexdigest(),
            "uid": os.geteuid(), "gid": os.getegid(), "mode": mode}


class Firewall:
    def __init__(self, root=Path("/"), command=None):
        self.root = root
        self.main = root / "etc/nftables.conf"
        self.fragment = root / "etc/nftables.d/vpn-tailnet-ssh-sets.nft"
        self.state = root / "var/lib/vpn-tailnet-management"
        self.command = command or files.Runtime._command

    @contextmanager
    def _errors(self):
        try:
            yield
        except (files.Refusal, OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
            raise domain.Refusal("bootstrap-firewall-refused") from error

    def _read(self, path):
        if not os.path.lexists(path):
            return None
        return files._record(path)

    def _write(self, path, record):
        if record is None:
            path.unlink(missing_ok=True)
            files._sync(path.parent)
        else:
            files._atomic(path, files._record_bytes(record), record["mode"], record["uid"], record["gid"])

    def _expanded(self, main, fragment):
        content = files._record_bytes(main)
        includes = re.findall(rb'\binclude\b[^\n]*', content)
        if not includes:
            return content
        if includes != [INCLUDE.encode()] or fragment is None:
            raise domain.Refusal("bootstrap-firewall-includes-unsupported")
        value = files._record_bytes(fragment)
        files.canonical_fragment(value)
        return content.replace(INCLUDE.encode(), value)

    @contextmanager
    def _candidate(self, content):
        files._directory(self.state, private=True)
        path = self.state / (".nft-" + secrets.token_hex(16))
        files._atomic(path, content)
        try:
            yield path
        finally:
            path.unlink(missing_ok=True)
            files._sync(self.state)

    def _parse(self, content):
        # A private network namespace gives the real nft parser and kernel the
        # whole candidate without touching host policy. No shell or host mounts.
        program = (
            "import subprocess,sys; "
            "subprocess.run(['/usr/sbin/nft','-f',sys.argv[1]],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
            "subprocess.run(['/usr/sbin/nft','-j','list','ruleset'],check=True)"
        )
        with self._candidate(content) as path:
            raw = self.command(["unshare", "--net", "/usr/bin/python3", "-c", program, str(path)])
        return _stable(json.loads(raw))

    def _rules(self):
        return _stable(json.loads(self.command(["nft", "-j", "list", "ruleset"])))

    def _service(self):
        raw = self.command(["systemctl", "show", "nftables.service", "--property=ActiveState", "--property=UnitFileState", "--no-pager"])
        try:
            return firewall_service_state(raw)
        except ProbeError as error:
            raise domain.Refusal("bootstrap-firewall-service-unsupported") from error

    def _preflight(self):
        for unit in ("ufw.service", "firewalld.service", "netfilter-persistent.service"):
            state = self.command(["systemctl", "show", unit, "--property=ActiveState", "--value"]).decode().strip()
            if state not in {"inactive", ""}:
                raise domain.Refusal("bootstrap-foreign-firewall")
        # Do not race an independently owned network transaction. Existing
        # initialized state is deliberately not inferred to be safe from age.
        for name in ("vpn-tailnet-network", "vpn-network-promotion"):
            path = self.root / "var/lib" / name
            if path.exists() and any(path.iterdir()):
                raise domain.Refusal("bootstrap-network-state-present")

    def snapshot(self, binding):
        with self._errors():
            domain.validate_binding(binding)
            self._preflight()
            main, fragment = self._read(self.main), self._read(self.fragment)
            if main is None:
                raise domain.Refusal("bootstrap-nft-package-foundation-required")
            original = self._rules()
            service = self._service()
            content = files._record_bytes(main)
            _, owned = split_inert_tables(original)
            seed = self._inert_seed(original)
            if not owned:
                # Installation is inert and may leave the distribution's
                # original package conffile. Never adopt a hand-edited file.
                conffiles = self.command(["dpkg-query", "-W", "-f=${Conffiles}", "nftables"]).decode().splitlines()
                expected = [line.split()[1] for line in conffiles if line.split() and line.split()[0] == "/etc/nftables.conf" and len(line.split()) == 2]
                if (len(expected) != 1 or hashlib.md5(content, usedforsecurity=False).hexdigest() != expected[0]
                        or fragment is not None or service != {"ActiveState": "inactive", "UnitFileState": "disabled"}):
                    raise domain.Refusal("bootstrap-empty-firewall-unowned")
                candidate_main = _record(foundation(binding))
            else:
                try:
                    validate_owned_rules(original)
                except ProbeError as error:
                    raise domain.Refusal("bootstrap-foreign-firewall") from error
                if HEADER.encode() not in content.splitlines() and not content.startswith(b"#!/usr/sbin/nft -f\n" + HEADER.encode()):
                    raise domain.Refusal("bootstrap-firewall-unowned")
                if fragment is None or content.count(INCLUDE.encode()) != 1:
                    raise domain.Refusal("bootstrap-firewall-layout-unsupported")
                if self._parse(self._expanded(main, fragment) + seed) != original:
                    raise domain.Refusal("bootstrap-firewall-runtime-drift")
                port = binding["ssh_port"]
                lines = [f'iifname "tailscale0" tcp dport {port} ip saddr @vpn_tailnet_ssh_v4 accept',
                         f'iifname "tailscale0" tcp dport {port} ip6 saddr @vpn_tailnet_ssh_v6 accept',
                         f'iifname "tailscale0" tcp dport {port} drop']
                offsets = [content.index(line.encode()) for line in lines]
                if offsets != sorted(offsets):
                    raise domain.Refusal("bootstrap-firewall-source-order")
                candidate_main = main
            candidate_fragment = _record(domain.canonical_sources_fragment(binding["approved_sources"]).encode())
            before_text = self.command(["nft", "-s", "list", "ruleset"])
            # Prove replay roundtrips the exact effective policy before arming.
            if self._parse(before_text) != original:
                raise domain.Refusal("bootstrap-firewall-snapshot-drift")
            result = {"schema_version": 1, "main": main, "fragment": fragment,
                      "fragment_directory_existed": self.fragment.parent.exists(),
                      "candidate_main": candidate_main, "candidate_fragment": candidate_fragment,
                      "service": service, "before_rules": original, "rules_text": _record(before_text),
                      "boot_rules": self._parse(self._expanded(main, fragment)),
                      "after_rules": self._parse(self._expanded(candidate_main, candidate_fragment) + seed)}
            result["sha256"] = hashlib.sha256(files._json(result)).hexdigest()
            self.validate_snapshot(result)
            return result

    def validate_snapshot(self, snapshot):
        with self._errors():
            fields = {"schema_version", "main", "fragment", "fragment_directory_existed", "candidate_main", "candidate_fragment", "service", "before_rules", "rules_text", "boot_rules", "after_rules", "sha256"}
            if set(snapshot) != fields or type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1:
                raise domain.Refusal("bootstrap-firewall-snapshot-invalid")
            if hashlib.sha256(files._json({k: v for k, v in snapshot.items() if k != "sha256"})).hexdigest() != snapshot["sha256"]:
                raise domain.Refusal("bootstrap-firewall-snapshot-invalid")
            for name in ("main", "candidate_main", "candidate_fragment", "rules_text"):
                files._record_bytes(snapshot[name])
            if snapshot["fragment"] is not None:
                files._record_bytes(snapshot["fragment"])
            if (type(snapshot["fragment_directory_existed"]) is not bool
                    or snapshot["service"] not in [{"ActiveState": active, "UnitFileState": enabled} for active in ("active", "inactive") for enabled in ("enabled", "disabled")]
                    or any(not isinstance(snapshot[k], list) for k in ("before_rules", "boot_rules", "after_rules"))):
                raise domain.Refusal("bootstrap-firewall-snapshot-invalid")
            self._expanded(snapshot["main"], snapshot["fragment"])
            self._expanded(snapshot["candidate_main"], snapshot["candidate_fragment"])

    def _inert_seed(self, entries):
        inert, _ = split_inert_tables(entries)
        return ("\n" + "".join(
            f"table {item['table']['family']} {item['table']['name']} {{}}\n"
            for item in inert
        )).encode()

    def _boot_with_inert(self, snapshot):
        inert, _ = split_inert_tables(snapshot["before_rules"])
        _, boot = split_inert_tables(snapshot["boot_rules"])
        return inert + boot

    def _graph(self, snapshot):
        if self._read(self.main) not in (snapshot["main"], snapshot["candidate_main"]):
            raise domain.Refusal("bootstrap-firewall-file-drift")
        if self._read(self.fragment) not in (snapshot["fragment"], snapshot["candidate_fragment"]):
            raise domain.Refusal("bootstrap-firewall-file-drift")
        if self._rules() not in (snapshot["before_rules"], snapshot["boot_rules"], self._boot_with_inert(snapshot), snapshot["after_rules"], []):
            raise domain.Refusal("bootstrap-firewall-runtime-drift")

    def _load(self, content):
        with self._candidate(content) as path:
            self.command(["nft", "-c", "-f", str(path)])
            self.command(["nft", "-f", str(path)])

    def apply(self, snapshot, binding):
        with self._errors():
            self.validate_snapshot(snapshot)
            self._graph(snapshot)
            if self._rules() != snapshot["before_rules"] or self._service() != snapshot["service"]:
                raise domain.Refusal("bootstrap-firewall-preapply-drift")
            self.fragment.parent.mkdir(mode=0o755, exist_ok=True)
            files._directory(self.fragment.parent)
            self._write(self.fragment, snapshot["candidate_fragment"])
            self._write(self.main, snapshot["candidate_main"])
            candidate = self._expanded(snapshot["candidate_main"], snapshot["candidate_fragment"])
            complete = candidate + self._inert_seed(snapshot["before_rules"])
            self._load(complete)
            self.command(["systemctl", "enable", "nftables.service"])
            self.command(["systemctl", "start", "nftables.service"])
            # An inactive service may load a canonical conffile containing
            # flush ruleset. Reconcile only that exact observed package load,
            # never an arbitrary concurrent rule change.
            if self._rules() != snapshot["after_rules"]:
                if self._rules() != self._parse(candidate):
                    raise domain.Refusal("bootstrap-firewall-service-load-drift")
                self._load(complete)
            self.verify(snapshot, binding)

    def verify(self, snapshot, binding):
        with self._errors():
            self.validate_snapshot(snapshot)
            if (self._read(self.main) != snapshot["candidate_main"] or self._read(self.fragment) != snapshot["candidate_fragment"]
                    or self._rules() != snapshot["after_rules"] or self._service() != {"ActiveState": "active", "UnitFileState": "enabled"}):
                raise domain.Refusal("bootstrap-firewall-verification-failed")

    def restore(self, snapshot, binding, *, early_boot=False):
        with self._errors():
            self.validate_snapshot(snapshot)
            self._graph(snapshot)
            self._write(self.main, snapshot["main"])
            if self.fragment.parent.exists():
                self._write(self.fragment, snapshot["fragment"])
                if not snapshot["fragment_directory_existed"]:
                    self.fragment.parent.rmdir()
                    files._sync(self.fragment.parent.parent)
            # The graph check excluded foreign runtime policy before this full
            # atomic replay. No individual chain flushing or best-effort edits.
            content = b"flush ruleset\n" + files._record_bytes(snapshot["rules_text"])
            self._load(content)
            if not early_boot:
                enabled = snapshot["service"]["UnitFileState"] == "enabled"
                active = snapshot["service"]["ActiveState"] == "active"
                self.command(["systemctl", "enable" if enabled else "disable", "nftables.service"])
                self.command(["systemctl", "start" if active else "stop", "nftables.service"])
                # Stopping nftables flushes owned tables; starting it may load
                # package defaults. Restore the original effective snapshot last.
                self._load(content)
                if self._service() != snapshot["service"]:
                    raise domain.Refusal("bootstrap-firewall-service-restore-failed")
            if self._rules() != snapshot["before_rules"]:
                raise domain.Refusal("bootstrap-firewall-restore-failed")
