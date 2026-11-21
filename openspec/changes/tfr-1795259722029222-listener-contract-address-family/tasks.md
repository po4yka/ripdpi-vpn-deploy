# TFR-1795259722029222: Add an address family to the public listener contract

## Objective

Each entry of the public listener contract states whether it is reachable over IPv4, IPv6 or both. The provider firewall, the node nftables ruleset and the live listener verifier all follow that field, so a listener that serves one family is closed on the other at every layer.

## Ownership

`terraform/providers/*/` (`public_listeners` variable, firewall rules, outputs, mock-provider tests), the Conftest policies, `scripts/check-listener-contract.py`, `scripts/verify-public-listeners.py`, `ansible/templates/listener-manifest.json.j2`, `ansible/roles/firewall/templates/nftables.conf.j2`, and their tests. One writer at a time for the nftables template and the listener manifest.

## Execution

- [ ] TFR-1795259793636372 Add the optional family field with validation and a dual default to every provider root, with mock-provider tests and Conftest policies #feature @item:TFR-1795259722029222
- [ ] TFR-1795259837898750 Carry the family in the listener manifest and refuse a disagreement in the listener contract check #feature @item:TFR-1795259722029222
- [ ] TFR-1795259877267081 Accept a single-family listener only on its family in the node ruleset and report other-family accepts in the live verifier #feature @item:TFR-1795259722029222
- [ ] TFR-1795259924993740 Run staging acceptance of an IPv4-only listener closed on IPv6 at the provider and the node #feature @item:TFR-1795259722029222

## Verification

Local: `make tf-test`, `make tf-policy-verify`, the listener contract and verifier unit tests, `make snapshot-check`, `make check`. Remote CI: the full PR plan, because the change spans Terraform, Ansible and scripts. Dry-run: `make plan` and `make dry-run` for a node with a single-family listener show matching provider and node rules. Staging: a disposable node refuses the closed family at the provider and on the node. Live: the next production deploy after the operator states the family. Client: not applicable. Artifact: not applicable.
