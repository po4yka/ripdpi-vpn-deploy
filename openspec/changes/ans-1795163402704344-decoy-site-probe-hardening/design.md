## Context

Findings of the 2026-11-20 outside probe, checked against the source at 5f82a695. The production gate for the bundled site already tests `env` and the Terraform-derived `vpn_build_environment`, so a workspace name does not bypass it. The remaining gap is content: `make public-site-render` copies the bundled static files into every operator tree, and one tree can serve two nodes.

## Goals / Non-Goals

- Goal: refuse content that the repository can prove is shared, without a label.
- Goal: make the TLS and HTTP answers of both sites match an ordinary nginx site.
- Non-goal: generate distinct content for each node. A role sees one host and one workspace; it cannot compare two nodes.
- Non-goal: change the Terraform listener contract or the firewall.

## Decisions

- **Hash gate, not a label.** One shared task file compares sha256 checksums of the operator tree with both roles' bundled files on the controller. It runs for every environment, so a staging rehearsal fails the same way as production.
- **Reject the handshake instead of a second certificate.** `ssl_reject_handshake` needs no key material and no new secret. A self-signed default certificate would need generated state and would itself be a fleet-wide fingerprint. Strict-SNI refusal is ordinary nginx behaviour.
- **One TLS policy macro.** nginx negotiates the protocol version and session cache from the default server of a listener, so the default server must carry the same policy as the named servers.
- **TLS 1.2 and three groups.** A site that accepts only TLS 1.3 with X25519 is rare. X25519 stays first because REALITY clients offer only that group. Hybrid post-quantum groups are not listed: OpenSSL 3.0 on Ubuntu 24.04 refuses the name.
- **Edit `nginx.conf` in place, outside the transaction.** `worker_connections` is valid only in the `events` block of the packaged file, so no drop-in can raise it. The role edits the two directives with `nginx -t -c` validation and reloads nginx. Review rejected the first design, a transaction row: the site journal refuses a declared path that exists for an owner without a receipt, so every host with nginx and without a self-steal receipt would fail at begin, and a receipt would then refuse each later package or operator edit of the shared file.
- **No default TLS server on the loopback self-steal target.** REALITY forwards every unauthenticated handshake to the target, and a refusal there would change what a probe of TCP/443 sees for a foreign SNI. That decision needs a live REALITY measurement first.
- **TCP/80 on a self-steal node is opt-in.** A closed TCP/80 beside an HTTPS site is unusual, but the listener needs a contract and firewall change that another owner makes.

## Contracts and ownership

- The shared TLS validator of the subscription-host role accepts a lifetime policy of seven days at most. The self-steal role keeps that call and adds its own `openssl x509 -checkend` task for the 30-day floor, so the shared script does not change.

- `/etc/nginx/nginx.conf` stays outside every transaction owner; the declared ingress paths do not change.
- `decoy-content.yml` lives in the self-steal role and nginx-xhttp includes it by path, as self-steal already includes the nginx-xhttp transaction.

## Risks / Trade-offs

- A deploy of a node whose tree came from `make public-site-render` fails until the operator replaces the bundled static files. This is the intended refusal.
- A deploy with a self-steal certificate between 7 and 30 days from expiry now fails. The variable lowers the limit for an emergency recreation.
- A client that connects to the nginx-xhttp port without SNI now fails. No role-managed probe does this.
- Idle XHTTP streams hold a connection for up to one hour; only authenticated streams reach the upstream.

## Migration Plan

1. Replace the bundled static files in each node's site tree and give each node its own pages.
2. Renew a self-steal certificate that has fewer than 30 days left.
3. Deploy through the ordinary dry-run and deploy transaction; the site transaction restores the previous files on failure.
