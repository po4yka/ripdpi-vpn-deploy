"""Coverage silence lifecycle around one node's transport mutation."""
from __future__ import annotations

import base64
import datetime
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONFIGURED = {
    "DEPLOY_SILENCE_OWNER": "deploy",
    "DEPLOY_SILENCE_COLLECTOR": "node-b",
    "DEPLOY_SILENCE_ENVIRONMENT": "fleet",
    "DEPLOY_KNOWN_HOSTS": "/pins",
}
MAIN_ID = "11111111-1111-4111-8111-111111111111"
TAIL_ID = "22222222-2222-4222-8222-222222222222"


def _module():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location("deployment_silence_under_test", ROOT / "scripts/deployment_silence.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class Gateway:
    """Stands in for the collector SSH boundary behind maintenance_silence()."""

    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def maintenance_silence(self, inventory, collector, known_hosts, owner, *, request=None, silence_id=None):
        kind = "delete" if request is None else "tail" if any(c[0] == "create" for c in self.calls) else "create"
        body = None if request is None else json.loads(request)
        self.calls.append((kind, collector, str(known_hosts), owner, body, silence_id))
        if kind in self.fail:
            raise RuntimeError("ssh: secret diagnostic /private/path")
        return {"create": MAIN_ID, "tail": TAIL_ID, "delete": silence_id}[kind]


@pytest.fixture
def silence(monkeypatch):
    module = _module()

    def install(gateway):
        monkeypatch.setattr(module, "_operator", lambda: gateway)
        return module
    return install


def _seconds(body):
    start, end = (datetime.datetime.fromisoformat(body[key].replace("Z", "+00:00")) for key in ("starts_at", "ends_at"))
    return (end - start).total_seconds()


def test_success_tails_before_deleting_the_exact_coverage_silence(silence, capsys):
    gateway = Gateway()
    with silence(gateway).coverage_silence("scaleway-p1-scaleway", CONFIGURED):
        assert [call[0] for call in gateway.calls] == ["create"]
    assert [call[0] for call in gateway.calls] == ["create", "tail", "delete"]
    create, tail, delete = gateway.calls
    expected = {"environment": "fleet", "node": "scaleway-p1-scaleway", "component": "observability-external-coverage"}
    assert create[4]["matchers"] == tail[4]["matchers"] == expected
    assert create[1:4] == ("node-b", "/pins", "deploy")
    assert (_seconds(create[4]), _seconds(tail[4])) == (7500, 300)
    assert delete[5] == MAIN_ID
    assert capsys.readouterr().err == ""


def test_failed_mutation_deletes_without_tail_and_keeps_its_error(silence):
    gateway = Gateway()
    with pytest.raises(KeyboardInterrupt), silence(gateway).coverage_silence("node-id", CONFIGURED):
        raise KeyboardInterrupt
    assert [call[0] for call in gateway.calls] == ["create", "delete"]


@pytest.mark.parametrize("fail,expected_calls,warning", [
    ({"create"}, ["create"], "not created"),
    ({"tail"}, ["create", "tail", "delete"], "tail not created"),
    ({"delete"}, ["create", "tail", "delete"], "not deleted; it expires at its finite end"),
])
def test_gateway_failure_only_warns_categorically(silence, capsys, fail, expected_calls, warning):
    gateway, ran = Gateway(fail), []
    with silence(gateway).coverage_silence("node-id", CONFIGURED):
        ran.append(True)
    err = capsys.readouterr().err
    assert ran == [True]
    assert [call[0] for call in gateway.calls] == expected_calls
    assert err == f"deploy: warning: maintenance silence {warning}\n"


@pytest.mark.parametrize("environ,node,err", [
    ({}, "node-id", ""),
    (CONFIGURED, "", ""),
    ({"DEPLOY_SILENCE_OWNER": "deploy"}, "node-id", "deploy: warning: maintenance silence configuration incomplete\n"),
])
def test_unconfigured_or_unidentified_node_makes_no_gateway_call(silence, capsys, environ, node, err):
    gateway, ran = Gateway(), []
    with silence(gateway).coverage_silence(node, environ):
        ran.append(True)
    assert ran == [True] and gateway.calls == []
    assert capsys.readouterr().err == err


def _operator(monkeypatch, host):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location("silence_operator", ROOT / "scripts/observability-operator.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    seen = {}
    monkeypatch.setattr(module, "_selected_host", lambda args: host)
    monkeypatch.setattr(module, "_require_inventory_scope",
                        lambda args, selected, *source: seen.update(environment=args.environment, source=source))
    monkeypatch.setattr(module.fleet_inspection, "_local_file", lambda path: None)

    def remote(args, selected, payload, *, operation):
        seen.update(operation=operation, payload=payload.decode())
        return {"silence_id": MAIN_ID}
    monkeypatch.setattr(module, "_remote", remote)
    return module, seen


def _collector(env, *nodes):
    topology = base64.b64encode(json.dumps({"nodes": [{"node_id": node} for node in nodes]}).encode()).decode()
    return {"variables": {"env": env, "observability_topology_b64": topology}}


def _silence_request(node):
    return json.dumps({"matchers": {"node": node}}).encode()


def test_operator_admits_collector_by_its_own_environment_without_source_binding(monkeypatch):
    module, seen = _operator(monkeypatch, _collector("p1-scaleway", "node-id"))
    assert module.maintenance_silence(Path("inv"), "node-b", Path("pins"), "deploy",
                                      request=_silence_request("node-id")) == MAIN_ID
    assert (seen["environment"], seen["source"], seen["operation"]) == ("p1-scaleway", (), "silence-create")
    assert "silence-owner-deploy-token" in seen["payload"] and "/v1/silences" in seen["payload"]
    module.maintenance_silence(Path("inv"), "node-b", Path("pins"), "deploy", silence_id=MAIN_ID)
    assert seen["operation"] == "silence-delete" and "/v1/silences/" + MAIN_ID in seen["payload"]


@pytest.mark.parametrize("owner,kwargs", [
    ("deploy", {}),
    ("deploy", {"request": _silence_request("node-id"), "silence_id": MAIN_ID}),
    ("Deploy;", {"request": _silence_request("node-id")}),
    ("deploy", {"request": _silence_request("other-collector-node")}),
])
def test_operator_refuses_ambiguous_unsafe_or_unmonitored_silence_calls(monkeypatch, owner, kwargs):
    module, seen = _operator(monkeypatch, _collector("fleet", "node-id"))
    with pytest.raises(module.OperatorError):
        module.maintenance_silence(Path("inv"), "node-b", Path("pins"), owner, **kwargs)
    assert "operation" not in seen
