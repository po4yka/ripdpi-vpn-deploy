# SEC-1787916931540401

## Objective

Deliver restricted ordinary SSH management with policy-preserving legacy migration and recoverable activation.

## Ownership

Primary owns the transaction/controller/installation surfaces and integration; delegated planner work is limited to `ansible/roles/baseline/files/sshd_ownership.py` and its dedicated unit tests. Coordinator-owned inventory, site pre-task tags and backup surfaces are excluded. Shared Makefile edits are serialized.

## Execution

- [x] SEC-1787917604306451 Implement the bounded legacy SSH ownership planner and full effective-policy regression tests #feature !high @item:SEC-1787916931540401
- [x] SEC-1787917604868749 Implement durable fixed-path SSH activation and recovery with interruption and reboot reconciliation tests #feature !high @item:SEC-1787916931540401
- [ ] SEC-1787917605386179 Install restricted opt-in Tailnet management without changing DNS routes or SSH identity #feature !high @item:SEC-1787916931540401
- [ ] SEC-1787917605886845 Implement exact-node strict connection promotion and owned guest and provider network rollback #feature !high @item:SEC-1787916931540401
- [ ] SEC-1787917606418274 Rehearse migration and recovery on the authorized isolated staging node using real SSH #feature !high @item:SEC-1787916931540401
- [ ] SEC-1787917606923503 Roll out approved management changes serially and verify unchanged emergency and VPN paths #feature !high @item:SEC-1787916931540401

## Verification

Run focused real-OpenSSH and filesystem failure tests first, then both pinned distro checks, `make ci-fast`, `make validate`, independent review and exact-SHA CI. Actual staging disconnect/reboot and serial fleet probes are separate required steps; no external write is performed by local verification.
