"""Actual portable TLS checks for native fixture readiness; no native acceptance."""
from __future__ import annotations

import shutil
import time

import pytest
from test_device_lifecycle_probe import HttpsOrigin, PortableRuntime, certificate
from test_device_lifecycle_probe_native import wait_for_native_decoy


@pytest.mark.parametrize("state", ["ready", "wrong-body", "untrusted", "unavailable"])
def test_decoy_readiness_requires_actual_trusted_payload_within_one_deadline(tmp_path, state):
    cert, key = certificate(tmp_path)
    origin = HttpsOrigin(cert, key)
    if state == "untrusted":
        other = tmp_path / "other"
        other.mkdir()
        cert, _ = certificate(other)
    runtime = PortableRuntime(binaries={"curl": shutil.which("curl")}, ca_file=cert)
    body = b"different payload" if state == "wrong-body" else origin.body
    closed = state == "unavailable"
    if closed:
        origin.close()
    timeout = 3 if state == "ready" else 0.4
    started = time.monotonic()
    try:
        if state == "ready":
            wait_for_native_decoy(runtime, origin.url, body, tmp_path, timeout=timeout)
            assert time.monotonic() - started < timeout
        else:
            with pytest.raises(AssertionError, match="decoy readiness"):
                wait_for_native_decoy(runtime, origin.url, body, tmp_path, timeout=timeout)
            assert timeout <= time.monotonic() - started < timeout + 2
        assert not list(tmp_path.glob("*.body")), "readiness must reclaim response files"
    finally:
        if not closed:
            origin.close()
