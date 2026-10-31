# role: reality-self-steal — owned loopback TLS target for P0

## Design decisions

Operator target hygiene selects `--mode owned-public` with an explicit public endpoint. A remote validator must not use the node-local loopback target as public service evidence; local plumbing and public acceptance stay distinct.

**Memory validation and shared publication authority** — certificate/key/hostname and the seven-day remaining lifetime are validated without controller staging files. Immutable pair, current pointer, vhost and owned asset/credential removals pass through the existing serialized nginx transaction; no controller deletes another invocation's stage. Failed validation/activation retains compensated prior authority. Empty owned directory scaffolding is retained rather than recursively deleting a concurrent writer's namespace. Check mode validates available TLS tooling and predicts publication without installing credentials.

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

- The loopback site's access log uses the `vpn_self_steal` format (distinct from nginx-xhttp's `vpn_public`: nginx refuses duplicate `log_format` names when both site files load) without `$remote_addr`, referer or user agent; every request there arrives through Xray, so the address would only be the REALITY frontend anyway, but the browser fingerprint of a real visitor must not be retained.

- Enabling the role without first changing `xray.target` to the exact loopback listener is intentionally rejected.
- `server_names` must contain only the owned certificate hostname; borrowed fallback names defeat the same-ASN design.
- A hostname shared with nginx-xhttp must carry the same `cert_pem` in both roles; one name presenting two certificates on two ports is a correlation signal. Distinct names are fine. `make validate-target` in `owned-public` mode reports `owned_name_resolution` (`matches`, `elsewhere`, `unresolved`), the comparison a censor makes before trusting an SNI; promotion requires `matches`. It is reported rather than refused because fixtures cannot own public DNS.
- Do not add a public nginx listener here. Public HTTP behavior requires a separate Terraform/firewall/listener-contract change.
- The loopback site is its own decoy identity. For new decoy surfaces the
  canonical scaffold is `ansible/roles/nginx-xhttp/templates/public-site/`
  plus `ansible/roles/nginx-xhttp/files/public-site/` (pages and served
  assets); copy and re-theme both per identity. Never share exact assets or
  the 404 body across domains — identical content hashes make the fleet
  clusterable.
- DNS, certificate issuance, client SNI rotation, and filtered-vantage survival remain operator promotion gates outside this role.

Remote target validation uses `TARGET_MODE=owned-public`, `PUBLIC_ENDPOINT` and
`OWNED_SNI`; the endpoint is the approved service ingress, not this role's
node-local `127.0.0.1:8443`. That listener and the accepted certificate authority
are never modified by validation. A passing local TLS/HTTP observation does not
approve promotion or establish filtered-path/client survival.
