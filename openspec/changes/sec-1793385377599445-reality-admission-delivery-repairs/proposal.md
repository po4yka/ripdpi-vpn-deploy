# Change: Harden REALITY admission and repair client delivery defects

Task ID: `SEC-1793385377599445`

## Why

A protocol support review found six defects in the P0 and client-delivery surfaces:

- REALITY inbounds render no `maxTimeDiff`. Xray treats the absent value as zero and accepts a captured ClientHello at any later time. A replayed hello takes the authenticated REALITY path instead of the borrowed target's handshake, and the encrypted handshake length can then distinguish the node from its target.
- Production Xray pins are only asserted to be non-empty. Upstream marks Xray prereleases with a release flag, not a tag suffix, so a tag-shape check cannot stop an unqualified build from reaching production.
- The watchdog and smoke REALITY clients always send the `chrome` uTLS fingerprint, and the watchdog XHTTP client sends none. They do not verify the fingerprint that recipient profiles actually carry when an operator overrides `xray_utls_fingerprint`.
- `emit-qr.sh --type uri` enrolls a new device and encodes a URI template that still contains `<SERVER_IP>`, `<SNI>` and `<REALITY_PUBLIC_KEY>`. The QR code cannot connect.
- RIPDPI bundles set `topology.split_hop_egress=true` for any host with `enable_split_hop_ingress`. The current split-hop pilot routes only the research probe runtimes through Node B, so the family transports on that host still use the entry IP for egress.
- New XHTTP paths carry 32 random bits. The repository fallback and example path `/app-sync` is public knowledge, yet it is silently accepted and rendered when the secret is absent.

## What Changes

- REALITY inbounds render a bounded `maxTimeDiff`, which defaults to 90 seconds. **BREAKING** for recipient devices whose clock is more than 90 seconds off: they see the borrowed target instead of the tunnel.
- Production deployments refuse any Xray version outside a reviewed production allowlist. The allowlist must contain the release tracker's repository pin.
- The watchdog and smoke REALITY clients, and the watchdog XHTTP client, use the configured recipient uTLS fingerprint.
- `emit-qr.sh --type uri` becomes read-only for an existing device. It derives one complete VLESS+REALITY share URI from the canonical client materializer. **BREAKING**: it no longer enrolls a device; operators use `new-client.sh` for issuance.
- RIPDPI bundle emission keeps `topology.split_hop_egress=false`, because no family transport egresses through Node B.
- `bootstrap-secrets.sh` generates XHTTP paths with 128 random bits. Admission refuses an absent path or the published `/app-sync` value. Existing operator-generated short paths remain valid; rotating them is an operator action.

## Capabilities

### New Capabilities

- `security/reality-admission-delivery-integrity`: replay window, production pin admission, recipient-equivalent probe fingerprints, share URI delivery, bundle topology truthfulness and XHTTP path secrecy.

### Modified Capabilities

- None.

## Impact

- **Ansible:** the `xray` template and defaults, the `xray-runtime` preflight, the `watchdog` probe template and the shared smoke task.
- **Scripts:** `emit-qr.sh`, `client_payload.py` (share URI output and topology), `bootstrap-secrets.sh` and `transport_semantics.py` (path admission).
- **Contracts:** the secrets example, test fixtures, snapshot goldens and the bundle topology documentation. The RIPDPI bundle schema shape is unchanged.
- **Not changed:** Terraform, provider state, live hosts and private secrets. A follow-up deploy is required for the runtime changes to reach existing nodes.
