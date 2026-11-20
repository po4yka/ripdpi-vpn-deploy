# role: reality-self-steal — owned loopback TLS target for P0

## Design decisions

Operator target hygiene selects `--mode owned-public` with an explicit public endpoint. A remote validator must not use the node-local loopback target as public service evidence; local plumbing and public acceptance stay distinct.

**Memory validation and shared publication authority** — certificate/key/hostname and the seven-day remaining lifetime are validated without controller staging files. Immutable pair, current pointer, vhost and owned asset/credential removals pass through the existing serialized nginx transaction; no controller deletes another invocation's stage. Failed validation/activation retains compensated prior authority. Empty owned directory scaffolding is retained rather than recursively deleting a concurrent writer's namespace. The shared validator accepts a lifetime policy of seven days at most, so the role's own floor (`reality_self_steal_min_cert_lifetime_days`, default 30, which leaves time for an off-node renewal) is a separate `openssl x509 -checkend` task. Check mode validates available TLS tooling and predicts publication without installing credentials. The role does not renew the certificate; `make renew-self-steal-cert` reissues it off-node into a new SOPS document for a reviewed deploy. The observability health adapter receives only `current/fullchain.pem` through `LoadCredential` and reports its expiry under `role="reality-self-steal"`.

**Same-node self-steal** — Xray keeps public TCP/443 and forwards unauthenticated REALITY handshakes to an nginx TLS + H2 site on `127.0.0.1:8443`. The site accepts TLS 1.2 and 1.3 with the groups X25519 (first, the only one REALITY clients offer), prime256v1 and secp384r1, because a site that accepts only TLS 1.3 with one group is rare. The target certificate and `xray.server_names` must describe the same operator-owned hostname.

**No public listener by default** — the TLS site binds only the literal IPv4 loopback address. `reality_self_steal_http_redirect` (default false) adds a TCP/80 server that redirects the owned name to HTTPS and answers any other Host with the site 404; nginx-xhttp keeps those servers when it shares the host. The role refuses the option until the public listener contract has TCP/80, so the Terraform and firewall change comes first.

**Connection limits live in `nginx.conf`** — the target holds every unauthenticated TCP/443 connection that Xray forwards. `worker_connections` is valid only in the packaged file's `events` block, so no drop-in can raise it: after its publication the role edits that directive and `worker_rlimit_nofile` (twice `reality_self_steal_worker_connections`) in place, validates the file with `nginx -t -c`, and reloads nginx through its handler. The file is deliberately not a transaction path: every nginx publisher shares it, the site journal refuses a declared path that exists for an owner without a receipt, and a receipt would refuse every later package or operator edit. Disabling the role leaves the raised limits.

**Operator-owned site on production** — `reality_self_steal_public_site_dir` names a controller-local site bundle whose `site/` directory holds the tree (at least `index.html` and `404.html`, regular files and directories only). When the `public-site` role has published the bundle's archive, the vhost root is `/var/lib/public-site/<digest>/current`, the same generation that nginx-xhttp serves for the same bundle. The role reads it on the controller and publishes it in the same nginx transaction, with the bundled pages it does not provide declared absent. A production host refuses an empty variable before the role changes the host (earlier roles of a site run have already converged), because the three bundled pages are public and identical on every node. Non-production hosts keep the bundled site. Under every label, `ansible/roles/reality-self-steal/tasks/decoy-content.yml` (shared with nginx-xhttp) refuses a tree with a file byte-identical to a file bundled by either role. A role sees one host, so it cannot compare the trees of two nodes; distinct content for each node stays an operator duty. Dot paths of the tree other than `.well-known` are never published, because the tree is often a checkout with `.git`. The contract copies `nginx_xhttp_public_site_dir`; the two variables stay separate because the two roles can serve different names. Inside a site deploy the nginx site journal admits only declared paths, so `playbooks/tasks/transport-ingress-begin.yml` reads the same tree and declares each of its files; a standalone role run has no journal and cannot show a missing declaration.

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
- Do not add another public nginx listener here, and do not enable the TCP/80 option before the Terraform/firewall/listener-contract change.
- The loopback site has no default server that refuses a foreign SNI: REALITY forwards every unauthenticated handshake to it, and a refusal there changes what a probe of TCP/443 sees. Measure it on a live REALITY listener before you add one.
- The loopback site is its own decoy identity. For new decoy surfaces the
  canonical scaffold is `ansible/roles/nginx-xhttp/templates/public-site/`
  plus `ansible/roles/nginx-xhttp/files/public-site/` (pages and served
  assets); copy and re-theme both per identity. Never share exact assets or
  the 404 body across domains — identical content hashes make the fleet
  clusterable.
- A file removed from the operator tree stays on the host until the role is disabled with the variable still set; retirement removes the bundled pages and the files of the current tree, and keeps empty directories.
- DNS, certificate issuance, client SNI rotation, and filtered-vantage survival remain operator promotion gates outside this role.

Remote target validation uses `TARGET_MODE=owned-public`, `PUBLIC_ENDPOINT` and
`OWNED_SNI`; the endpoint is the approved service ingress, not this role's
node-local `127.0.0.1:8443`. That listener and the accepted certificate authority
are never modified by validation. A passing local TLS/HTTP observation does not
approve promotion or establish filtered-path/client survival.
