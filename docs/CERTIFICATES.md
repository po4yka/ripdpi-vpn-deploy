# Certificate preflight

`make check-certs` validates the certificate material for the selected runtime
profile. The check requires a DNS SAN for the configured TLS name, current
validity, at least 14 days before expiry, a matching private key, TLS server
purpose, and a chain to the operator's trusted CA store. A matching common name
does not replace a DNS SAN. Wildcards must cover one complete leftmost label.

Put the leaf first in `cert_pem`, then all required intermediate certificates.
A root in the supplied bundle does not establish trust. OpenSSL uses its normal
operator trust store; `SSL_CERT_FILE` and `SSL_CERT_DIR` can select a controlled
local trust store for a direct check. Do not trust the supplied leaf to make an
issuance check pass. The deployment controllers use a closed environment and
the installed operator trust store.

The check includes only enabled nginx-XHTTP, Hysteria, Naive, and REALITY
self-steal authorities. It also checks a distinct enabled nginx fallback name
with its own certificate and key. Hysteria uses its explicit `server_name`, then
its ECH inner name, then the nginx name. A disabled Naive transport does not
require a `naive_secrets` block. A subscription-only profile has no manually
supplied transport certificate requirement; ACME issuance is a separate gate.

The deployment controller checks each selected host with the same ordered
canonical variables, host metadata, secrets, and overrides used by the runtime
playbook. Backup configuration uses its own approved variable order. These
controllers retain an immutable private input snapshot during the check.

Make preflight and `make check-certs` use the generated inventory when it exists
and honor `ANSIBLE_LIMIT`. They resolve canonical profile membership locally;
they do not connect to a host. A mixed selection checks each profile separately.
Without an inventory, the standalone check uses canonical `all` and `vpn`
defaults plus the supplied secrets. `COHORTS=<cohort>` selects one canonical
cohort for that standalone check. Multiple distinct cohorts need an inventory
or the exact ordered variable contract.

For a direct script call, `VPN_CERT_VARS_FILES` is a JSON array of ordered
variable file paths, including the supplied `VPN_SECRETS_FILE`. Later files
replace top-level variables, as the deployment loader does. An explicit list
selects the complete context; do not omit host metadata or approved overrides.
Diagnostics name the check category and do not print certificate, key, or host
values. This source preflight does not prove that a live endpoint serves the
same chain or negotiates the expected TLS and ALPN settings.
