"""Bounded advisory release check; corrupt or unwritable cache is nonfatal."""

import asyncio
import json
import os
import signal
import subprocess
from pathlib import Path
import re
import sys
import socket
import threading
import time
import tomllib
import tomli_w
from vpnd.text import trim_whitespace

GITHUB_API_URL = "https://api.github.com/repos/po4yka/ripdpi-vpn-deploy/releases/latest"
CACHE_FILE = "last-update-check.toml"
TTL_SECS = 86400
REQUEST_TIMEOUT = 10
CONNECT_TIMEOUT = 5


def load_cache(path, now):
    try:
        cache = tomllib.loads(Path(path).read_text())
        checked, tag = cache["checked_at"], cache["latest_tag"]
        if (
            type(checked) is int
            and checked >= 0
            and isinstance(tag, str)
            and 0 <= now - checked < TTL_SECS
        ):
            return cache
    except (OSError, ValueError, KeyError, TypeError):
        # Missing or malformed advisory cache entries trigger a fresh check.
        return None
    return None


def check_update(path, now, fetch):
    cached = load_cache(path, now)
    if cached:
        return cached["latest_tag"]
    try:
        tag = fetch()
    except Exception:
        return None
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomli_w.dumps({"checked_at": now, "latest_tag": tag}))
    except OSError:
        # A read-only cache directory must not discard the fetched release tag.
        return tag
    return tag


def _fetch_network(url, request_timeout):
    from vpnd import version

    __version__ = version()
    # Socket operations share an absolute deadline; a trickling response cannot
    # extend the advisory operation beyond request_timeout.
    import http.client
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("unsupported release URL")
    deadline = time.monotonic() + request_timeout
    cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = cls(parsed.hostname, parsed.port, timeout=min(CONNECT_TIMEOUT, request_timeout))
    watchdog = None
    try:
        connection.request(
            "GET",
            parsed.path + (("?" + parsed.query) if parsed.query else ""),
            headers={"User-Agent": f"vpnd/{__version__}"},
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("release request timed out")
        socket_handle = connection.sock
        if socket_handle:
            socket_handle.settimeout(remaining)

            # A socket timeout alone resets after each successful read. Bound
            # even a header/body peer that trickles one byte indefinitely.
            def expire():
                try:
                    socket_handle.shutdown(socket.SHUT_RDWR)
                except OSError:
                    # A completed request may close the socket before the timer fires.
                    pass

            watchdog = threading.Timer(remaining, expire)
            watchdog.daemon = True
            watchdog.start()
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("GitHub releases API request failed")
        raw = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("release request timed out")
            if connection.sock:
                connection.sock.settimeout(remaining)
            chunk = response.read1(65536)
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 1024 * 1024:
                raise ValueError("release response too large")
        tag = json.loads(raw)["tag_name"]
        if not isinstance(tag, str):
            raise ValueError("invalid release tag")
        return tag
    finally:
        if watchdog:
            watchdog.cancel()
            watchdog.join()
        connection.close()


_FETCH_WORKER = r"""
import importlib.util, json, os, signal, sys, threading
from pathlib import Path
parent_read = int(sys.argv[4])
def parent_liveness():
    try:
        while os.read(parent_read, 1):
            pass
    finally:
        os.killpg(os.getpgrp(), signal.SIGKILL)
threading.Thread(target=parent_liveness, daemon=True).start()
try:
    # The launcher adds the package root only to its own interpreter. Resolve
    # the same root from this known module in both source and installed layouts.
    sys.path.insert(0, str(Path(sys.argv[1]).resolve().parents[2]))
    spec = importlib.util.spec_from_file_location('vpnd_update_network', sys.argv[1])
    network = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(network)
    tag = network._fetch_network(sys.argv[2], float(sys.argv[3]))
    print(json.dumps({'tag_name': tag}))
except Exception:
    print(json.dumps({'error': 'release request failed'}))
    sys.exit(1)
"""


def fetch_latest_tag_with_timeout(url, request_timeout):
    # One owned process bounds resolver/connect/TLS/header/body work together.
    # Its liveness pipe also terminates it if interactive dispatch is killed.
    deadline = time.monotonic() + request_timeout
    parent_read: int | None
    parent_read, parent_write = os.pipe()
    child = None
    try:
        child = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-c",
                _FETCH_WORKER,
                str(Path(__file__).resolve()),
                url,
                str(request_timeout),
                str(parent_read),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(parent_read,),
            start_new_session=True,
        )
        os.close(parent_read)
        parent_read = None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(child.args, request_timeout)
        stdout, _stderr = child.communicate(timeout=remaining)
        if child.returncode:
            raise ValueError("GitHub releases API request failed")
        tag = json.loads(stdout)["tag_name"]
        if not isinstance(tag, str):
            raise ValueError("invalid release tag")
        return tag
    except BaseException:
        if child is not None and child.returncode is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                # The worker may exit between the state check and group termination.
                pass
            child.communicate()
        raise
    finally:
        if parent_read is not None:
            os.close(parent_read)
        os.close(parent_write)


def fetch_latest_tag(url):
    return fetch_latest_tag_with_timeout(url, REQUEST_TIMEOUT)


def normalize_tag(tag):
    bare = trim_whitespace(tag)
    if bare.startswith("vpnd-"):
        bare = bare[5:]
    return bare[1:] if bare.startswith("v") else None


def parse_version(value):
    if not value or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        return None
    parts = tuple(map(int, value.split(".")))
    return parts if all(part <= 2**64 - 1 for part in parts) else None


def is_newer(tag):
    from vpnd import version

    __version__ = version()
    current, latest = parse_version(__version__), parse_version(normalize_tag(tag))
    return current is not None and latest is not None and latest > current


def print_notice(tag):
    from vpnd import version

    __version__ = version()
    if is_newer(tag):
        print(
            f"notice: A newer vpnd release is available: {tag.removeprefix('vpnd-')} (you have v{__version__}). See https://github.com/po4yka/ripdpi-vpn-deploy/releases",
            file=sys.stderr,
        )


async def run(ctx, args):
    if ctx.explain or args.explain:
        print(
            f"# vpnd update would query:\n  GET {GITHUB_API_URL}\n# Cache: {ctx.config_dir / CACHE_FILE}"
        )
        return 0
    tag = await asyncio.to_thread(
        check_update,
        ctx.config_dir / CACHE_FILE,
        int(time.time()),
        lambda: fetch_latest_tag(GITHUB_API_URL),
    )
    if tag:
        print_notice(tag)
    return 0
