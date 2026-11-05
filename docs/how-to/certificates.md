# Certificate preflight and public HTTPS renewal

> **Status:** Current · **Type:** how-to · **Tier:** — · **Reviewed:** 2026-11-03

`make check-certs` validates the certificate material for the selected runtime profile. The check requires a DNS SAN for the configured TLS name, current validity, at least 14 days before expiry, a matching private key, TLS server purpose, and a chain to the operator's trusted CA store. A matching common name does not replace a DNS SAN. Wildcards must cover one complete leftmost label.

Put the leaf first in `cert_pem`, then all required intermediate certificates. A root in the supplied bundle does not establish trust. OpenSSL uses its normal operator trust store; `SSL_CERT_FILE` and `SSL_CERT_DIR` can select a controlled local trust store for a direct check. Do not trust the supplied leaf to make an issuance check pass. The deployment controllers use a closed environment and the installed operator trust store.

The check includes only enabled nginx-XHTTP, Hysteria, Naive, and REALITY self-steal authorities. It also checks a distinct enabled nginx fallback name with its own certificate and key. Hysteria uses its explicit `server_name`, then its ECH inner name, then the nginx name. A disabled Naive transport does not require a `naive_secrets` block. A subscription-only profile has no manually supplied transport certificate requirement; ACME issuance is a separate gate.

The deployment controller checks each selected host with the same ordered canonical variables, host metadata, secrets, and overrides used by the runtime playbook. Backup configuration uses its own approved variable order. These controllers retain an immutable private input snapshot during the check.

Make preflight and `make check-certs` use the generated inventory when it exists and honor `ANSIBLE_LIMIT`. They resolve canonical profile membership locally; they do not connect to a host. A mixed selection checks each profile separately. Without an inventory, the standalone check uses canonical `all` and `vpn` defaults plus the supplied secrets. `COHORTS=<cohort>` selects one canonical cohort for that standalone check. Multiple distinct cohorts need an inventory or the exact ordered variable contract.

For a direct script call, `VPN_CERT_VARS_FILES` is a JSON array of ordered variable file paths, including the supplied `VPN_SECRETS_FILE`. Later files replace top-level variables, as the deployment loader does. An explicit list selects the complete context; do not omit host metadata or approved overrides. Diagnostics name the check category and do not print certificate, key, or host values. This source preflight does not prove that a live endpoint serves the same chain or negotiates the expected TLS and ALPN settings.

## REALITY self-steal renewal

The P0 node exposes no public HTTP listener, so the self-steal pair is issued off-node with an ACME DNS-01 challenge on the Vultr zone. Run `sops exec-env <DNS env authority> 'make renew-self-steal-cert SELF_STEAL_SOPS_FILE=<P0 SOPS>'`, where the authority holds only `VULTR_API_KEY`. The target reads the current values through the `make decrypt` gate, removes them with `make clean` on every exit, and does nothing while more than 30 days remain. A second run waits on no lock: it refuses with `renewal-in-progress`. When the pair is due, the target requires the pinned lego release, issues a new pair for `reality_self_steal.server_name` and checks the SAN, key match and a lifetime of at least 40 days. It then writes the pair into a new `<document>-self-steal-renewed-<date>.<extension>` next to the source and deletes the issued key from disk; the source document is not changed. While such a renewed document exists, later runs report `awaiting-deploy` instead of issuing again. A hostname shared with the nginx-XHTTP frontend is refused, because both roles must carry the same pair. The DNS API key exists only in that process environment, and output reports categories, never values.

The command does not deploy. Review the new document as the runtime authority, run the P0 dry-run and deploy, make it the new source, and record it in the private catalog; the next renewal then starts from it. Set `SELF_STEAL_SOPS_FILE` and `SELF_STEAL_DNS_ENV_FILE` (absolute paths) for `make install-operator-crons` to run the check daily; a macOS notification reports a renewal or a refusal.

## Managed public HTTPS

The public site's ACME mode and a supplied certificate pair are separate paths. Select `nginx_xhttp.acme` only for the reviewed owned names. Terraform owns DNS; the nginx role owns HTTP-01 ingress and the guarded publication of the issued certificate pair. Keep HTTP/80 available for the selected challenge and the ordinary redirect. A successful DNS lookup is not issuance or live TLS proof.

After accepted site publication, `vpn-public-tls.timer` runs the renewal coordinator. It uses the same transaction lock as application publication and refuses an open ingress journal. Candidate nginx checks and certificate publication retain rollback; a failed renewal must not replace the working pair. Do not replace this path with an unreviewed certbot cron job or edit the live certificate symlinks by hand.

For an authorized live check, inspect the selected host's timer and last service result without printing key material. Check both the primary name and every served alias from outside the host: DNS, hostname, trust chain, validity, expected content and HTTP-to-HTTPS redirect. Record the next expiry and renewal result separately. A timer being enabled does not prove that an online renewal has succeeded. The [deployment snapshot](../reference/deployment-status.md) records the last observed public certificate, not a promise of future renewal.

Hysteria native ACME has its own cache and restore admission. Follow [the restore guide](restore.md#path-b--restore-from-restic-snapshot); copying a cache does not prove that its account can renew online. Supplied certificate pairs remain the operator's renewal responsibility.
