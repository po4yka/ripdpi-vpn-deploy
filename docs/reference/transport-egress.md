# Recipient destination boundary

> **Status:** Current · **Type:** reference · **Tier:** — · **Reviewed:** 2026-10-22

P0 REALITY, P1 XHTTP and P2 Hysteria recipient TCP/UDP traffic uses an
unprivileged metadata normalizer, followed by the same pinned native Xray
runtime as a literal-only gateway. WARP-selected Xray routes use a separate
native gateway inside the owned WARP tunnel namespace. AmneziaWG device
forwarding keeps its existing separate contract.

Each new TCP connection or UDP destination binding resolves through sealed
libc/NSS against the direct gateway's loopback forwarder (`127.0.0.2:53`),
which answers A/AAAA queries over DNS-over-HTTPS and drops every other type;
only the DNS-Morph profile, which claims UDP/53 on every address, keeps
numeric plaintext resolvers. An all-denied answer refuses. TCP uses
one immutable set of admitted literals, sorted within each family and
interleaved IPv4-first. It tries at most eight candidates with at most two
concurrent authenticated gateway controls and a 250 ms start stagger. One
connection deadline covers all attempts after resolution; per-attempt budgets
leave time for later candidates when earlier controls stall. Each literal is
checked again before its CONNECT request and before selecting a winner.
All losing controls close before application bytes reach the winner. A later
payload failure never selects another candidate or replays application bytes.

UDP keeps one stable admitted literal per destination binding and checks that
literal on every packet. New associations, destinations and generations resolve
anew; TCP candidates never trigger a second DNS lookup. Frontend routing carries
no separate GeoIP private-address rule: literal and named destinations use the
same canonical address policy. A binding stores no raw DNS answer set and never
delegates its domain to the native gateway. Recipient port53 TCP/UDP traffic
retains the requested DNS authority and payload, including records other than
A/AAAA.

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


## Protected deployment and recovery

Protected site staging has one compensation owner. It snapshots both ingress owners before publication, keeps frontend staging inside a rescued block, and closes the transaction before unrelated roles run. Failure quiesces owned candidate processes, restores and validates accepted Nginx authority, then resumes accepted egress/frontends. Standalone frontend roles retain their own rollback.

Nginx adoption receipts now require schema 2 ownership and bounded digest-only path witnesses; ordinary interrupted publication also retains the prior receipt in its private journal. Legacy receipts/journals do not contain sufficient ownership evidence and refuse before mutation. This is a contract break: recreate those disposable nodes or perform separately authorized, verified authority reconciliation before rollout. No compatibility inference or automatic migration exists.

Watchdog recovery for Xray and Hysteria goes through the running root controller. A successful request changes only its selected frontend PID; mappings and the other frontend retain their PIDs. The requester checks actual root controller identity, private receipt binding and current readiness under one deadline. Unrelated drift cannot count as targeted recovery, and failure has no direct-restart fallback. The watchdog service budget includes both enabled protected requests at the maximum supported timeout.

Node-local masquerade resolution is scoped to Hysteria with a private read-only hosts bind that participates in frontend rollback. Nginx never changes global `/etc/hosts`; public site pages/assets share its typed publication and compensation. Host-NSS verification remains separate from independently authenticated public DNS/client acceptance.
