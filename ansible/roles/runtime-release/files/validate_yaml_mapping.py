#!/usr/bin/env python3
"""Validate a bounded YAML mapping without disclosing its contents or path."""

from __future__ import annotations

import argparse
import base64
import ipaddress
import importlib.util
from pathlib import Path
import os
import re
import stat
import sys

import yaml

MAX_CONFIG_BYTES = 1024 * 1024


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader variant that refuses ambiguous duplicate mapping keys."""


def _construct_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict:
    loader.flatten_mapping(node)
    result: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as error:
            raise ValueError("mapping key must be scalar") from error
        if duplicate:
            raise ValueError("duplicate mapping key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _mapping(document: dict, key: str) -> dict:
    value = document.get(key)
    if not isinstance(value, dict) or not value:
        raise ValueError("required mapping is empty or invalid")
    return value


def _string(document: dict, key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError("required string is empty or invalid")
    return value


def _port(document: dict, key: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError("required port is invalid")
    return value


def _positive_int(document: dict, key: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("required positive integer is invalid")
    return value


def _validate_hysteria(document: dict) -> None:
    listen = _string(document, "listen")
    match = re.fullmatch(
        r":([1-9][0-9]{0,4})(?:,([1-9][0-9]{0,4})-([1-9][0-9]{0,4}))?", listen
    )
    if match is None:
        raise ValueError("Hysteria listen selector is invalid")
    ports = [int(value) for value in match.groups() if value is not None]
    if any(port > 65535 for port in ports) or (len(ports) == 3 and ports[1] > ports[2]):
        raise ValueError("Hysteria listen port is invalid")
    if ('tls' in document) == ('acme' in document):
        raise ValueError('Hysteria requires exactly one TLS authority')
    if 'tls' in document:
        tls = _mapping(document, "tls")
        _string(tls, "cert")
        _string(tls, "key")
    if 'ech' in document:
        ech = _mapping(document, 'ech')
        if ech != {'keyPath': '/run/credentials/hysteria-server.service/hysteria-ech'}:
            raise ValueError('Hysteria ECH credential path is invalid')
    if 'congestion' in document:
        congestion = _mapping(document, 'congestion')
        if (set(congestion) != {'type', 'bbrProfile'} or congestion['type'] != 'bbr'
                or congestion['bbrProfile'] not in {'conservative', 'standard'}
                or document.get('ignoreClientBandwidth') is not True):
            raise ValueError('Hysteria resource profile is invalid')
    auth = _mapping(document, "auth")
    if auth.get("type") != "userpass":
        raise ValueError("Hysteria auth type is invalid")
    _mapping(auth, "userpass")
    bandwidth = _mapping(document, "bandwidth")
    _string(bandwidth, "up")
    _string(bandwidth, "down")
    masquerade = _mapping(document, "masquerade")
    # The same source is installed beside this helper; repository execution
    # selects its canonical scripts location instead of maintaining a copy.
    shared = Path(__file__).with_name("transport_semantics.py")
    if not shared.is_file():
        shared = Path(__file__).resolve().parents[4] / "scripts" / "transport_semantics.py"
    spec = importlib.util.spec_from_file_location("transport_semantics", shared)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if 'acme' in document:
        module.hysteria_native_acme(document['acme'])
        if 'ech' in document:
            raise ValueError('Hysteria native ACME does not admit ECH')
    proxy = _mapping(masquerade, "proxy")
    if module.hysteria_errors({"masquerade_type": masquerade.get("type"),
                               "masquerade_url": proxy.get("url")}):
        raise ValueError("Hysteria masquerade is invalid")
    outbounds = document.get("outbounds")
    if not isinstance(outbounds, list) or len(outbounds) != 1:
        raise ValueError("Hysteria requires one guarded outbound")
    outbound = outbounds[0]
    if not isinstance(outbound, dict) or set(outbound) != {"name", "type", "socks5"} or outbound.get("name") != "guarded-direct" or outbound.get("type") != "socks5":
        raise ValueError("Hysteria outbound is invalid")
    proxy_out = _mapping(outbound, "socks5")
    if set(proxy_out) != {"addr", "username", "password"} or proxy_out.get("addr") != "127.0.0.1:12081" or proxy_out.get("username") != "normalizer-direct-hysteria":
        raise ValueError("Hysteria gateway authority is invalid")
    password = _string(proxy_out, "password")
    if not re.fullmatch(r"[ -~]{32,128}", password):
        raise ValueError("Hysteria gateway credential is invalid")
    if "acl" in document or "resolver" in document:
        raise ValueError("Hysteria recipient authority override is invalid")
    quic = _mapping(document, "quic")
    for key in (
        "initStreamReceiveWindow",
        "maxStreamReceiveWindow",
        "initConnReceiveWindow",
        "maxConnReceiveWindow",
    ):
        value = _positive_int(quic, key)
        ceiling = 16777216 if 'Stream' in key else 67108864
        if not 1048576 <= value <= ceiling:
            raise ValueError('Hysteria receive window exceeds resource bounds')


def _validate_dns_morph(document: dict, *, allow_echo_only: bool = False) -> None:
    listen = _mapping(document, "listen")
    _string(listen, "address")
    _port(listen, "port")
    forward = _mapping(document, "forward")
    _string(forward, "address")
    _port(forward, "port")
    if forward.get("protocol") != "udp":
        raise ValueError("DNS-Morph forward protocol is invalid")
    morph = _mapping(document, "morph")
    key = _string(morph, "signing_key")
    if len(key) != 44:
        raise ValueError("DNS-Morph requires a base64 Ed25519 seed")
    seed = base64.b64decode(key, validate=True)
    if len(seed) != 32 or base64.b64encode(seed).decode("ascii") != key:
        raise ValueError("DNS-Morph requires a canonical 32-byte Ed25519 seed")
    endpoint = morph.get("upstream_endpoint")
    if not isinstance(endpoint, str):
        raise ValueError("DNS-Morph upstream endpoint is invalid")
    if endpoint or not allow_echo_only:
        match = re.fullmatch(r"(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]+):([1-9][0-9]{0,4})", endpoint)
        if match is None or int(match[2]) > 65535:
            raise ValueError("DNS-Morph requires a data-plane host and port")
        host = match[1]
        if host.startswith("["):
            ipaddress.IPv6Address(host[1:-1])
        else:
            try:
                ipaddress.IPv4Address(host)
            except ValueError:
                if (len(host) > 253 or re.fullmatch(r"[0-9.]+", host)
                        or any(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) is None
                               for label in host.split("."))):
                    raise ValueError("DNS-Morph upstream host is invalid") from None
    _positive_int(_mapping(document, "limits"), "events_per_minute_max")
    log_dir = _string(_mapping(document, "log"), "dir")
    if not log_dir.startswith("/"):
        raise ValueError("DNS-Morph log path must be absolute")


PROFILE_VALIDATORS = {
    "dns-morph": _validate_dns_morph,
    "hysteria": _validate_hysteria,
}


def _read_payload(path: str) -> bytes:
    if path == "-":
        payload = sys.stdin.buffer.read(MAX_CONFIG_BYTES + 1)
        if len(payload) > MAX_CONFIG_BYTES:
            raise ValueError("configuration exceeds its bound")
        return payload
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CONFIG_BYTES:
            raise ValueError("configuration is not a bounded regular file")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if remaining or (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("configuration changed while reading")
    finally:
        os.close(descriptor)
    return payload


def validate(
    path: str,
    profile: str | None,
    *,
    allow_dns_morph_echo_only: bool = False,
) -> None:
    payload = _read_payload(path)
    document = yaml.load(payload, Loader=UniqueKeyLoader)
    if not isinstance(document, dict):
        raise ValueError("configuration root must be a mapping")
    if profile == "dns-morph":
        _validate_dns_morph(document, allow_echo_only=allow_dns_morph_echo_only)
    elif allow_dns_morph_echo_only:
        raise ValueError("echo-only selection requires DNS-Morph")
    elif profile is not None:
        PROFILE_VALIDATORS[profile](document)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(PROFILE_VALIDATORS))
    parser.add_argument("--allow-dns-morph-echo-only", action="store_true")
    parser.add_argument("path")
    arguments = parser.parse_args()
    try:
        validate(
            arguments.path,
            arguments.profile,
            allow_dns_morph_echo_only=arguments.allow_dns_morph_echo_only,
        )
    except (OSError, TypeError, UnicodeError, ValueError, yaml.YAMLError):
        print("configuration validation failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
