"""Actual recipient and native Xray clients against the rendered guarded P0 server.

The existing isolated Linux fixture owns all services and synthetic identities.
Provider metadata is injected in memory; transport engines are never replaced.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

import pytest
import yaml

import client_payload
from liveness_profiles import build_profiles
from template_render import render_fragment, render_template

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime
spec = importlib.util.spec_from_file_location(
    "p0_client_owned_fixture", ROOT / "tests/integration/transport_destination_boundary/fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def require_runtime(name, version):
    assert sys.platform == "linux" and os.geteuid() == 0 and os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1", "isolated-linux-root-required"
    binary = shutil.which(name)
    assert binary, "required-real-engine-unavailable"
    assert version in fixture.command([binary, "version"]), "native-engine-pin-mismatch"
    return binary


def generated_p0(stack, monkeypatch):
    values = deepcopy(stack.values)
    values["vpn"].update(enable_hysteria=False, enable_amneziawg=False, enable_snell=False, enable_naive=False)
    values["xray"]["reality_public_key"] = stack.reality_password
    values["xray"]["version"] = "v26.3.27"
    # This is the metadata boundary only. Both the materializer and protocol
    # configuration stay real, and no provider CLI or secret file is read.
    def metadata(argv, **_):
        assert argv[-3:] == ["output", "-raw", "server_ipv4"]
        return b"192.0.2.90"
    monkeypatch.setattr(client_payload, "command", metadata)
    monkeypatch.setattr(client_payload, "context", lambda _: deepcopy(values))
    document = {"xray": values["xray"], "client_registry": {"native-device": {"status": "active"}}}
    source = str(stack.library / "in-memory-authority")
    options = client_payload.options("singbox", hosts=["upcloud:fixture"], cohorts=["p0-minimal"])
    delivered, _ = client_payload.materialize("native-device", options, documents={source: document}, source_paths=[source])
    built = build_profiles(delivered, None, document, "native-device", ["p0-reality"],
                           None, None, None, None, str(stack.library), awg_defaults={}, awg_cohort={})
    return built["files"]["sing-box.json"]


def start_sing_box(stack, binary, document, label):
    path = stack.file(label + ".json", json.dumps(document), "x")
    fixture.command([str(binary), "check", "-c", str(path)])
    stack.unit(label, [str(binary), "run", "-c", str(path)], "x")
    time.sleep(.5)
    return document["inbounds"][0]["listen_port"]


def test_generated_vision_recipient_preserves_authenticated_tcp_xudp_and_refusal(monkeypatch):
    require_runtime("xray", "Xray 26.3.27")
    binary = require_runtime("sing-box", "sing-box version 1.14.3")
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_frontend("p0")
        executable = stack.library / "sing-box"
        shutil.copyfile(binary, executable)
        executable.chmod(0o555)
        delivered = generated_p0(stack, monkeypatch)
        assert delivered["outbounds"][0]["flow"] == "xtls-rprx-vision"
        assert "multiplex" not in delivered["outbounds"][0]
        port = start_sing_box(stack, executable, delivered, "recipient")
        stack.run_driver(port)
        invalid = deepcopy(delivered)
        invalid["inbounds"][0]["listen_port"] += 1
        invalid["outbounds"][0]["uuid"] = str(uuid.uuid4())
        rejected = start_sing_box(stack, executable, invalid, "wrong-recipient")
        stack.run_driver(rejected, True)
        stack.run_driver(port)
    finally:
        stack.close()


def smoke_document(stack):
    tasks = yaml.safe_load((ROOT / "ansible/playbooks/tasks/smoke-reality.yml").read_text())[0]["block"]
    source = next(task["ansible.builtin.copy"]["content"] for task in tasks if task["name"] == "Render Xray client config (REALITY)")
    values = deepcopy(stack.values)
    values["xray"]["reality_public_key"] = stack.reality_password
    values["smoketest_client"] = values["xray"]["clients"][0]
    values["smoketest_reality_cohort"] = {"port": 443}
    def lookup(plugin, path, *, template_vars):
        assert plugin == "ansible.builtin.template" and Path(path).resolve() == (ROOT / "ansible/templates/p0-reality-shape.json.j2").resolve()
        return render_template(Path(path), {**values, **template_vars})
    return json.loads(render_fragment("smoke.json.j2", source, {**values, "lookup": lookup}))


def start_xray(stack, document, label):
    path = stack.file(label + ".json", json.dumps(document), "x")
    fixture.command([stack.xray, "run", "-test", "-config", str(path)])
    stack.unit(label, [stack.xray, "run", "-config", str(path)], "x")
    time.sleep(.5)
    return document["inbounds"][0]["port"]


@pytest.mark.parametrize("flow,masked", [("mux", False), ("vision", True), ("mux", True)])
def test_native_smoke_shape_authentication_xudp_and_active_finalmask(flow, masked):
    require_runtime("xray", "Xray 26.3.27")
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.values["vpn"].update(xray_flow_mode=flow, xray_finalmask=masked)
        stack.start_frontend("p0")
        document = smoke_document(stack)
        watchdog_values = deepcopy(stack.values)
        watchdog_values["xray"]["reality_public_key"] = stack.reality_password
        watchdog_values["watchdog"]["reality_probe_client"] = "native-device"
        watchdog_values["vpn_service_address"] = "192.0.2.90"
        watchdog_values["watchdog_reality_probes"] = [{"port": 443, "p0_reality_shape_input": {}}]
        watchdog = stack.file("watchdog.json", render_template(
            ROOT / "ansible/roles/watchdog/templates/reality-probe.json.j2", watchdog_values), "x")
        fixture.command([stack.xray, "run", "-test", "-config", str(watchdog)])
        stream = document["outbounds"][0]["streamSettings"]
        assert ("finalmask" in stream) is masked
        assert document["outbounds"][0].get("mux", {}).get("enabled", False) is (flow == "mux")
        port = start_xray(stack, document, "native-smoke")
        stack.run_driver(port)
        invalid = deepcopy(document)
        invalid["inbounds"][0]["port"] += 1
        invalid["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"] = str(uuid.uuid4())
        stack.run_driver(start_xray(stack, invalid, "wrong-native-identity"), True)
        if masked:
            unmasked = deepcopy(document)
            unmasked["inbounds"][0]["port"] += 2
            del unmasked["outbounds"][0]["streamSettings"]["finalmask"]
            # If the typed setting were ignored, this valid unmasked identity
            # would succeed. Refusal proves that the transform is active.
            stack.run_driver(start_xray(stack, unmasked, "wrong-native-mask"), True)
        stack.run_driver(port)
    finally:
        stack.close()
