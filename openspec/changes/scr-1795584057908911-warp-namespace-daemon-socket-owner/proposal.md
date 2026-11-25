# Change: Admit the WARP daemon tunnel socket in the namespace relay-owner check

Task ID: `SCR-1795584057908911`

## Why

The WARP cohort cannot deploy. On the disposable node of the 2026-11-24/25 staging run (revision 60a371e4b) the vendor daemon connected and its tunnel interface was up, but `namespace.py refresh` was refused with `foreign-relay-owner` on all 30 attempts, and the deploy recovered the accepted generation. The transport-egress policy loader refuses every UDP socket whose local address is the WARP relay address and whose owner is not the WARP gateway. The vendor daemon runs inside the same namespace, and that namespace has one address, so the daemon's own connected underlay socket has the relay address as its local address. The loader admitted the captured socket listing when that one line was removed. This blocks step ANS-1795358069969748 of task ANS-1795357817411977.

## What Changes

- Inside the WARP namespace, the socket-owner admission accepts a UDP socket on the relay address that root owns and that is connected to a peer other than the host side of the namespace link.
- Every other UDP socket on the relay address that the WARP gateway does not own stays refused with `foreign-relay-owner`: a non-root owner, an unconnected socket, a socket connected to the host side of the link, and a socket whose peer cannot be read as an address.
- The host (direct gateway) admission does not change.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `transports/resolved-destination-boundary`: adds the relay-address socket-owner requirement, with the vendor tunnel exception in the WARP namespace.

## Impact

- `scripts/transport_egress_kernel.py`, installed on nodes as the transport-egress policy loader. Nodes receive it on the next deploy.
- `ansible/roles/transport-egress/CLAUDE.md` design note.
- No change to rendered nftables rules, secrets, schemas, Terraform or client contracts. Profiles without WARP are not affected.
