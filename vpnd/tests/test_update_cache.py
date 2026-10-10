import socket
import threading
import time
import pytest
from artifact_helpers import scaffold, cli, environment
from vpnd import version
from vpnd.commands import update
from vpnd.config import config_home


# Rust test: vpnd/tests/update_cache.rs::fresh_cache_drives_actual_notice_and_suppresses_current_release
def test_fresh_cache_drives_actual_notice_and_suppresses_current_release(tmp_path, monkeypatch):
    scaffold(tmp_path)
    for key, value in environment(tmp_path).items():
        if key in ["HOME", "XDG_CONFIG_HOME"]:
            monkeypatch.setenv(key, value)
    cache = config_home() / "vpn-provision" / update.CACHE_FILE
    cache.parent.mkdir(parents=True)
    for tag, notice in [
        ("vpnd-v" + version(), False),
        ("vpnd-v999.0.0", True),
        ("other-v999.0.0", False),
    ]:
        text = f'checked_at = {int(time.time())}\nlatest_tag = "{tag}"\n'
        cache.write_text(text)
        output = cli(tmp_path, "update")
        assert output.returncode == 0, output.stderr
        assert ("A newer vpnd release is available" in output.stderr) == notice
        if notice:
            assert "v999.0.0" in output.stderr and version() in output.stderr
        assert cache.read_text() == text


# Rust test: vpnd/tests/update_cache.rs::explain_reports_endpoint_without_creating_cache_or_needing_repository
def test_explain_reports_endpoint_without_creating_cache_or_needing_repository(tmp_path):
    for args in [("--explain", "update"), ("update", "--explain")]:
        output = cli(tmp_path, *args)
        assert output.returncode == 0, output.stderr
        assert "GET " + update.GITHUB_API_URL in output.stdout
        assert not (tmp_path / "home").exists()


# Rust test: vpnd/src/commands/update.rs::refresh_writes_real_cache_and_fresh_hits_skip_fetch
def test_refresh_writes_real_cache_and_fresh_hits_skip_fetch(tmp_path):
    path = tmp_path / "nested" / update.CACHE_FILE
    tag = "vpnd-v9.0.0"
    assert update.check_update(path, 100000, lambda: tag) == tag
    assert update.load_cache(path, 100001) == {"checked_at": 100000, "latest_tag": tag}

    def unexpected():
        raise RuntimeError("unexpected fetch")

    assert update.check_update(path, 100001, unexpected) == tag
    assert (
        update.check_update(path, 100000 + update.TTL_SECS, lambda: "vpnd-v10.0.0")
        == "vpnd-v10.0.0"
    )
    assert update.load_cache(path, 100000 + update.TTL_SECS)["latest_tag"] == "vpnd-v10.0.0"
    path.write_text("corrupt")
    assert update.check_update(path, 200000, lambda: tag) == tag
    assert update.load_cache(path, 200000)["latest_tag"] == tag
    assert update.check_update(path, 300000, unexpected) is None
    file = tmp_path / "file"
    file.touch()
    assert update.check_update(file / update.CACHE_FILE, 1, lambda: tag) == tag


def server(status, body, stall=0):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    url = f"http://127.0.0.1:{listener.getsockname()[1]}/releases/latest"
    requests = []

    def serve():
        conn, _ = listener.accept()
        with conn:
            conn.settimeout(5)
            requests.append(conn.recv(4096).decode())
            if stall:
                time.sleep(stall)
            else:
                conn.sendall(
                    f"HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}".encode()
                )
        listener.close()

    thread = threading.Thread(target=serve)
    thread.start()
    return url, thread, requests


# Rust test: vpnd/src/commands/update.rs::release_fetch_uses_real_http_json_and_rejects_http_or_schema_errors
def test_release_fetch_uses_real_http_json_and_rejects_http_or_schema_errors():
    for status, body, expected in [
        ("200 OK", '{"tag_name":"vpnd-v9.0.0"}', "vpnd-v9.0.0"),
        ("200 OK", "{}", None),
        ("200 OK", "not json", None),
        ("503 Service Unavailable", "{}", None),
    ]:
        url, thread, requests = server(status, body)
        try:
            if expected is None:
                with pytest.raises(Exception):
                    update.fetch_latest_tag(url)
            else:
                assert update.fetch_latest_tag(url) == expected
        finally:
            thread.join()
        assert (
            requests[0].startswith("GET /releases/latest HTTP/1.1")
            and "user-agent: vpnd/" in requests[0].lower()
        )


# Rust test: vpnd/src/commands/update.rs::production_cache_load_enforces_ttl_and_rejects_corrupt_or_future_data
def test_production_cache_load_enforces_ttl_and_rejects_corrupt_or_future_data(tmp_path):
    path = tmp_path / update.CACHE_FILE
    assert update.load_cache(path, 100000) is None
    for raw, fresh in [
        ("invalid toml", False),
        ("", False),
        ("checked_at = 100000", False),
        ("checked_at = 100001\nlatest_tag = 'vpnd-v9.0.0'", False),
        (f"checked_at = {100000 - update.TTL_SECS}\nlatest_tag = 'vpnd-v9.0.0'", False),
        (f"checked_at = {100001 - update.TTL_SECS}\nlatest_tag = 'vpnd-v9.0.0'", True),
    ]:
        path.write_text(raw)
        cached = update.load_cache(path, 100000)
        assert bool(cached) == fresh
        if cached:
            assert cached["latest_tag"] == "vpnd-v9.0.0"


# Rust test: vpnd/src/commands/update.rs::normalize_tag_accepts_both_release_train_schemes
def test_normalize_tag_accepts_both_release_train_schemes():
    for value, expected in [
        ("vpnd-v9.0.0", "9.0.0"),
        ("v9.0.0", "9.0.0"),
        ("vpnd-v0.1.0", "0.1.0"),
        ("release-2026-08-23", None),
        ("9.0.0", None),
    ]:
        assert update.normalize_tag(value) == expected


# Rust test: vpnd/src/commands/update.rs::notice_requires_a_strictly_newer_parseable_release
def test_notice_requires_a_strictly_newer_parseable_release():
    current = update.parse_version(version())
    total = current[0] * 10000 + current[1] * 100 + current[2]

    def bump(n):
        v = total + n
        return f"vpnd-v{v // 10000}.{v // 100 % 100}.{v % 100}"

    assert not update.is_newer(bump(-1)) and not update.is_newer(bump(0))
    assert update.is_newer(bump(1)) and update.is_newer(bump(1).removeprefix("vpnd-"))
    assert not update.is_newer(bump(1) + "-rc1") and not update.is_newer("release-2026-08-23")


# Rust test: vpnd/src/commands/update.rs::stalled_connection_fails_within_the_explicit_timeout
def test_stalled_connection_fails_within_the_explicit_timeout():
    url, thread, _ = server("200 OK", "", stall=2)
    start = time.monotonic()
    try:
        with pytest.raises(Exception):
            update.fetch_latest_tag_with_timeout(url, 1)
        assert time.monotonic() - start < 4
    finally:
        thread.join()


def test_total_timeout_bounds_a_trickling_header():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(3)
    url = f"http://127.0.0.1:{listener.getsockname()[1]}/releases/latest"
    accepted = threading.Event()
    requests = []

    def serve():
        try:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(3)
                requests.append(conn.recv(4096).decode())
                accepted.set()
                try:
                    # The status/header cannot complete before the one-second
                    # total request budget, even when every read makes progress.
                    for byte in b"HTTP/1.1 200 OK\r\nX-Slow: " + b"x" * 100:
                        conn.sendall(bytes([byte]))
                        time.sleep(0.05)
                except OSError:
                    pass
        except (TimeoutError, OSError):
            pass
        finally:
            listener.close()

    thread = threading.Thread(target=serve)
    thread.start()
    start = time.monotonic()
    try:
        with pytest.raises(Exception):
            update.fetch_latest_tag_with_timeout(url, 1)
        assert time.monotonic() - start < 4
        assert accepted.is_set(), "timeout must be observed during a real header exchange"
        assert requests[0].startswith("GET /releases/latest HTTP/1.1")
    finally:
        listener.close()
        thread.join(timeout=4)
        assert not thread.is_alive()


def test_update_tag_trim_preserves_invalid_control_separators():
    from vpnd.text import WHITE_SPACE

    assert update.normalize_tag(WHITE_SPACE + "vpnd-v999.0.0" + WHITE_SPACE) == "999.0.0"
    for character in ["\x1c", "\x1d", "\x1e", "\x1f"]:
        for tag in [character + "vpnd-v999.0.0", "vpnd-v999.0.0" + character]:
            assert not update.is_newer(tag)


def test_total_timeout_bounds_dns_and_stops_late_network_work(tmp_path, monkeypatch):
    import subprocess

    marker = tmp_path / "late-network"
    ready = tmp_path / "resolver-started"
    # The real child records resolver entry before blocking. This proves the
    # timeout exercises DNS rather than only cold interpreter startup.
    delay = (
        "import socket, time, os\ndef stalled_resolver(*args, **kwargs):\n open("
        + repr(str(ready))
        + ", 'w').write(str(os.getpid()))\n time.sleep(2)\n open("
        + repr(str(marker))
        + ", 'w').write('late resolver')\n raise OSError('resolver stalled')\nsocket.getaddrinfo = stalled_resolver\n"
    )
    monkeypatch.setattr(update, "_FETCH_WORKER", delay + update._FETCH_WORKER)
    started = time.monotonic()
    with pytest.raises(Exception):
        update.fetch_latest_tag_with_timeout("http://invalid.example/releases/latest", 1)
    assert time.monotonic() - started < 1.75
    assert ready.is_file(), "the isolated worker must reach the DNS boundary"
    status = subprocess.run(
        ["ps", "-o", "stat=", "-p", ready.read_text()], capture_output=True, text=True
    )
    assert not status.stdout.strip(), "timed-out resolver worker must be killed and reaped"
    assert not marker.exists()


def test_fetch_worker_exits_when_parent_is_terminated(tmp_path):
    import os
    import signal
    import subprocess
    import sys

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    url = f"http://127.0.0.1:{listener.getsockname()[1]}/releases/latest"
    source = (
        "from vpnd.commands.update import fetch_latest_tag_with_timeout; fetch_latest_tag_with_timeout("
        + repr(url)
        + ", 10)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", source],
        env={
            **os.environ,
            "PYTHONPATH": str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    connection = None
    try:
        listener.settimeout(3)
        connection, _ = listener.accept()
        connection.recv(4096)
        # The request proves the private worker is alive, even though its
        # foreground parent receives a direct signal instead of group delivery.
        parent.send_signal(signal.SIGTERM)
        assert parent.wait(timeout=3) == -signal.SIGTERM
        connection.settimeout(3)
        assert connection.recv(1) == b""
    finally:
        listener.close()
        if connection is not None:
            connection.close()
        if parent.poll() is None:
            parent.kill()
        parent.wait()
