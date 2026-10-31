# SEC-1793428673775693: Close the remaining traffic-privacy audit findings

## Objective

A default node resolves recipient names only through the direct gateway's DoH forwarder, keeps visitor addresses and user agents out of decoy logs, watches the borrowed REALITY target for handshake drift, refuses unmeasured WireGuard-shaped AmneziaWG instances on production and listens dual-stack for REALITY.

## Ownership

Primary: this repository. Scripts `transport_destination_policy.py`, `transport_egress_config.py`, `transport_egress_normalizer.py`, `transport_egress_kernel.py`; Ansible roles `transport-egress`, `warp-outbound`, `xray`, `nginx-xhttp`, `reality-self-steal`, `watchdog`, `amneziawg`; `ansible/group_vars/all.yml`; matching tests, snapshot goldens and documentation. No client-repository contract change.

## Execution

- [x] SEC-1793429856858268 Route normalizer and frontend DNS through the direct gateway DoH forwarder with bounded capability and kernel policy #bug !high @item:SEC-1793428673775693
- [x] SEC-1793429857802806 Strip client identity from decoy access logs and watch the REALITY target handshake #bug !high @item:SEC-1793428673775693
- [x] SEC-1793429858741823 Guard WireGuard-shaped AmneziaWG instances on production, listen dual-stack and document the I1-I5 and bandwidth-hint decisions #bug !high @item:SEC-1793428673775693

## Verification

Local: `python3 -m pytest` on the touched test files, `make snapshot-check`, then `make check -j 4 -k` once because the change spans scripts, Ansible roles and the kernel-policy contract. Remote CI: the pull request's full run at the exact head, including the native egress lanes. Dry-run, staging, live and client gates are not authorized by this change; no host is touched. Artifact: refreshed snapshot goldens reviewed in the diff.
