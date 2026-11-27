"""The egress-proxy role refuses unsafe listen, region and allowlist inputs before any host change.

Evaluates the real assert task from the role with the pinned ansible-core templar.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

ROLE = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "egress-proxy"
TASK_NAME = "Admit proxy inputs before any host change"
DEFAULTS = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text())


def _admitted(**overrides: object) -> bool:
    task = next(t for t in yaml.safe_load((ROLE / "tasks" / "main.yml").read_text()) if t["name"] == TASK_NAME)
    variables = {**DEFAULTS, "egress_proxy_listen_address": "100.64.0.1", "egress_proxy_b2_region": "us-west-004"}
    variables.update(overrides)
    templar = Templar(loader=DataLoader(), variables=variables)
    variables.update({k: templar.template(trust_as_template(v)) for k, v in task["vars"].items()})
    templar.available_variables = variables
    return all(
        templar.template(trust_as_template("{{ " + condition + " }}"))
        for condition in task["ansible.builtin.assert"]["that"]
    )


def test_tailnet_address_and_region_are_admitted() -> None:
    assert _admitted()
    assert _admitted(egress_proxy_listen_address="100.127.255.254")


@pytest.mark.parametrize(
    "address",
    ["", "0.0.0.0", "203.0.113.9", "100.128.0.1", "100.63.255.255", "100.064.0.1", "100.64.0.1\n", "100.64.0.256", "127.0.0.1"],
)
def test_production_listen_address_must_be_canonical_tailnet(address: str) -> None:
    assert not _admitted(egress_proxy_listen_address=address)


def test_loopback_is_admitted_only_when_the_tailnet_requirement_is_off() -> None:
    assert _admitted(egress_proxy_listen_address="127.0.0.1", egress_proxy_require_tailnet_listen=False)
    assert _admitted(egress_proxy_listen_address="0.0.0.0", egress_proxy_require_tailnet_listen=False)
    assert not _admitted(egress_proxy_listen_address="127.0.0.01", egress_proxy_require_tailnet_listen=False)


@pytest.mark.parametrize("region", ["", "US-West", "us west", "us-west-004\n"])
def test_b2_region_must_be_set_and_literal(region: str) -> None:
    assert not _admitted(egress_proxy_b2_region=region)


@pytest.mark.parametrize("host", [".api.vultr.com", "*.vultr.com", "api.vultr.com.", "localhost", "api.vultr.com\n"])
def test_allowlist_rejects_wildcards_and_malformed_hosts(host: str) -> None:
    assert not _admitted(egress_proxy_api_hosts=["api.vultr.com", host])
