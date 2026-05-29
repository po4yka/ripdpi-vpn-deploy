# Delivering Configuration to Clients

How an operator turns a provisioned client into something a user imports in one tap. The first-class target is the RIPDPI Android client; the same artifacts work with any sing-box-compatible client (the RIPDPI-specific extension is ignored by other clients).

## Emitters

| Command | Output | Use |
| --- | --- | --- |
| `make emit-singbox CLIENT=<name>` | sing-box JSON (P0/P1/P2 + selector/urltest) | any sing-box client; the plain subscription payload |
| `make emit-awg CLIENT=<name>` | AmneziaWG `wg-quick` `.conf` | the device-VPN as a standalone file |
| `make emit-bundle CLIENT=<name>` | sing-box JSON **plus** a `ripdpi` extension | one artifact for RIPDPI carrying the whole device config |
| `vpnd share <client>` | recipient page (`index.html` + QR) + bundle | operator-friendly handoff page |

`emit-bundle` is `emit-singbox` plus a top-level `ripdpi` object carrying the AmneziaWG peer and the Hysteria salamander/insecure/port-hop knobs that plain sing-box cannot express. The sing-box document is preserved verbatim, so a non-RIPDPI client can use the same file and simply ignore the `ripdpi` key. The schema is specified in [`RIPDPI-BUNDLE.md`](RIPDPI-BUNDLE.md).

## Delivery channels

- **Recipient page** (`vpnd share`) — leads with an **Add to RIPDPI** card: a `ripdpi://` deep link plus a QR. One tap or scan lands the whole fleet in RIPDPI. Also serves the sing-box import option for other clients.
- **Subscription URL** — `https://<host>:8444/sub/<token>` served by the `subscription-host` role, populated by `scripts/issue-sub-token.sh` (which runs an emitter and installs the payload as `sha256(token)`). Long-lived, rate-limited, and revocable; the client auto-updates it. Run it on a dedicated host via `vpn_subscription_only` (see [`SUBSCRIPTION-HOST-SEPARATION.md`](SUBSCRIPTION-HOST-SEPARATION.md)).
- **One-shot bootstrap** — `https://<host>:8444/bootstrap/<token>`, deleted after the first successful read; for single-use provisioning.

## The `ripdpi://` deep link

The recipient page emits, and the RIPDPI client consumes, this exact contract:

```
ripdpi://import?sub=<percent-encoded https subscription URL>   # enroll + auto-update (preferred)
ripdpi://import?url=<percent-encoded https config or bundle URL>  # one-shot import
```

Targets must be `https`. Point `sub=` at a subscription endpoint that serves the RIPDPI bundle when the client is RIPDPI, so auto-update keeps the device-VPN and Hysteria obfs in sync along with the proxy profiles.

## What each artifact carries

| Capability | `emit-singbox` / `/sub` | `emit-bundle` | `emit-awg` |
| --- | --- | --- | --- |
| P0 REALITY + P1 XHTTP + P2 Hysteria2, with failover | yes | yes | no |
| Background auto-update (via subscription URL) | yes | yes | no |
| Hysteria salamander obfs / insecure / port-hop | no | yes | no |
| AmneziaWG device-VPN | no | yes | yes (standalone) |

## AmneziaWG device-key handoff

`new-client.sh` generates the AmneziaWG device private key, prints it once, and stores only the public key, preshared key, and allowed IPs in SOPS. The key is never written to disk on the server, so no emitter can include it: `emit-awg` writes a `PrivateKey` placeholder and `emit-bundle` sets `private_key_placeholder: true`. Hand the private key to the user over a secure channel at creation time; the RIPDPI client prompts for it after import. Lose it and the only recovery is reissuing the peer (`new-client.sh` + `make rotate-credentials`).

## Rotation, revocation, burned IPs

- **Rotation** — re-emit and re-publish via `issue-sub-token.sh`; subscribed clients pick up new credentials on their next refresh.
- **Revocation** — add the token's `sha256` hex to `subscription.revoked_token_hashes` and re-deploy; the bootstrap service re-reads the revocation list per request.
- **Burned IP (P3)** — recreate the node from git + secrets; clients on the subscription URL follow the new endpoint without manual re-import.

## End-to-end flow

```mermaid
sequenceDiagram
    participant Op as Operator
    participant Em as Emitter (make / vpnd)
    participant Sub as subscription-host
    participant App as RIPDPI client
    Op->>Em: make emit-bundle CLIENT=phone  /  vpnd share phone
    Em-->>Op: bundle JSON + recipient page (ripdpi:// button, QR)
    Op->>Sub: issue-sub-token.sh (publish payload at sha256(token))
    Op->>App: deep link / QR / subscription URL (+ AWG private key out of band)
    App->>Sub: GET /sub/<token> (https)
    Sub-->>App: sing-box JSON (+ ripdpi extension)
    App->>App: import fleet + AmneziaWG; user pastes AWG private key
    Note over App,Sub: client auto-refreshes; rotation and burned-IP follow
```

## See also

- [`RIPDPI-BUNDLE.md`](RIPDPI-BUNDLE.md) — authoritative bundle schema.
- [`SUBSCRIPTION-PLANE.md`](SUBSCRIPTION-PLANE.md) and [`SUBSCRIPTION-HOST-SEPARATION.md`](SUBSCRIPTION-HOST-SEPARATION.md) — subscription delivery.
- [`CLIENT-NOTES.md`](CLIENT-NOTES.md) — client-side bugs and version pins.
- RIPDPI repo `docs/server-integration.md` — the client-side counterpart (how the app imports these artifacts).
