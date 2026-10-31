# SEC-1793428979810694: Encrypt node-side destination DNS resolution

## Objective

Hosts with systemd-resolved use strict DoT with explicit servers and a fail-closed proof, strict egress admits TCP/853, and DNS-Morph's port-53 lifecycle stays unchanged. The recipient forwarder is owned by the merged change SEC-1793428673775693; the first two steps below built an alternative NAT-redirect forwarder that was dropped when main merged first, so their checked state records superseded work, not shipped behavior.

## Ownership

Single serialized lane. Ansible: `roles/baseline/tasks/resolver.yml` and notes, `roles/firewall/templates/nftables.conf.j2`, `ansible/CLAUDE.md`. Tests: `tests/unit/test_resolver_roundtrip.py`, `tests/unit/test_runtime_audit_regressions.py`, `tests/unit/test_firewall_egress_policy.py`, the firewall snapshot golden.

## Execution

- [x] SEC-1793429342091969 Seal the normalizer to the owned loopback forwarder and render its kernel redirect in the egress policy #feature !high @item:SEC-1793428979810694
- [x] SEC-1793429343002855 Render DoH upstreams and the direct-gateway DNS forwarder inbound, frontend DoH servers and refreshed goldens #feature !high @item:SEC-1793428979810694
- [x] SEC-1793429343972584 Install the strict host DoT drop-in with proof and compensation in baseline and admit TCP/853 under strict egress #feature !high @item:SEC-1793428979810694
- [x] SEC-1793429344859335 Update the egress reference, role notes and run the full local gate #feature !high @item:SEC-1793428979810694

## Verification

- Local narrow checks: `pytest tests/unit/test_resolver_roundtrip.py tests/unit/test_runtime_audit_regressions.py tests/unit/test_firewall_egress_policy.py`, then `make snapshot-check` and `make docs-check`.
- Local gate: `make check`.
- Remote: PR CI on the exact head SHA.
- Dry-run, staging, live and client: deferred to a separately authorized `make dry-run`/`make deploy`; this change does not run them.
