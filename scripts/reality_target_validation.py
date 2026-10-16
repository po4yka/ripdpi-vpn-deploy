"""Finite, redacted REALITY target hygiene using actual TLS hostname checks."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import time

from bootstrap_readiness import run_command, ReadinessError, cancellation
from transport_semantics import hostname_valid


class ValidationError(ValueError):
    pass


def names(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValidationError("invalid-server-names")
    if any(not part.strip() for part in value.split(",")):
        raise ValidationError("invalid-server-names")
    result = []
    for raw in re.split(r"[\s,]+", value.strip()):
        try:
            name = (raw[:-1] if raw.endswith(".") else raw).encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValidationError("invalid-server-names") from None
        if not name or not hostname_valid(name) or "*" in name:
            raise ValidationError("invalid-server-names")
        if name not in result:
            result.append(name)
    if not 1 <= len(result) <= 8:
        raise ValidationError("invalid-server-names")
    return result


def endpoint(value):
    if not isinstance(value, str) or len(value) > 512 or any(ord(c) <= 32 for c in value):
        raise ValidationError("invalid-endpoint")
    if value.startswith("["):
        host, separator, port = value[1:].partition("]:")
        if not separator:
            raise ValidationError("invalid-endpoint")
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            raise ValidationError("invalid-endpoint") from None
    else:
        host, separator, port = value.rpartition(":")
        if not separator:
            host, port = value, "443"
        if ":" in host:
            raise ValidationError("invalid-endpoint")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not hostname_valid(host):
                raise ValidationError("invalid-endpoint")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValidationError("invalid-endpoint")
    return host, int(port)


def worker(kind):
    data = json.loads(sys.stdin.buffer.read(8192))
    if kind == "dns":
        addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(data["host"], data["port"], type=socket.SOCK_STREAM)))
        if not 1 <= len(addresses) <= 8:
            raise ValidationError("dns-empty-or-unbounded")
        print(json.dumps(addresses))
        return
    context = ssl.create_default_context(cafile=data.get("ca"))
    context.hostname_checks_common_name = False
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.set_alpn_protocols(["h2"])
    with socket.create_connection((data["address"], data["port"]), timeout=data["timeout"]) as raw:
        with context.wrap_socket(raw, server_hostname=data["name"]) as connection:
            if connection.selected_alpn_protocol() != "h2":
                raise ValidationError("h2-unavailable")
    print("true")


def execute(argv, deadline, stage, data=None):
    remaining = min(stage, deadline - time.monotonic())
    if remaining <= 0:
        raise ValidationError("aggregate-deadline-exceeded")
    try:
        code, output = run_command(argv, input_data=json.dumps(data).encode() if data is not None else b"",
                                   environment=os.environ.copy(), timeout=remaining, capture=True, output_limit=65536)
        if code:
            raise ValidationError("stage-refused-or-deadline-exceeded")
        return output
    except ReadinessError:
        raise ValidationError("stage-refused-or-deadline-exceeded") from None


def validate(target, server_names, *, budget=30, stage=5, ca=None, mode="borrowed", public_endpoint=None):
    deadline = time.monotonic() + budget
    selected = names(server_names)
    if mode == "owned-public" and not public_endpoint:
        raise ValidationError("owned-public-endpoint-required")
    host, port = endpoint(public_endpoint if mode == "owned-public" else target)
    response = execute([sys.executable, __file__, "--worker", "dns"], deadline, stage, {"host": host, "port": port})
    addresses = json.loads(response)
    if not addresses or len(addresses) > 8:
        raise ValidationError("dns-empty-or-unbounded")
    if mode == "owned-public" and any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValidationError("owned-public-path-required")
    failures, observations = [], []
    for index, name in enumerate(selected):
        accepted = False
        for address in addresses:
            try:
                execute([sys.executable, __file__, "--worker", "tls"], deadline, stage,
                        {"address": address, "port": port, "name": name, "ca": ca, "timeout": stage})
                authority = "[" + address + "]" if ":" in address else address
                args = ["curl", "--silent", "--show-error", "--noproxy", "*", "--proto", "=https",
                        "--http1.1", "--connect-timeout", str(stage), "--max-time", str(stage), "--output", "/dev/null",
                        "--write-out", "%{http_code}", "--resolve", f"{name}:{port}:{authority}"]
                if ca:
                    args += ["--cacert", ca]
                status = execute(args + [f"https://{name}:{port}/"], deadline, stage).decode().strip()
                if not re.fullmatch(r"[23][0-9]{2}|40[34]", status):
                    raise ValidationError("http-hygiene-refused")
                accepted = True
                break
            except ValidationError:
                if time.monotonic() >= deadline:
                    break
        observations.append({"identity": index + 1, "tls13_h2_verified": accepted, "http_hygiene": accepted})
        if not accepted:
            failures.append("identity-or-path-refused")
    return {"schema": 1, "mode": mode, "verdict": "failed" if failures else "passed",
            "target_digest": hashlib.sha256((host + ":" + str(port)).encode()).hexdigest(),
            "observations": observations, "reason_codes": sorted(set(failures)),
            "browser_clienthello": "unverified", "filtered_survival": "unverified"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("dns", "tls"))
    parser.add_argument("--mode", choices=("borrowed", "owned-public"), default="borrowed")
    parser.add_argument("--budget", type=float, default=30)
    parser.add_argument("--stage-timeout", type=float, default=5)
    args = parser.parse_args()
    if args.worker:
        try:
            worker(args.worker)
            return 0
        except (ValueError, OSError, ssl.SSLError):
            return 1
    started = time.monotonic()
    try:
        if not 0 < args.stage_timeout <= args.budget <= 120:
            raise ValidationError("invalid-deadline-budget")
        target, selected = os.environ.get("TARGET"), os.environ.get("SERVER_NAMES")
        if target is None or selected is None:
            import client_payload
            client_payload.DEADLINE = time.monotonic() + args.budget
            raw = os.environ.get("VPN_SECRETS_FILE") or os.environ.get("SOPS_FILE") or str(
                Path.home() / ".config/vpn-provision" / (os.environ.get("ENV", "prod") + ".secrets.sops.yaml"))
            document = client_payload.read_document(raw, plaintext=bool(os.environ.get("VPN_SECRETS_FILE")))
            target = target if target is not None else document["xray"]["target"]
            selected = selected if selected is not None else " ".join(document["xray"]["server_names"])
        result = validate(target, selected, budget=args.budget - (time.monotonic() - started), stage=args.stage_timeout,
            ca=os.environ.get("REALITY_TARGET_CA_FILE"), mode=args.mode,
            public_endpoint=os.environ.get("REALITY_TARGET_PUBLIC_ENDPOINT"))
    except (ValueError, KeyError, OSError, TypeError):
        result = {"schema": 1, "verdict": "failed", "reason_codes": ["input-or-prerequisite-refused"],
                  "browser_clienthello": "unverified", "filtered_survival": "unverified"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verdict"] == "passed" else 1


if __name__ == "__main__":
    with cancellation():
        raise SystemExit(main())
