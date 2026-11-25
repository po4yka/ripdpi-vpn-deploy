# SCR-1795584057908911: Admit the WARP daemon tunnel socket in the namespace relay-owner check

## Objective

Namespace policy activation succeeds while the vendor daemon holds its root-owned connected underlay socket on the relay address, and every socket that can receive normalizer UDP on that address stays refused with `foreign-relay-owner`.

## Ownership

`scripts/transport_egress_kernel.py` (`admit_owners`), `tests/unit/test_transport_egress_kernel.py`, `ansible/roles/transport-egress/CLAUDE.md`. No other session edits these paths for this task.

## Execution

- [x] SCR-1795584146089592 Admit the root-owned connected vendor tunnel socket in the namespace relay-owner check, with admitted and refused tests #bug !high @item:SCR-1795584057908911
- [x] SCR-1795584161332355 Update the transport-egress design note on foreign UDP owners #bug !high @item:SCR-1795584057908911

## Verification

- Local: `mise exec -- python3 -m pytest tests/unit/test_transport_egress_kernel.py`, `make check`.
- Remote CI: PR checks.
- Dry-run: not applicable; the admission reads live sockets and a dry-run does not run it.
- Staging: a separately authorized rerun of the WARP cohort under ANS-1795357817411977 shows that `namespace.py refresh` is admitted and that tunnel traffic passes after it.
- Live, client, artifact: not applicable.
