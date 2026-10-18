"""The upgrade fixture renders hopping policy for its actual owned ingress."""
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
from pathlib import Path

from template_render import merge_render_vars

ROOT = Path(__file__).resolve().parents[2]


def test_upgrade_hopping_uses_owned_veth_without_replacing_convergence_facts(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "runtime_hopping_context", ROOT / "tests/integration/transport_runtime_acceptance/fixture.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    lab = fixture.Lab.__new__(fixture.Lab)
    lab.token, lab.namespace = "rtatest", "rtatest"
    lab.host_link, lab.peer_link = "rtatesth", "rtatestp"
    lab.context = merge_render_vars()
    lab.context["ansible_facts"]["default_ipv4"]["interface"] = "ordinary4"
    lab.context["ansible_facts"]["default_ipv6"] = {"interface": "ordinary6"}
    original_facts = deepcopy(lab.context["ansible_facts"])
    calls = []

    def record(argv, **kwargs):
        calls.append((argv, kwargs))
        return ""

    monkeypatch.setattr(fixture, "command", record)
    with ExitStack() as lab.resources:
        lab.enable_hysteria_hopping()
    rules = next(kwargs["input"].decode() for argv, kwargs in calls
                 if argv == ["nft", "-f", "-"])
    redirect = next(line for line in rules.splitlines() if 'comment "hysteria-port-hopping"' in line)
    assert 'iifname { "rtatesth" } fib daddr type local udp dport 46000-46015' in redirect
    assert 'ordinary4' not in redirect and 'ordinary6' not in redirect
    assert lab.context["ansible_facts"] == original_facts
    assert "redirect to :443" in redirect
