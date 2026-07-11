#!/usr/bin/env python3
"""Classify one destination against the unchanged V2Ray geoip.dat contract."""

from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
from typing import TypeAlias


DATASET_UNAVAILABLE_EXIT = 3
IPNetwork: TypeAlias = ipaddress.IPv4Network | ipaddress.IPv6Network


class DatasetUnavailable(ValueError):
    """The classifier cannot make a policy-safe routing decision."""


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift <= 63:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise DatasetUnavailable("malformed protobuf varint")


def _fields(data: bytes):
    offset = 0
    while offset < len(data):
        tag, offset = _read_varint(data, offset)
        number, wire_type = tag >> 3, tag & 7
        if number == 0:
            raise DatasetUnavailable("malformed protobuf field")
        if wire_type == 0:
            value, offset = _read_varint(data, offset)
        elif wire_type == 1:
            if offset + 8 > len(data):
                raise DatasetUnavailable("truncated fixed64 field")
            value, offset = data[offset : offset + 8], offset + 8
        elif wire_type == 2:
            length, offset = _read_varint(data, offset)
            if offset + length > len(data):
                raise DatasetUnavailable("truncated length-delimited field")
            value, offset = data[offset : offset + length], offset + length
        elif wire_type == 5:
            if offset + 4 > len(data):
                raise DatasetUnavailable("truncated fixed32 field")
            value, offset = data[offset : offset + 4], offset + 4
        else:
            raise DatasetUnavailable(f"unsupported protobuf wire type {wire_type}")
        yield number, wire_type, value


def _parse_cidr(payload: bytes) -> IPNetwork:
    packed = None
    prefix = None
    for number, wire_type, value in _fields(payload):
        if number == 1 and wire_type == 2:
            packed = value
        elif number == 2 and wire_type == 0:
            prefix = value
    if packed is None or prefix is None or len(packed) not in (4, 16):
        raise DatasetUnavailable("invalid CIDR entry in geoip.dat")
    address = ipaddress.ip_address(packed)
    if prefix > address.max_prefixlen:
        raise DatasetUnavailable("invalid CIDR prefix in geoip.dat")
    return ipaddress.ip_network((address, prefix), strict=False)


def _parse_geoip(payload: bytes) -> tuple[str, bool, list[IPNetwork]]:
    country = ""
    inverse = False
    networks: list[IPNetwork] = []
    for number, wire_type, value in _fields(payload):
        if number == 1 and wire_type == 2:
            country = value.decode("utf-8", errors="strict").upper()
        elif number == 2 and wire_type == 2:
            networks.append(_parse_cidr(value))
        elif number == 3 and wire_type == 0:
            inverse = bool(value)
    return country, inverse, networks


def load_ru_networks(path: Path) -> list[IPNetwork]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DatasetUnavailable(f"dataset missing or unreadable: {path}") from exc
    if not data:
        raise DatasetUnavailable("dataset is empty")

    found = False
    networks: list[IPNetwork] = []
    try:
        for number, wire_type, value in _fields(data):
            if number != 1 or wire_type != 2:
                continue
            country, inverse, entries = _parse_geoip(value)
            if country == "RU":
                found = True
                if inverse:
                    raise DatasetUnavailable("inverse RU dataset is unsupported")
                networks.extend(entries)
    except (UnicodeDecodeError, ValueError) as exc:
        if isinstance(exc, DatasetUnavailable):
            raise
        raise DatasetUnavailable(f"dataset malformed: {exc}") from exc
    if not found or not networks:
        raise DatasetUnavailable("dataset contains no usable RU classification entries")
    return networks


def classify(path: Path, destination: str) -> dict[str, str]:
    try:
        address = ipaddress.ip_address(destination)
    except ValueError as exc:
        raise DatasetUnavailable("destination is unknown or invalid") from exc
    networks = load_ru_networks(path)
    state = "ru" if any(address.version == network.version and address in network for network in networks) else "foreign"
    return {"state": state}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--destination")
    mode.add_argument("--check-dataset", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.check_dataset:
            load_ru_networks(args.dataset)
            result = {"state": "ready"}
        else:
            result = classify(args.dataset, args.destination)
    except DatasetUnavailable as exc:
        print(json.dumps({"reason": str(exc), "state": "dataset-unavailable"}, sort_keys=True))
        return DATASET_UNAVAILABLE_EXIT
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
