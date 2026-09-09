"""Synthetic Tailnet enrollment; real nftables and systemd, never live proof."""
import json

import tailnet_management as domain
from tailnet_firewall import Firewall

paths = domain._production_paths()
binding = {
    "inventory_alias": "fixture-node", "public_address": "192.0.2.10",
    "ssh_port": 22, "public_sources": ["198.51.100.10"],
    "approved_sources": ["100.64.10.20", "fd7a:115c:a1e0::1234"],
    "host_key_sha256": "c" * 64, "source_revision": "a" * 40,
    "deployable_digest": "b" * 64,
}
firewall = Firewall()
status = domain.transaction_status(paths=paths, firewall=firewall, binding=binding)
if status["status"] == "configured":
    print(json.dumps({"changed": False}))
else:
    assert status["status"] == "idle", status
    capability = domain.enroll(paths=paths, firewall=firewall, binding=binding,
                               auth_key="tskey-auth-molecule-fixture")
    assert capability["status"] == "pending", capability
    assert domain.recover(paths=paths, firewall=firewall)["status"] == "pending"
    contexts = [
        {"user": "root", "host": "fixture-public", "addr": "198.51.100.10",
         "laddr": binding["public_address"], "lport": 22},
        {"user": "root", "host": "fixture-management", "addr": "100.64.10.20",
         "laddr": capability["node"]["ipv4"], "lport": 22},
    ]
    result = domain.confirm(paths=paths, firewall=firewall, capability=capability,
                            contexts=contexts)
    assert result["status"] == "configured", result
    print(json.dumps({"changed": True}))
