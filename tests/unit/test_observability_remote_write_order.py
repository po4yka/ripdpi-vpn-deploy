"""Exercise retained remote-write batches against the pinned receiver."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest
import yaml

from scripts.template_render import render_template
from tests.unit.test_observability_control_plane_render import ROLE, _values

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _varint(value: int) -> bytes:
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _field(number: int, value: bytes) -> bytes:
    return _varint(number << 3 | 2) + _varint(len(value)) + value


def _write_payload(samples: list[tuple[str, int, float]]) -> bytes:
    # Remote Write v1: WriteRequest.timeseries, TimeSeries.labels/samples,
    # Label.name/value and Sample.value/timestamp. Each message has one sample.
    payload = b""
    for metric, timestamp, value in samples:
        series = b"".join(
            _field(1, _field(1, name.encode()) + _field(2, label.encode()))
            for name, label in (("__name__", metric), ("node", "node-fixture"))
        )
        sample = b"\x09" + struct.pack("<d", value) + b"\x10" + _varint(timestamp)
        payload += _field(1, series + _field(2, sample))
    # A single literal is valid unframed Snappy; no compression library is needed.
    length = len(payload) - 1
    if length < 60:
        literal = bytes([length << 2])
    else:
        width = (length.bit_length() + 7) // 8
        literal = bytes([(59 + width) << 2]) + length.to_bytes(width, "little")
    return _varint(len(payload)) + literal + payload


def _write(origin: str, samples: list[tuple[str, int, float]]) -> int:
    request = urllib.request.Request(
        origin + "/api/v1/write",
        data=_write_payload(samples),
        headers={
            "Content-Type": "application/x-protobuf",
            "Content-Encoding": "snappy",
            "X-Prometheus-Remote-Write-Version": "0.1.0",
        },
    )
    try:
        with OPENER.open(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        error.close()
        return error.code


def _query(origin: str, expression: str, timestamp: int) -> list[dict]:
    parameters = urllib.parse.urlencode({"query": expression, "time": timestamp / 1000})
    with OPENER.open(origin + "/api/v1/query?" + parameters, timeout=5) as response:
        result = json.loads(response.read(65537))
    assert result["status"] == "success"
    assert result["data"]["resultType"] == "vector"
    return result["data"]["result"]


@contextlib.contextmanager
def _receiver(tmp_path: Path, configuration: dict):
    binary = shutil.which("prometheus")
    assert binary is not None, "The pinned Prometheus receiver is required."
    version = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, check=True, timeout=5
    )
    assert "prometheus, version 3.14.0 " in version.stdout + version.stderr
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    config = tmp_path / "prometheus.yml"
    config.write_text(yaml.safe_dump(configuration))
    origin = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            binary,
            "--config.file=" + str(config),
            f"--web.listen-address=127.0.0.1:{port}",
            "--web.enable-remote-write-receiver",
            "--storage.tsdb.path=" + str(tmp_path / "data"),
            "--storage.tsdb.retention.time=7d",
            "--storage.tsdb.retention.size=64MB",
            "--storage.tsdb.wal-segment-size=10MB",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            assert process.poll() is None, "The pinned receiver failed to start."
            try:
                with OPENER.open(origin + "/-/ready", timeout=1) as response:
                    if response.status == 200:
                        break
            except urllib.error.HTTPError as error:
                error.close()
                if error.code != 503:
                    raise
                # TSDB startup/replay can return 503 until ready; retry only
                # within the same 15-second deadline checked below.
            except (
                urllib.error.URLError,
                ConnectionRefusedError,
                TimeoutError,
            ) as error:
                reason = (
                    error.reason if isinstance(error, urllib.error.URLError) else error
                )
                if not isinstance(reason, (ConnectionRefusedError, TimeoutError)):
                    raise
                # The loopback listener can refuse or time out during startup;
                # the deadline below bounds these expected connection retries.
            assert time.monotonic() < deadline, "Receiver readiness timed out."
            time.sleep(0.05)
        yield origin
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.parametrize("configured", [False, True])
def test_pinned_receiver_recovers_exact_reordered_batch_within_retention(
    tmp_path, configured
):
    values = _values()
    configuration = yaml.safe_load(
        render_template(ROLE / "templates/prometheus.yml.j2", values)
    )
    retention = values["observability_control_plane"]["tsdb_retention_time"]
    assert configuration["storage"]["tsdb"]["out_of_order_time_window"] == retention
    if not configured:
        configuration["storage"]["tsdb"]["out_of_order_time_window"] = "0s"
    now = time.time_ns() // 1_000_000
    historical = now - 60_000
    metric = "vpn_observability_rollback_probe"
    selector = metric + '{node="node-fixture"}'
    nonce = 123456789.0
    with _receiver(tmp_path, configuration) as origin:
        assert _write(origin, [("node_load1", now, 0.5)]) == 204
        # The pinned sender can return its unsent worker block to the queue tail
        # on stop, after later blocks. Preserve the batch and its sample times.
        status = _write(
            origin,
            [("node_load1", historical, 0.4), (metric, historical, nonce)],
        )
        if not configured:
            assert status == 400
            assert _query(origin, selector, historical) == []
            return
        assert status == 204
        rows = _query(origin, selector, historical)
        clocks = _query(origin, "timestamp(" + selector + ")", historical)
        assert len(rows) == len(clocks) == 1
        assert rows[0]["metric"] == {"__name__": metric, "node": "node-fixture"}
        assert clocks[0]["metric"] == {"node": "node-fixture"}
        assert float(rows[0]["value"][1]) == nonce
        assert float(clocks[0]["value"][1]) == historical / 1000
        expired = now - 7 * 86400 * 1000 - 1000
        assert _write(origin, [("node_load1", expired, 0.3)]) == 400


def test_fixture_receiver_uses_its_own_finite_retention_window():
    agent = ROLE.parent / "observability_agent"
    tasks = yaml.safe_load((agent / "molecule/enabled/prepare.yml").read_text())[0][
        "tasks"
    ]
    config = next(
        task["ansible.builtin.copy"]["content"]
        for task in tasks
        if task["name"]
        == "Configure the fixture sink without scrapes or remote destinations"
    )
    unit = next(
        task["ansible.builtin.copy"]["content"]
        for task in tasks
        if task["name"]
        == "Install isolated sink using the already verified previous Prometheus binary"
    )
    assert yaml.safe_load(config)["storage"]["tsdb"]["out_of_order_time_window"] == "1h"
    assert "--storage.tsdb.retention.time=1h" in unit


def _track_receiver_process(monkeypatch):
    processes = []
    original = subprocess.Popen

    def start(*args, **kwargs):
        process = original(*args, **kwargs)
        command = args[0] if args else kwargs.get("args", [])
        if "--web.enable-remote-write-receiver" in command:
            processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", start)
    return processes


@pytest.mark.parametrize("failure", ["http-500", "unexpected-url-reason"])
def test_receiver_readiness_propagates_unexpected_failures_and_cleans_up(
    tmp_path, monkeypatch, failure
):
    processes = _track_receiver_process(monkeypatch)
    error = (
        urllib.error.HTTPError("http://127.0.0.1/-/ready", 500, "unexpected", {}, None)
        if failure == "http-500"
        else urllib.error.URLError(ValueError("unexpected opener failure"))
    )
    requests = []

    def unavailable(url, timeout):
        requests.append(url)
        assert timeout == 1
        raise error

    monkeypatch.setattr(OPENER, "open", unavailable)
    with pytest.raises(type(error)) as caught:
        with _receiver(tmp_path, {"scrape_configs": []}):
            pytest.fail("Unexpected readiness failure was accepted.")
    assert caught.value is error
    assert len(requests) == 1, "Unexpected failures must propagate without retries."
    assert len(processes) == 1
    assert processes[0].poll() is not None, "Failed startup must retire its receiver."


@pytest.mark.parametrize("failure", ["http-503", "connection-refused"])
def test_receiver_readiness_bounds_expected_retries_and_cleans_up(
    tmp_path, monkeypatch, failure
):
    from types import SimpleNamespace
    import sys

    processes = _track_receiver_process(monkeypatch)
    error = (
        urllib.error.HTTPError("http://127.0.0.1/-/ready", 503, "starting", {}, None)
        if failure == "http-503"
        else urllib.error.URLError(ConnectionRefusedError("listener starting"))
    )
    requests, sleeps = [], []
    elapsed = [0.0]

    def unavailable(url, timeout):
        requests.append(url)
        assert timeout == 1
        assert len(requests) <= 2, "Readiness retried past its 15-second budget."
        raise error

    def advance(seconds):
        sleeps.append(seconds)
        elapsed[0] += 16

    # Replace this test module's clock facade; subprocess cleanup retains its
    # real clock and the receiver remains a real pinned process.
    monkeypatch.setattr(
        sys.modules[__name__],
        "time",
        SimpleNamespace(
            monotonic=lambda: elapsed[0],
            sleep=advance,
        ),
    )
    monkeypatch.setattr(OPENER, "open", unavailable)
    with pytest.raises(AssertionError, match="Receiver readiness timed out"):
        with _receiver(tmp_path, {"scrape_configs": []}):
            pytest.fail("An unavailable receiver was accepted.")
    assert len(requests) == 2
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 1
    assert len(processes) == 1
    assert processes[0].poll() is not None, (
        "Timed-out startup must retire its receiver."
    )
