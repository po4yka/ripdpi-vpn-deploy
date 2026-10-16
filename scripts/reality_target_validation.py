#!/usr/bin/env python3
"""Read-only, bounded REALITY target observations. Never emits private inputs."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import shlex
import stat
import ssl
import sys
import time

from bootstrap_readiness import CommandTimeout, ReadinessError, cancellation, run_command

HERE = Path(__file__).resolve().parent
MAX_NAMES = 16
MAX_ADDRESSES = 16
CLIENT_HASHES = {
    "3989bb0f568e2660f284802f39a01477ca1b39215a99c8f21d16e68a70239ff1",
    "356696645768b000bf89d6d5a7229084ec84a626daf245797ab4b2ae240c867f",
    "6ff9756421f4b43702bd954ff28537ea70eb041ba8a82096038669b7123edc06",
}
CLIENT_PROFILE_HASH = "702534e73a2548e34bbce51b9e086bb4b107b9fb2aff21b83d48b8907033f88f"


class Refused(Exception):
    """Categorical diagnostic only."""


def names(value):
    if not isinstance(value, str) or not 0 < len(value) <= 4096:
        raise Refused("invalid_names")
    if any(not part.strip() for part in value.split(",")):
        raise Refused("invalid_names")
    result = []
    for name in re.split(r"[,\s]+", value.strip()):
        name = name.lower().removesuffix(".")
        if (not name or len(name) > 253 or "." not in name
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                       for label in name.split("."))):
            raise Refused("invalid_names")
        try:
            ipaddress.ip_address(name)
        except ValueError:
            pass
        else:
            raise Refused("invalid_names")
        if name not in result:
            result.append(name)
    if not 1 <= len(result) <= MAX_NAMES:
        raise Refused("invalid_names")
    return result


def endpoint(value):
    try:
        if value.startswith("["):
            match = re.fullmatch(r"\[([^\]]+)\]:([0-9]+)", value)
            if not match:
                raise ValueError
            host, port = match.groups()
            ipaddress.IPv6Address(host)
        else:
            if value.count(":") != 1 or "[" in value or "]" in value:
                raise ValueError
            host, port = value.rsplit(":", 1)
        if not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            candidates = names(host)
            if len(candidates) != 1 or any(c in host for c in ", \t\r\n"):
                raise ValueError
            host = candidates[0]
        return host, int(port)
    except (ValueError, AttributeError, Refused):
        raise Refused("invalid_endpoint") from None


class Budget:
    def __init__(self):
        try:
            self.stage = float(os.environ.get("PROBE_TIMEOUT", "12"))
            total = float(os.environ.get("VALIDATION_TIMEOUT", "120"))
            if not all(math.isfinite(x) and 0 < x <= 600 for x in (self.stage, total)):
                raise ValueError
        except ValueError:
            raise Refused("invalid_budget") from None
        self.end = min(time.monotonic() + total, float(os.environ.get("REALITY_VALIDATION_END", "inf")))
        if math.isnan(self.end):
            raise Refused("invalid_budget")

    def run(self, stage, command, **kwargs):
        left = min(self.stage, self.end - time.monotonic())
        if left <= 0:
            raise Refused("aggregate_timeout")
        try:
            code, data = run_command(command, timeout=left, capture=True, **kwargs)
        except CommandTimeout:
            raise Refused("aggregate_timeout" if time.monotonic() >= self.end else stage + "_timeout") from None
        except ReadinessError:
            raise Refused(stage + "_unavailable") from None
        if code:
            raise Refused(stage + "_failed")
        return data.decode("utf-8")


def worker(kind, payload):
    """Blocking libc DNS and TLS are isolated in an owned bounded session."""
    if kind == "dns":
        rows = socket.getaddrinfo(payload["host"], None, type=socket.SOCK_STREAM)
        print(json.dumps(sorted({row[4][0] for row in rows})))
    else:
        context = ssl.create_default_context(cafile=os.environ.get("REALITY_CA_FILE"))
        context.hostname_checks_common_name = False
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.set_alpn_protocols(["h2", "http/1.1"])
        try:
            with socket.create_connection((payload["ip"], payload["port"])) as raw:
                with context.wrap_socket(raw, server_hostname=payload["sni"]) as conn:
                    print(json.dumps({"h2": conn.selected_alpn_protocol() == "h2"}))
        except ssl.SSLCertVerificationError:
            print(json.dumps({"error": "certificate_validation_failed"}))


def call_worker(budget, kind, payload):
    return json.loads(budget.run(kind, [sys.executable, str(Path(__file__).resolve()),
                                     "worker", kind], input_data=json.dumps(payload).encode()))


def load_inputs(budget):
    target, configured = os.environ.get("TARGET"), os.environ.get("SERVER_NAMES")
    normalized = names(configured) if configured is not None else None
    if target is None or configured is None:
        source = os.environ.get("SOPS_FILE", str(Path.home() / ".config/vpn-provision" /
                                (os.environ.get("ENV", "prod") + ".secrets.sops.yaml")))
        data = json.loads(budget.run("secrets", ["sops", "--decrypt", "--output-type", "json", source],
                                      output_limit=1_048_576))
        xray = data["xray"]
        target = xray["target"] if target is None else target
        configured = " ".join(xray["server_names"]) if configured is None else configured
    if normalized is None:
        normalized = names(configured)
    mode = os.environ.get("TARGET_MODE", "borrowed")
    host, port = endpoint(target)
    if mode == "owned-public":
        host, port = endpoint(os.environ.get("PUBLIC_ENDPOINT", ""))
        if names(os.environ.get("OWNED_SNI", "")) != normalized or len(normalized) != 1:
            raise Refused("owned_sni_mismatch")
    elif mode != "borrowed":
        raise Refused("invalid_mode")
    return mode, host, port, normalized


def http(budget, ip, port, sni, *, client=None):
    address = f"[{ip}]" if ":" in ip else ip
    command = [*(client if client else ["curl", "--disable"]), "--silent", "--show-error", "--noproxy", "*",
               "--output", os.devnull, "--write-out", "%{http_code}/%{http_version}" if client else "%{http_code}",
               "--resolve", f"{sni}:{port}:{address}", f"https://{sni}:{port}/"]
    if not client:
        command.append("--http1.1")
    ca = os.environ.get("REALITY_CA_FILE")
    if ca:
        command.extend(["--cacert", ca])
    result = budget.run("client" if client else "http", command)
    if client:
        result, separator, version = result.partition("/")
        if separator != "/" or version != "2":
            raise Refused("client_failed")
    if not re.fullmatch(r"[1-5][0-9]{2}", result):
        raise Refused("client_failed" if client else "https_no_response")
    return result


def pinned_client():
    directory = os.environ.get("REALITY_CLIENT_DIR")
    if not directory:
        return None
    root = Path(directory)
    try:
        binary = root / "curl-impersonate-chrome"
        profile = root / "curl_chrome116"
        # Bound regular public executable reads; unknown engines cannot claim compatibility.
        for path, hashes in ((binary, CLIENT_HASHES), (profile, {CLIENT_PROFILE_HASH})):
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as source:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise Refused("client_pin_mismatch")
                data = source.read(32 * 1024 * 1024 + 1)
            if len(data) > 32 * 1024 * 1024 or hashlib.sha256(data).hexdigest() not in hashes:
                raise Refused("client_pin_mismatch")
        # Only the exact pinned profile reaches this parser. Execute its argv
        # directly so --disable is first and ambient curlrc cannot weaken trust.
        profile_text = data.decode("utf-8")
        arguments = profile_text.split('"$dir/curl-impersonate-chrome"', 1)[1]
        arguments = arguments.rsplit('"$@"', 1)[0].replace("\\\n", "")
        return [str(binary), "--disable", *shlex.split(arguments)]
    except OSError:
        raise Refused("client_unavailable") from None


def collect(budget, mode, host, port, configured, *, metadata=False):
    reasons, observations = [], []
    compatibility = "unavailable"
    client = pinned_client()
    client_errors = []
    ips = call_worker(budget, "dns", {"host": host})
    if not ips or len(ips) > MAX_ADDRESSES:
        raise Refused("dns_address_limit")
    if any(ipaddress.ip_address(ip).is_loopback or ipaddress.ip_address(ip).is_unspecified for ip in ips):
        if mode == "owned-public":
            raise Refused("public_endpoint_loopback")
        raise Refused("borrowed_endpoint_loopback")
    for ip in ips:
        failed, asn, prefix = 0, "", ""
        if metadata:
            try:
                fields = budget.run("metadata", [str(HERE / "probe-asn.sh"), ip]).strip().split("\t")
                if len(fields) != 5 or not fields[1].isdigit():
                    raise Refused("asn_lookup_failed")
                asn, prefix = "AS" + fields[1], str(ipaddress.ip_network(fields[2]))
            except (Refused, ValueError) as error:
                reasons.append(str(error) if isinstance(error, Refused) else "asn_lookup_failed")
        for sni in configured:
            pair_reasons = []
            try:
                result = call_worker(budget, "tls", dict(ip=ip, port=port, sni=sni))
                if result.get("error"):
                    pair_reasons.append(result["error"])
                elif not result["h2"]:
                    pair_reasons.append("h2_unavailable")
                status = http(budget, ip, port, sni)
                if not metadata and not (status.startswith(("2", "3")) or status in {"403", "404"}):
                    pair_reasons.append("http_status_failed")
            except Refused as error:
                pair_reasons.append(str(error))
            if client:
                try:
                    http(budget, ip, port, sni, client=client)
                except Refused as error:
                    client_errors.append(str(error))
            failed += bool(pair_reasons)
            reasons.extend(pair_reasons)
        observations.append((ip, asn, prefix, len(configured), failed))
    if client:
        compatibility = ("unavailable" if "client_unavailable" in client_errors
                         else "failed" if client_errors else "passed")
    reasons.extend(client_errors)
    return reasons, observations, compatibility


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "bounded":
        try:
            with cancellation():
                Budget().run(sys.argv[2], sys.argv[3:])
            return 0
        except (Refused, ValueError):
            return 1
    if len(sys.argv) > 1 and sys.argv[1] == "deadline":
        try:
            print(Budget().end)
            return 0
        except (Refused, ValueError):
            return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["validate", "collect", "worker"])
    parser.add_argument("kind", nargs="?")
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--reasons", type=Path)
    parser.add_argument("--names", type=Path)
    args = parser.parse_args()
    if args.action == "worker":
        try:
            worker(args.kind, json.load(sys.stdin))
            return 0
        except (OSError, ValueError):
            return 1
    reasons, observations, compatibility, mode = [], [], "unavailable", "unknown"
    try:
        with cancellation():
            budget = Budget()
            mode, host, port, configured = load_inputs(budget)
            if args.names:
                args.names.write_text(" ".join(configured))
            reasons, observations, compatibility = collect(budget, mode, host, port, configured,
                                                          metadata=args.action == "collect")
    except Refused as error:
        reasons.append(str(error))
    except (OSError, ValueError, KeyError, TypeError):
        reasons.append("invalid_configuration")
    if args.action == "collect":
        args.observations.write_text("".join("\t".join(map(str, row)) + "\n" for row in observations))
        args.reasons.write_text("\n".join(sorted(set(reasons))))
    else:
        print(json.dumps(dict(schema_version=1, mode=mode, hygiene="failed" if not observations or any(not r.startswith("client_") for r in reasons) else "passed",
                              reason_codes=sorted(set(reasons)), client_compatibility=compatibility,
                              client_engine="curl-impersonate-0.6.1/chrome116" if compatibility != "unavailable" else None,
                              filtered_survival="unverified", promotion="not_authorized",
                              checked_pairs=sum(row[3] for row in observations))))
    return int(bool(reasons))


if __name__ == "__main__":
    sys.exit(main())
