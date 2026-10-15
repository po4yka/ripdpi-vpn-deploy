#!/usr/bin/env python3
"""Shared transport input relationships; diagnostics contain no input values.

Pure callers supply resolved role/profile context. The CLI consumes one bounded
JSON request on stdin, never secret arguments, and publishes diagnostics only.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

INTERFACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,14}\Z")
PLACEHOLDER = re.compile(r"REPLACE_WITH_[A-Z0-9_]+\Z")
AWG_PARAMETERS = {"jc": 4, "jmin": 40, "jmax": 70, "s1": 50, "s2": 100}
MAX_INPUT_BYTES = 4 * 1024 * 1024
EGRESS_CREDENTIALS = (
    "direct_xray_password", "direct_hysteria_password", "warp_xray_password",
    "direct_gateway_password", "warp_gateway_password",
)
XHTTP_PATH = re.compile(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\Z")
DNS_NAME = re.compile(
    r"(?=^.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
PUBLIC_ORIGIN_TEMPLATE = "https://{{ nginx_xhttp.server_name }}{{ ':' ~ nginx_xhttp_public_port if nginx_xhttp_public_port | int != 443 else '' }}"


def xhttp_path_valid(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 256 and XHTTP_PATH.fullmatch(value) is not None


def served_origin(host: object, port: object) -> str:
    if (not isinstance(host, str) or DNS_NAME.fullmatch(host) is None
            or type(port) is not int or not 1 <= port <= 65535):
        raise ValueError("invalid-primary-origin")
    return "https://" + host + ("" if port == 443 else ":" + str(port))


def key_valid(value: object, *, allow_placeholders: bool = False) -> bool:
    if isinstance(value, str) and allow_placeholders and PLACEHOLDER.fullmatch(value):
        return True
    try:
        raw = base64.b64decode(value, validate=True) if isinstance(value, str) else b""
        return len(raw) == 32 and any(raw) and base64.b64encode(raw).decode() == value
    except (ValueError, TypeError, binascii.Error):
        return False


def origin_valid(value: object) -> bool:
    if not isinstance(value, str) or any(ord(char) < 33 for char in value):
        return False
    try:
        url = urlsplit(value)
        host = url.hostname
        if not host:
            return False
        try:
            address = ipaddress.ip_address(host)
            authority = "[" + str(address) + "]" if address.version == 6 else str(address)
        except ValueError:
            if DNS_NAME.fullmatch(host) is None:
                return False
            authority = host
        port = url.port
        return (url.scheme == "https" and url.username is None and url.password is None
                and not url.path and not url.query and not url.fragment
                and (port is None or 1 <= port <= 65535)
                and value == "https://" + authority + ("" if port in (None, 443) else ":" + str(port)))
    except ValueError:
        return False


def xhttp_errors(doc: dict, context: dict) -> list[tuple[str, str]]:
    raw = doc.get("xray", {})
    errors = []
    if not isinstance(raw, dict) or not xhttp_path_valid(raw.get("xhttp_path", "/app-sync")):
        errors.append(("xray.xhttp_path", "must be a bounded nonroot path of slash-separated alphanumeric underscore or dash segments"))
    origin = context.get("public_site_canonical_url")
    if origin is not None:
        frontend = doc.get("nginx_xhttp", {})
        try:
            expected = served_origin(frontend.get("server_name"), context.get("nginx_xhttp_public_port", 8443))
        except (AttributeError, ValueError):
            expected = None
        if expected is None or not origin_valid(origin) or origin != expected:
            errors.append(("public_site_canonical_url", "must match the served primary HTTPS host and port"))
    return errors


def hysteria_errors(raw: object, canonical_origin: object = None) -> list[tuple[str, str]]:
    if not isinstance(raw, dict):
        return [("hysteria", "must be a mapping")]
    errors = []
    if raw.get("masquerade_type", "proxy") != "proxy":
        errors.append(("hysteria.masquerade_type", "only owned HTTPS proxy is supported"))
    if not origin_valid(raw.get("masquerade_url")):
        errors.append(("hysteria.masquerade_url", "must be an HTTPS origin"))
    if canonical_origin is not None and (not origin_valid(canonical_origin)
                                        or raw.get("masquerade_url") != canonical_origin):
        errors.append(("hysteria.masquerade_url", "must match the owned canonical origin"))
    if "clients" in raw:
        clients = raw["clients"]
        if not isinstance(clients, list) or any(not isinstance(item, dict) for item in clients):
            errors.append(("hysteria.clients", "must be a client collection"))
        else:
            names = set()
            for index, item in enumerate(clients):
                name, password = item.get("name"), item.get("password")
                if not isinstance(name, str) or not name or not isinstance(password, str) or not password:
                    errors.append((f"hysteria.clients.{index}", "invalid userpass client"))
                elif name in names:
                    errors.append(("hysteria.clients", "duplicate name"))
                else:
                    names.add(name)
    return errors


def cohort_errors(raw: object) -> list[tuple[str, str]]:
    if not isinstance(raw, dict):
        return [("xray", "must be a mapping")]
    errors = []
    clients, cohorts = raw.get("clients", []), raw.get("cohorts", [])
    if not isinstance(clients, list) or any(not isinstance(item, dict) for item in clients):
        return [("xray.clients", "must be a client collection")]
    names = [item.get("name") for item in clients]
    string_names = [name for name in names if isinstance(name, str)]
    known_names = set(string_names)
    if any(not isinstance(name, str) or not name for name in names):
        errors.append(("xray.clients", "invalid client name"))
    if len(string_names) != len(known_names):
        errors.append(("xray.clients", "duplicate name"))
    if not isinstance(cohorts, list):
        return errors + [("xray.cohorts", "must be a cohort collection")]
    cohort_names = set()
    for index, item in enumerate(cohorts):
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name:
            errors.append((f"xray.cohorts.{index}.name", "invalid cohort name"))
        elif name in cohort_names:
            errors.append(("xray.cohorts", "duplicate name"))
        else:
            cohort_names.add(name)
        path = f"xray.cohorts.{index}.clients"
        refs = item.get("clients") if isinstance(item, dict) else None
        if not isinstance(refs, list) or not refs:
            errors.append((path, "explicit nonempty client references are required"))
            continue
        if any(not isinstance(ref, str) or not ref for ref in refs):
            errors.append((path, "invalid client reference"))
            continue
        if len(set(refs)) != len(refs):
            errors.append((path, "duplicate client reference"))
        if any(ref not in known_names for ref in refs):
            errors.append((path, "unknown xray client reference"))
    return errors


def parameter_errors(raw: dict, path: str, *, allow_placeholders: bool = False) -> list[tuple[str, str]]:
    errors = []
    effective = {**AWG_PARAMETERS, **raw}
    for name in (*AWG_PARAMETERS, "h1", "h2", "h3", "h4"):
        value = effective.get(name)
        if name.startswith("h") and allow_placeholders and isinstance(value, str) and PLACEHOLDER.fullmatch(value):
            continue
        maximum = 128 if name == "jc" else (2**32 - 1 if name.startswith("h") else 1280)
        if type(value) is not int or not 0 <= value <= maximum:
            errors.append((f"{path}.{name}", "invalid bounded integer"))
    if all(type(effective.get(name)) is int for name in ("jmin", "jmax")) and effective["jmin"] > effective["jmax"]:
        errors.append((path, "junk bounds must be ordered"))
    headers = [effective.get(f"h{i}") for i in range(1, 5)]
    if all(type(value) is int for value in headers) and len(set(headers)) != 4:
        errors.append((path, "headers must be pairwise distinct"))
    return errors


def awg_dns_valid(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 4:
        return False
    try:
        return (len(set(value)) == len(value)
                and all(isinstance(server, str) and ipaddress.IPv4Address(server).is_global
                        and str(ipaddress.IPv4Address(server)) == server for server in value))
    except (ValueError, TypeError):
        return False


def effective_awg_instances(raw: object, defaults: object = None, cohort: object = None) -> list[dict]:
    """Resolve the sole instance authority without repairing old peer layouts."""
    if not isinstance(raw, dict) or set(raw) != {"instances"}:
        raise ValueError("invalid-awg-contract")
    instances = raw["instances"]
    if not isinstance(instances, list) or not instances or any(not isinstance(item, dict) for item in instances):
        raise ValueError("invalid-awg-contract")
    fields = {"name", "listen_port", "address_v4", "address_v6", "server_private_key", "peers",
              "s3", "s4", *AWG_PARAMETERS, "h1", "h2", "h3", "h4"}
    if any(set(item) - fields for item in instances):
        raise ValueError("invalid-awg-contract")
    defaults = defaults if isinstance(defaults, dict) else {}
    cohort = cohort if isinstance(cohort, dict) else {}
    if set(cohort) - fields or any(f"i{index}" in defaults for index in range(1, 6)):
        raise ValueError("unsupported-awg-policy")
    return [{**AWG_PARAMETERS, "dns_servers": ["1.1.1.1", "1.0.0.1"], **{key: value for key, value in cohort.items() if key in fields - {"name"}},
             **{key: value for key, value in defaults.items() if key in (
                 "listen_port", "address_v4", "address_v6", "dns_servers")},
             **item} for item in instances]


def awg_errors(raw: object, defaults: object = None, cohort: object = None, *,
               allow_placeholders: bool = False) -> list[tuple[str, str]]:
    if not isinstance(raw, dict):
        return [("amneziawg_secrets", "must be a mapping")]
    defaults = defaults if isinstance(defaults, dict) else {}
    cohort = cohort if isinstance(cohort, dict) else {}
    try:
        instances = effective_awg_instances(raw, defaults, cohort)
    except ValueError:
        return [("amneziawg_secrets.instances", "must be the sole nonempty instance authority")]
    errors = []
    # Preserve the existing forward guard across every declared source.
    for source in [raw, defaults, cohort, *instances]:
        for name in ("s3", "s4"):
            if type(source.get(name, 0)) is not int or source.get(name, 0) != 0:
                errors.append(("amneziawg_secrets", "S3/S4 must remain zero"))
    selected = [(f"amneziawg_secrets.instances.{index}", item) for index, item in enumerate(instances)]
    names, ports, claims = set(), set(), []
    key_owners: dict[str, str] = {}
    device_names = set()
    for path, item in selected:
        if not awg_dns_valid(item["dns_servers"]):
            errors.append(("amneziawg.dns_servers", "requires one to four distinct global IPv4 DNS addresses"))
        name = item.get("name")
        if not isinstance(name, str) or not INTERFACE.fullmatch(name):
            errors.append((f"{path}.name", "invalid interface name"))
        elif name in names:
            errors.append(("amneziawg_secrets.instances", "duplicate name"))
        else:
            names.add(name)
        port = item.get("listen_port", defaults.get("listen_port"))
        if port is not None:
            if type(port) is not int or not 1 <= port <= 65535:
                errors.append((f"{path}.listen_port", "invalid port"))
            elif port in ports:
                errors.append(("amneziawg_secrets.instances", "duplicate listen_port"))
            else:
                ports.add(port)
        for field, version in (("address_v4", 4), ("address_v6", 6)):
            if field in item:
                try:
                    if not isinstance(item[field], str):
                        raise ValueError
                    address = ipaddress.ip_interface(item[field])
                    if address.version != version:
                        raise ValueError
                except (ValueError, TypeError):
                    errors.append((f"{path}.{field}", "invalid interface address family or CIDR"))
        errors.extend(parameter_errors(item, path, allow_placeholders=allow_placeholders))
        server_key = item.get("server_private_key")
        if not key_valid(server_key, allow_placeholders=allow_placeholders):
            errors.append((f"{path}.server_private_key", "invalid canonical 32-byte key"))
        peers = item.get("peers")
        if not isinstance(peers, list) or any(not isinstance(peer, dict) for peer in peers):
            errors.append((f"{path}.peers", "must be a peer collection"))
            continue
        local_names, local_keys, local_psks = set(), set(), set()
        for index, peer in enumerate(peers):
            peer_path = f"{path}.peers.{index}"
            peer_name = peer.get("name")
            if not isinstance(peer_name, str) or not peer_name:
                errors.append((f"{peer_path}.name", "invalid device name"))
            elif peer_name in local_names:
                errors.append((f"{path}.peers", "duplicate name"))
            else:
                local_names.add(peer_name)
            if peer.get("address_kind", "device") == "device" and isinstance(peer_name, str):
                if peer_name in device_names:
                    errors.append((f"{path}.peers", "duplicate device name across instances"))
                device_names.add(peer_name)
            for field, seen in (("public_key", local_keys), ("preshared_key", local_psks)):
                value = peer.get(field)
                if not key_valid(value, allow_placeholders=allow_placeholders):
                    errors.append((f"{peer_path}.{field}", "invalid canonical 32-byte key"))
                    continue
                if allow_placeholders and PLACEHOLDER.fullmatch(value):
                    continue
                if value in seen:
                    errors.append((f"{path}.peers", f"duplicate {field}"))
                seen.add(value)
                previous = key_owners.get(value)
                if previous is not None and previous != peer_name:
                    errors.append((f"{path}.peers", "key material reused between devices"))
                if isinstance(peer_name, str):
                    key_owners[value] = peer_name
                if value == server_key:
                    errors.append((peer_path, "server and peer key material must differ"))
            if peer.get("public_key") == peer.get("preshared_key"):
                errors.append((peer_path, "peer public and preshared keys must differ"))
            kind = peer.get("address_kind", "device")
            if kind not in ("device", "routed"):
                errors.append((f"{peer_path}.address_kind", "unsupported address kind"))
            try:
                if not isinstance(peer.get("allowed_ips"), str):
                    raise ValueError
                network = ipaddress.ip_network(peer["allowed_ips"], strict=True)
            except (ValueError, TypeError):
                errors.append((f"{peer_path}.allowed_ips", "must be a valid IPv4 or IPv6 CIDR"))
                continue
            if kind == "device":
                try:
                    server = ipaddress.IPv4Interface(item["address_v4"])
                    if (network.version != 4 or network.prefixlen != 32
                            or network.network_address not in server.network
                            or network.network_address in (server.ip, server.network.network_address, server.network.broadcast_address)):
                        raise ValueError
                except (ValueError, TypeError, KeyError):
                    errors.append((f"{peer_path}.allowed_ips", "device requires an unreserved IPv4 host inside its instance pool; other prefixes require explicit routed ownership"))
            claims.append((network.version, int(network.network_address),
                           int(network.broadcast_address), f"{peer_path}.allowed_ips"))
    family, previous_end = 0, -1
    for version, start, end, claim_path in sorted(claims):
        if version != family:
            family, previous_end = version, -1
        if start <= previous_end:
            errors.append((claim_path, "conflicting peer address claim"))
        previous_end = max(previous_end, end)
    return errors


def egress_errors(raw: object, vpn: object = None, *, required: bool = False,
                  allow_placeholders: bool = False) -> list[tuple[str, str]]:
    """Validate private service authority without exposing credential values."""
    vpn = vpn if isinstance(vpn, dict) else {}
    xray_enabled = bool(vpn.get("enable_xray_reality", True)
                        or vpn.get("enable_nginx_xhttp", False))
    hysteria_enabled = bool(vpn.get("enable_hysteria", False))
    active = required and (xray_enabled or hysteria_enabled)
    if active and not vpn.get("enable_transport_egress", True):
        return [("vpn.enable_transport_egress", "required for enabled proxy transports")]
    if raw is None and not active:
        return []
    if not isinstance(raw, dict):
        return [("transport_egress_secrets", "must be a credential mapping")]
    errors = []
    if set(raw) - set(EGRESS_CREDENTIALS):
        errors.append(("transport_egress_secrets", "unknown credential field"))
    needed = set()
    if active:
        needed.add("direct_gateway_password")
        if xray_enabled:
            needed.add("direct_xray_password")
        if hysteria_enabled:
            needed.add("direct_hysteria_password")
        if xray_enabled and vpn.get("enable_warp_outbound", False):
            needed.update(("warp_xray_password", "warp_gateway_password"))
    values = set()
    for name in EGRESS_CREDENTIALS:
        if name not in raw:
            if name in needed:
                errors.append(("transport_egress_secrets." + name, "required for enabled path"))
            continue
        value = raw[name]
        path = "transport_egress_secrets." + name
        if (allow_placeholders and isinstance(value, str)
                and PLACEHOLDER.fullmatch(value)):
            continue
        if (not isinstance(value, str) or not 32 <= len(value) <= 128
                or any(ord(char) < 32 or ord(char) > 126 for char in value)
                or PLACEHOLDER.fullmatch(value)):
            errors.append((path, "must be a non-placeholder printable ASCII credential of 32 to 128 bytes"))
        elif value in values:
            errors.append((path, "service credentials must be distinct"))
        else:
            values.add(value)
    return errors


def transport_errors(doc: object, context: object = None, *, sections: list[str] | None = None,
                     allow_placeholders: bool = False) -> list[tuple[str, str]]:
    if not isinstance(doc, dict):
        return [("transport", "must be a mapping")]
    context = context if isinstance(context, dict) else {}
    # Resolve only the repository's named profile expression, never arbitrary
    # Jinja or an operator-supplied origin. Ansible supplies an already resolved value.
    if context.get("public_site_canonical_url") == PUBLIC_ORIGIN_TEMPLATE:
        try:
            context = {**context, "public_site_canonical_url": served_origin(
                doc.get("nginx_xhttp", {}).get("server_name"), context.get("nginx_xhttp_public_port", 8443))}
        except (AttributeError, ValueError):
            return [("public_site_canonical_url", "invalid served primary origin")]
    require_egress = bool(context.get("require_transport_egress",
                                    sections is not None and "egress" in sections))
    if sections is None:
        vpn = context.get("vpn")
        if isinstance(vpn, dict):
            sections = []
            if vpn.get("enable_xray_reality", True) or vpn.get("enable_nginx_xhttp", False):
                sections.append("xray")
            if vpn.get("enable_amneziawg", False):
                sections.append("awg")
            if vpn.get("enable_hysteria", False):
                sections.append("hysteria")
        else:
            sections = [name for name, field in (("xray", "xray"), ("awg", "amneziawg_secrets"), ("hysteria", "hysteria")) if field in doc]
        if "transport_egress_secrets" in doc or context.get("require_transport_egress", False):
            sections.append("egress")
    errors = []
    if "xray" in sections:
        errors.extend(cohort_errors(doc.get("xray")))
    vpn = context.get("vpn")
    if ("xhttp" in sections
            or ("xray" in sections and (not isinstance(vpn, dict) or vpn.get("enable_nginx_xhttp", False)))
            or ("hysteria" in sections and isinstance(vpn, dict) and vpn.get("enable_nginx_xhttp", False))):
        errors.extend(xhttp_errors(doc, context))
    if "awg" in sections:
        errors.extend(awg_errors(doc.get("amneziawg_secrets"), context.get("amneziawg"), context.get("amneziawg_cohort"), allow_placeholders=allow_placeholders))

    if "hysteria" in sections:
        errors.extend(hysteria_errors(doc.get("hysteria"), context.get("public_site_canonical_url")))
    if "egress" in sections:
        errors.extend(egress_errors(doc.get("transport_egress_secrets"), context.get("vpn"),
                                    required=require_egress,
                                    allow_placeholders=allow_placeholders))
    return errors


def selected_context(context: object, sections: list[str] | None) -> dict:
    """Load only the selected, repository-owned technical AWG cohort for CLI IO."""
    context = dict(context) if isinstance(context, dict) else {}
    vpn = context.get("vpn", {})
    if not isinstance(vpn, dict):
        raise ValueError
    selected = "awg" in sections if sections is not None else vpn.get("enable_amneziawg", False)
    name = os.environ.get("AWG_COHORT") or vpn.get("awg_cohort", "")
    if not selected or not name:
        return context
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", name):
        raise ValueError
    import yaml
    directory = Path(__file__).resolve().parent.parent / "ansible/roles/amneziawg/vars/cohorts"
    path = directory / (name + ".yml")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError
    try:
        cohort = yaml.safe_load(path.read_text())
    except (OSError, UnicodeError, yaml.YAMLError):
        raise ValueError from None
    if not isinstance(cohort, dict) or not isinstance(cohort.get("amneziawg_cohort"), dict):
        raise ValueError
    override = context.get("amneziawg_cohort", {})
    if not isinstance(override, dict):
        raise ValueError
    context["amneziawg_cohort"] = {**cohort["amneziawg_cohort"], **override}
    return context


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", action="append", choices=("xray", "xhttp", "awg", "hysteria", "egress"))
    parser.add_argument("--allow-placeholders", action="store_true")
    args = parser.parse_args()
    try:
        payload = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(payload) > MAX_INPUT_BYTES:
            raise ValueError
        request = json.loads(payload)
        if not isinstance(request, dict):
            raise ValueError
        doc = request.get("secrets", request)
        context = selected_context(request.get("context"), args.section)
        errors = transport_errors(doc, context if "context" in request or context else None, sections=args.section, allow_placeholders=args.allow_placeholders)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        print("transport: invalid bounded JSON input", file=sys.stderr)
        return 1
    for path, message in errors:
        print(f"{path}: {message}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
