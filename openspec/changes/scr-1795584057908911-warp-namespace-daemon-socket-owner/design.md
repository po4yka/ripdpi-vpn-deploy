## Context

`admit_owners` in `scripts/transport_egress_kernel.py` reads `ss -H -n -a -t -u -e` and refuses any UDP socket whose local address is the relay address and whose uid is not the relay gateway uid. The check exists because the first UDP sender locks the native relay to its tuple: a second receiver on the relay address could take datagrams that the normalizer sends to the gateway. In the WARP namespace the relay address (10.250.254.2) is the only address of the namespace, so the vendor daemon's underlay socket to its tunnel endpoint has the same local address. The vendor daemon runs as root; `ss -e` prints no `uid:` field for root. See proposal.md for the staging evidence.

## Goals / Non-Goals

- Goal: namespace policy activation succeeds while the vendor daemon holds its connected underlay socket.
- Goal: a socket that can receive normalizer UDP on the relay address stays refused.
- Non-goal: any change to the rendered nftables rules, the host check, or the port-owner check.
- Non-goal: proof that registered vendor traffic passes after activation. That needs a separately authorized staging run.

## Decisions

- Admit by what the socket can receive, plus the daemon identity. A connected UDP socket receives only datagrams from its peer. The normalizer reaches the namespace only from the host side of the link (10.250.254.1, `warp.host_address` in the policy), and the namespace input chain admits UDP to the relay address from that source only. A socket connected to any other peer therefore cannot receive normalizer datagrams and cannot take the relay tuple. The rule also requires uid 0, the identity of the vendor daemon, which already holds network administration in the namespace.
- Rejected: admit by port. The daemon's source port is ephemeral and the relay ports are allocated per association, so no port range separates them.
- Rejected: admit by process name. `ss` reports it only with `-p`, the name is set by the process itself, and it adds no bound on what the socket can receive.
- Rejected: admit every root-owned socket. An unconnected root socket on the relay address can receive normalizer datagrams.
- The exception applies only with `namespace=True`. The host relay address (127.0.0.55) has no second legitimate owner.
- A peer that does not parse as an address (for example `0.0.0.0:*` read as a wildcard, or a malformed field) is refused: unknown is foreign.

## Contracts and ownership

- `scripts/transport_egress_kernel.py`: the only code change. The transport-egress role installs it as the policy loader; `ansible/roles/warp-outbound/files/namespace.py` calls it for `prepare`, `guard` and `refresh`.
- `tests/unit/test_transport_egress_kernel.py`: admitted and refused cases.
- `ansible/roles/transport-egress/CLAUDE.md`: the design note on foreign UDP owners.
- No secrets, schema, Terraform, vpnd or client contract changes.

## Risks / Trade-offs

- A root process in the namespace other than the vendor daemon can hold a connected UDP socket and be admitted. Root in the namespace can already replace the namespace rules, and such a socket cannot receive normalizer datagrams, so this adds no authority.
- The rule depends on the shape of the daemon's socket on a real node (connected and root-owned). The unit test uses a synthetic line of that shape. If the real socket is unconnected, activation stays refused, which is the safe direction; the staging rerun shows it.
- Not changed here: a local address that `ss` prints with a device suffix or as a wildcard does not compare equal to the relay address, so the relay-owner check does not examine such a socket, whatever its owner. Only a process that can enter the namespace can create one. This is a follow-up, not part of this change.
- The exception relies on `ss -e` printing `uid:` for every non-root owner, because an absent field reads as root.
- This change removes one refusal. It does not prove that the vendor underlay passes once the namespace input chain is active; that chain drops UDP to the relay address from sources other than the host side of the link. The staging rerun must check tunnel traffic after refresh.

## Migration Plan

Nodes receive the loader on the next deploy; no state migrates. Rollback is a revert of the commit, which restores the stricter refusal. Gates: the narrow unit test file, `make check`, PR checks, then a separately authorized staging rerun of the WARP cohort under ANS-1795357817411977.
