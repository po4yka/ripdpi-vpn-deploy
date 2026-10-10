"""Bounded SOCKS5 wire codec. This module performs no network IO."""
from __future__ import annotations

import hmac
import socket
import struct

from transport_destination_policy import canonical_name, normalize_address, PolicyError

FAILURE = b"\x05\x01\x00\x01" + bytes(6)
MAX_HANDSHAKE = 1024


class WireError(ValueError):
    """Fixed categorical diagnostics only."""


class NeedMore(Exception):
    """An otherwise bounded frame has not arrived completely."""


def _need(data: bytes | bytearray, size: int) -> None:
    if len(data) < size:
        raise NeedMore


def greeting(data) -> tuple[int, bytes]:
    _need(data, 2)
    if data[0] != 5 or not data[1]:
        raise WireError("invalid-greeting")
    _need(data, 2 + data[1])
    if 2 not in data[2:2 + data[1]]:
        raise WireError("authentication-required")
    return 2 + data[1], b"\x05\x02"


def authentication(data, username: str, password: str) -> tuple[int, bytes]:
    _need(data, 2)
    if data[0] != 1 or not data[1]:
        raise WireError("invalid-authentication")
    user_end = 2 + data[1]
    _need(data, user_end + 1)
    length = data[user_end]
    if not length:
        raise WireError("invalid-authentication")
    end = user_end + 1 + length
    _need(data, end)
    if not (hmac.compare_digest(bytes(data[2:user_end]), username.encode("ascii"))
            and hmac.compare_digest(bytes(data[user_end + 1:end]), password.encode("ascii"))):
        raise WireError("authentication-refused")
    return end, b"\x01\x00"


def address(data, offset=0) -> tuple[int, str, int]:
    _need(data, offset + 1)
    atyp = data[offset]
    offset += 1
    if atyp in (1, 4):
        length = 4 if atyp == 1 else 16
        _need(data, offset + length + 2)
        host = socket.inet_ntop(socket.AF_INET if atyp == 1 else socket.AF_INET6, bytes(data[offset:offset + length]))
        host = str(normalize_address(host))
    elif atyp == 3:
        _need(data, offset + 1)
        length = data[offset]
        offset += 1
        if not length:
            raise WireError("invalid-name")
        _need(data, offset + length + 2)
        try:
            value = bytes(data[offset:offset + length]).decode("utf-8")
            try:
                host = str(normalize_address(value))
            except PolicyError:
                host = canonical_name(value)
        except (UnicodeError, PolicyError):
            raise WireError("invalid-name") from None
    else:
        raise WireError("invalid-address-type")
    end = offset + length
    port = struct.unpack("!H", bytes(data[end:end + 2]))[0]
    return end + 2, host, port


def request(data) -> tuple[int, int, str, int]:
    _need(data, 4)
    if data[0] != 5 or data[2] != 0 or data[1] not in (1, 3):
        raise WireError("invalid-request")
    end, host, port = address(data, 3)
    if data[1] == 1 and not port:
        raise WireError("invalid-port")
    return end, data[1], host, port


def encoded_address(host: str, port: int) -> bytes:
    if type(port) is not int or not 0 <= port <= 65535:
        raise WireError("invalid-port")
    normalized = normalize_address(host)
    return bytes([1 if normalized.version == 4 else 4]) + normalized.packed + struct.pack("!H", port)


def reply(host: str, port: int) -> bytes:
    return b"\x05\x00\x00" + encoded_address(host, port)


def upstream_auth(username: str, password: str) -> bytes:
    user, secret = username.encode("ascii"), password.encode("ascii")
    if not 1 <= len(user) <= 255 or not 1 <= len(secret) <= 255:
        raise WireError("invalid-authentication")
    return bytes([1, len(user)]) + user + bytes([len(secret)]) + secret


def upstream_request(command: int, host: str, port: int) -> bytes:
    return bytes([5, command, 0]) + (encoded_address("0.0.0.0", 0) if command == 3 else encoded_address(host, port))


def upstream_reply(data) -> tuple[int, str, int]:
    _need(data, 4)
    if data[0] != 5 or data[1] != 0 or data[2] != 0 or data[3] not in (1, 4):
        raise WireError("upstream-refused")
    return address(data, 3)


def datagram(data: bytes, maximum: int) -> tuple[str, int, bytes]:
    if len(data) > maximum or len(data) < 4 or data[:3] != bytes(3):
        raise WireError("invalid-datagram")
    try:
        end, host, port = address(data, 3)
    except NeedMore:
        raise WireError("truncated-datagram") from None
    if not port:
        raise WireError("invalid-port")
    return host, port, data[end:]


def encoded_datagram(host: str, port: int, payload: bytes, maximum: int) -> bytes:
    frame = bytes(3) + encoded_address(host, port) + payload
    if len(frame) > maximum:
        raise WireError("oversized-datagram")
    return frame
