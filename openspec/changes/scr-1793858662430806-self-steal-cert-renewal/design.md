# Design

The check reads only the public certificate from the P0 document and returns when more than 30 days remain. Issuance requires lego 5.6.0 exactly. lego performs DNS-01 against the Vultr zone through the authoritative resolver, with a 10-minute propagation wait, because Vultr publishes records slowly. The DNS API key comes from its own SOPS document and reaches lego only through the environment.

The issued pair must name exactly `reality_self_steal.server_name`, the key must match the certificate, and at least 40 days must remain, which is below the shorter Let's Encrypt lifetimes that are planned. The pair is written with `sops set` into a copy of the source. The copy keeps the extension that sops reads the format from, and a hard link publishes it atomically under a dated name. The plaintext files that lego issued are deleted on success and on failure.

A hostname shared with the nginx-XHTTP frontend is refused, because the self-steal role requires both roles to carry the same pair. While a renewed document exists, the job reports `awaiting-deploy`. The renewed document becomes the source only through the operator's reviewed deploy. Unattended production deploys stay out of scope by repository rule.
