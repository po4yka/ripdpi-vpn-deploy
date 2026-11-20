# Change: Harden the decoy sites against content clustering and bare-address probes

Task ID: `ANS-1795163402704344`

## Why

An outside probe of two production nodes on 2026-11-20 found that their decoy sites can be linked and told apart from ordinary web sites. Both nodes served byte-identical pages. The nginx-xhttp node presented its certificate and its site to a handshake without SNI. Both nodes refused TLS 1.2, and the nginx-xhttp node offered one key exchange group. The self-steal target ran with the packaged connection limit, which about a thousand idle unauthenticated connections exhaust.

## What Changes

- Both site roles refuse an operator-owned tree that contains a file byte-identical to a file that this repository bundles. No environment label switches the check off.
- Both site roles never publish `.git` or another dot path from the operator-owned tree, except `.well-known`.
- nginx-xhttp adds a default TLS server for each TLS port. It refuses a handshake without SNI or with a foreign name before a certificate is sent, and it answers a request with the right SNI and another Host with the site 404 page.
- Every TLS server of both roles accepts TLS 1.2 and TLS 1.3 with ECDHE ciphers and the groups X25519, prime256v1 and secp384r1.
- The self-steal role raises `worker_connections` and `worker_rlimit_nofile` in the main nginx configuration with a validated in-place edit and a reload.
- BREAKING: the self-steal role refuses a certificate with fewer than 30 days left (variable `reality_self_steal_min_cert_lifetime_days`); the limit was 7 days.
- BREAKING: an operator-owned tree made by `make public-site-render` is refused until its bundled static files (`404.html`, `assets/site.css`, `favicon.svg`, `logo.svg`) are replaced.
- The self-steal role gains an opt-in TCP/80 redirect (`reality_self_steal_http_redirect`, default off) that it refuses until TCP/80 is in the public listener contract.
- The XHTTP locations keep idle streams for one hour and answer more upstream statuses with the site 404. The alias redirect server carries the shared TLS policy and an HSTS header. The ACME HTTP server answers a missing challenge with the site 404. The routing-list base URL omits port 443.

## Capabilities

### New Capabilities

- `ansible/decoy-site-probe-hardening`: what the decoy sites of the nginx-xhttp and reality-self-steal roles show to an outside probe, and which operator-owned content the roles refuse.

### Modified Capabilities

- None.

## Impact

- Ansible: `ansible/roles/reality-self-steal/`, the site, ACME, enable and routing-list files of `ansible/roles/nginx-xhttp/`.
- Operators: the next production deploy fails until each node has its own site content and, for self-steal, a certificate with 30 days left.
- Not in this change: the Terraform listener contract and the firewall for TCP/80 on a self-steal-only node, the IPv6 listener of Xray, and a content generator that gives each node distinct pages.
