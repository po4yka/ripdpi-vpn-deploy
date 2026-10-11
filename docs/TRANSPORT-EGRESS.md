# Recipient destination boundary

P0 REALITY, P1 XHTTP and P2 Hysteria recipient TCP/UDP traffic uses an
unprivileged metadata normalizer, followed by the same pinned native Xray
runtime as a literal-only gateway. WARP-selected Xray routes use a separate
native gateway inside the owned WARP tunnel namespace. AmneziaWG device
forwarding keeps its existing separate contract.

Each new TCP connection or UDP destination binding resolves through sealed
libc/NSS with numeric public resolvers. Mixed answers select one admitted
literal; an all-denied answer refuses. Each UDP packet checks that bound
literal again. New associations, destinations and generations resolve anew.
Frontend routing carries no separate GeoIP private-address rule; literal and
named destinations use the same canonical address policy.
A binding stores no raw DNS answer set and never delegates its domain to the
native gateway. Successful TCP acknowledgement does not permit payload replay
to another candidate. Recipient port53 TCP/UDP traffic retains the requested
DNS authority and payload, including records other than A/AAAA.

The canonical policy rejects IPv4 unspecified, private, shared, loopback,
link-local, multicast and reserved ranges and the corresponding IPv6 ranges.
IPv4-mapped IPv6 is normalized. Own public/floating management addresses and
actual or declared SSH/control ports are also denied; own public web services
and remote public SSH remain admissible. A dedicated UID-scoped final nft
output hook checks the actual packet destination after earlier ACCEPT and
admitted rewrites. Unsupported later rewrites, TC/XDP and flow-offload authority
refuse activation. Ordinary host infrastructure UIDs retain their own policy.

The private listeners are `12080` (Xray direct), `12081` (Hysteria direct), and
`12082` (Xray WARP). Native gateways use `12090` (direct) and `12091` (WARP).
Frontend UDP relay pools are `13000–15999`; upstream source pools are
`16000–18999`. Activation requires those ports to be outside the actual
kernel ephemeral range or already fully reserved, and refuses foreign socket
owners. Existing unrelated reservations are preserved.

`transport_egress_secrets` contains five distinct printable ASCII passwords,
32–128 characters: `direct_xray_password`, `direct_hysteria_password`,
`warp_xray_password`, `direct_gateway_password`, and `warp_gateway_password`.
Only enabled paths require their authority. Bootstrap generates all five;
existing encrypted documents must add the enabled fields before convergence.
Disabling `vpn.enable_transport_egress` while a protected frontend is enabled
refuses. Protected transport tags now stage both enabled frontend consumers.
Protected Xray runtime user and group are fixed at `xray`; alternate identities
refuse before host mutation. There is no unguarded compatibility route. The inert cascade classifier endpoint
is fixed at loopback TCP10808; a port override refuses before mutation. Its
dedicated classifier identity shares the final packet destination boundary,
including rejection after earlier destination NAT. The scaffold stays inert.

A UDP association owns separate frontend and upstream tuples. Closure drains
late packets and retires both tuples until 240 seconds of continuous quiet;
activity restarts that quiet interval. Active streams use an accepted-traffic
idle timeout rather than a fixed lifetime. The resource budget includes retired
associations. A fresh normalizer process resets paired native gateways before
new tuples are admitted, and the owned controller recovers enabled frontends.
The controller checks actual process UIDs against the typed packet policy and
restores lost kernel state only after stopping consumers. Legacy units without
a guarded receipt are stopped and disabled before publication; failed initial
upgrades retain no unguarded boot fallback. Failed additions of WARP retire and
mask the owned candidate vendor before removing its isolation files.
This pairing boundary does not add cryptographic identity or replay protection
to an application UDP payload.

Frontend units use immutable verified executable paths. Xray validation selects
the same release executable and bundled assets; read-only validation derives
accepted authority from the loaded unit. Rejected candidates can publish CLI
installer links without changing the accepted frontend executable on restart.
Purely numeric interface names refuse activation because their serialized
interface-index authority would be ambiguous.

WARP vendor isolation requires an actual systemd 257 or newer manager. Older
managers refuse before selected-WARP mutation; direct normalization remains
separate from this vendor requirement. WARP uses the sole owned vendor daemon in `tunnel_only` mode. Its root underlay
is separate from unprivileged gateway plaintext, which requires the verified
TUN ifindex. Missing or recreated tunnel authority blocks plaintext fallback.
Internal credentials and fixed listeners are private; no public SOCKS service
or admin panel is added. Package installation, namespace ownership and resolver
sealing retain their own fail-closed checks.

Local unit, namespace, native frontend and Molecule evidence is source/runtime
validation. A two-TUN packet fixture proves the local adapter path only.
Actual registered vendor TCP/UDP, staging and production acceptance require
separate authorized targets and observed evidence. This change does not deploy
or register a WARP account.
