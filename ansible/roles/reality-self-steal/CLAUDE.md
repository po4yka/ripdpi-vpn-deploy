# role: reality-self-steal — owned loopback TLS target for P0

## Design decisions

**Same-node self-steal** — Xray keeps public TCP/443 and forwards unauthenticated REALITY handshakes to an nginx TLS 1.3 + H2 site on `127.0.0.1:8443`. The target certificate and `xray.server_names` must describe the same operator-owned hostname.

**No public listener** — nginx binds only the literal IPv4 loopback address. The role does not add TCP/80, wildcard, or IPv6 listeners and therefore does not change the Terraform public-listener contract.

**Explicit lifecycle** — the role always participates in a normal site play. Enabled mode configures the target; disabled mode removes its nginx config, certificate, and site data so a stale private listener cannot survive a rollback.

## What's done well

- The role fails before package or file changes when REALITY, target, SNI, loopback, or port contracts disagree.
- Certificate SAN, remaining lifetime, and public-key match are validated before nginx activation.
- Certificate and key are activated together through one immutable release symlink, so an interrupted rotation cannot expose a mixed pair.
- The private key is mode `0600`; secret-bearing copy/template tasks suppress logs and diffs.
- Molecule covers live TLS/H2 site behavior, private binding, normal 404 responses, wrong-SAN and mismatched-key rejection without active-certificate corruption, idempotence, and interrupted disable cleanup.

## Pitfalls

- Enabling the role without first changing `xray.target` to the exact loopback listener is intentionally rejected.
- `server_names` must contain only the owned certificate hostname; borrowed fallback names defeat the same-ASN design.
- Do not add a public nginx listener here. Public HTTP behavior requires a separate Terraform/firewall/listener-contract change.
- DNS, certificate issuance, client SNI rotation, and filtered-vantage survival remain operator promotion gates outside this role.
