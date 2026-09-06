#!/usr/bin/env python3
"""Validate a bounded YAML mapping without disclosing its contents or path."""

from __future__ import annotations

import argparse
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
    tls = _mapping(document, "tls")
    _string(tls, "cert")
    _string(tls, "key")
    auth = _mapping(document, "auth")
    if auth.get("type") != "userpass":
        raise ValueError("Hysteria auth type is invalid")
    _mapping(auth, "userpass")
    bandwidth = _mapping(document, "bandwidth")
    _string(bandwidth, "up")
    _string(bandwidth, "down")
    masquerade = _mapping(document, "masquerade")
    if masquerade.get("type") != "proxy":
        raise ValueError("Hysteria masquerade type is invalid")
    _string(_mapping(masquerade, "proxy"), "url")
    quic = _mapping(document, "quic")
    for key in (
        "initStreamReceiveWindow",
        "maxStreamReceiveWindow",
        "initConnReceiveWindow",
        "maxConnReceiveWindow",
    ):
        _positive_int(quic, key)


def _validate_dns_morph(document: dict) -> None:
    listen = _mapping(document, "listen")
    _string(listen, "address")
    _port(listen, "port")
    forward = _mapping(document, "forward")
    _string(forward, "address")
    _port(forward, "port")
    if forward.get("protocol") != "udp":
        raise ValueError("DNS-Morph forward protocol is invalid")
    morph = _mapping(document, "morph")
    _string(morph, "signing_key")
    if not isinstance(morph.get("upstream_endpoint"), str):
        raise ValueError("DNS-Morph upstream endpoint is invalid")
    _positive_int(_mapping(document, "limits"), "events_per_minute_max")
    log_dir = _string(_mapping(document, "log"), "dir")
    if not log_dir.startswith("/"):
        raise ValueError("DNS-Morph log path must be absolute")


PROFILE_VALIDATORS = {
    "dns-morph": _validate_dns_morph,
    "hysteria": _validate_hysteria,
}


def validate(
    path: str,
    required: list[str],
    required_mappings: list[str],
    required_strings: list[str],
    profile: str | None,
) -> None:
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

    document = yaml.load(payload, Loader=UniqueKeyLoader)
    if not isinstance(document, dict):
        raise ValueError("configuration root must be a mapping")
    all_required = [*required, *required_mappings, *required_strings]
    if any(key not in document for key in all_required):
        raise ValueError("configuration is missing required keys")
    if any(not isinstance(document[key], dict) for key in required_mappings):
        raise ValueError("configuration mapping has an invalid type")
    if any(
        not isinstance(document[key], str) or not document[key]
        for key in required_strings
    ):
        raise ValueError("configuration string has an invalid type")
    if profile is not None:
        PROFILE_VALIDATORS[profile](document)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require", action="append", default=[])
    parser.add_argument("--require-mapping", action="append", default=[])
    parser.add_argument("--require-string", action="append", default=[])
    parser.add_argument("--profile", choices=sorted(PROFILE_VALIDATORS))
    parser.add_argument("path")
    arguments = parser.parse_args()
    try:
        validate(
            arguments.path,
            arguments.require,
            arguments.require_mapping,
            arguments.require_string,
            arguments.profile,
        )
    except (OSError, TypeError, UnicodeError, ValueError, yaml.YAMLError):
        print("configuration validation failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
