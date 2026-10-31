# SEC-1793428979810694: Encrypt node-side destination DNS resolution

## Objective

Recipient destination names resolve through the direct gateway's DoH forwarder behind an owned kernel redirect, the frontend and gateways render DoH servers with `unexpectedIPs`, and hosts with systemd-resolved use strict DoT with a fail-closed proof, while DNS-Morph's port-53 lifecycle stays unchanged.

## Ownership

Single serialized lane. Scripts: `transport_egress_config.py`, `transport_egress_normalizer.py`, `transport_egress_kernel.py`. Ansible: `roles/transport-egress` (defaults, `gateway.json.j2`, notes), `roles/xray/templates/config.json.j2`, `roles/baseline/tasks/resolver.yml` and notes, `roles/firewall/templates/nftables.conf.j2`. Tests: the matching `tests/unit` files, snapshot goldens, native egress fixtures. Docs: `docs/reference/transport-egress.md`, `ansible/CLAUDE.md`.

## Execution

- [x] SEC-1793429342091969 Seal the normalizer to the owned loopback forwarder and render its kernel redirect in the egress policy #feature !high @item:SEC-1793428979810694
- [x] SEC-1793429343002855 Render DoH upstreams and the direct-gateway DNS forwarder inbound, frontend DoH servers and refreshed goldens #feature !high @item:SEC-1793428979810694
- [x] SEC-1793429343972584 Install the strict host DoT drop-in with proof and compensation in baseline and admit TCP/853 under strict egress #feature !high @item:SEC-1793428979810694
- [x] SEC-1793429344859335 Update the egress reference, role notes and run the full local gate #feature !high @item:SEC-1793428979810694

## Verification

- Local narrow checks: `pytest tests/unit/test_transport_egress_kernel.py tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_egress_role.py tests/unit/test_resolver_roundtrip.py tests/unit/test_firewall_egress_policy.py tests/unit/test_cascade_xray_integration.py`, then `make snapshot-check` and `make docs-check`.
- Local gate: `make check`.
- Remote: PR CI on the exact head SHA, including the native egress and kernel lanes that apply the production projection.
- Dry-run, staging, live and client: deferred to a separately authorized `make dry-run`/`make deploy`; this change does not run them.
