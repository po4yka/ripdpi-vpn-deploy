"""Execute the actual private smoke template against an exact native server."""
from copy import deepcopy
from pathlib import Path
import time

import pytest
import yaml

from scripts.template_render import render_fragment
from test_xhttp_endpoint_contract_native import fixture

pytestmark = pytest.mark.native_runtime
ROOT = Path(__file__).resolve().parents[2]


def tasks(rows):
    for row in rows:
        yield row
        for key in ("tasks", "block", "rescue", "always"):
            yield from tasks(row.get(key, []))


@pytest.mark.parametrize("salamander", [False, True])
def test_canonical_smoke_client_uses_own_sni_trust_and_obfuscation(salamander):
    template = next(row["ansible.builtin.copy"]["content"] for row in tasks(
        yaml.safe_load((ROOT / "ansible/playbooks/smoke-test.yml").read_text()))
        if row.get("name") == "Render Hysteria client config")
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_hysteria(salamander=salamander)
        values = deepcopy(stack.values)
        values["hysteria"]["server_name"] = "owned.example"
        values["nginx_xhttp"]["server_name"] = "different.example"
        rendered = render_fragment("canonical-smoke.yaml", template, values)
        document = yaml.safe_load(rendered)
        assert document["tls"]["sni"] == "owned.example" and document["tls"]["insecure"] is False
        assert ("obfs" in document) is salamander
        config = stack.file("canonical-smoke.yaml", rendered)
        unit = stack.unit("canonical-smoke", [stack.hysteria, "client", "-c", str(config)])
        time.sleep(.5)
        stack.run_driver(31081)
        wrong = deepcopy(document)
        wrong["tls"]["sni"] = "wrong.example"
        wrong["socks5"]["listen"] = "127.0.0.1:31082"
        refused = stack.file("wrong-smoke.yaml", yaml.safe_dump(wrong))
        stack.unit("wrong-smoke", [stack.hysteria, "client", "-c", str(refused)])
        time.sleep(.5)
        stack.run_driver(31082, True)
        stack.run_driver(31081)
        journal = fixture.command(["journalctl", "--unit", unit, "--no-pager", "-o", "cat"])
        assert stack.hys_password not in journal and stack.values["hysteria"]["salamander_password"] not in journal
    finally:
        stack.close()
