# REALITY active-target ASN monitoring

`make validate-target` is a point-in-time hygiene check. A target that passed it can later become unsafe when the filtered path begins dropping traffic associated with one of the target's hosting prefixes. `make monitor-reality-target` closes that gap with an observed-path signal; it is not a global ASN reputation service and does not contain a permanent ASN denylist.

## Signal and vantage

Run the monitor from a filtered client path, never from the VPN server or an unfiltered operator workstation. The required `VANTAGE` value is a technical cohort label using letters, digits, dot, underscore, or hyphen; do not use carrier, operator, or geographic names. Each run decrypts the active target in a protected temporary file, resolves every IPv4/IPv6 address, maps each address to its ASN and prefix through `scripts/probe-asn.sh`, and checks every configured SNI for TLS 1.3, H2 ALPN, certificate SAN coverage, and an HTTPS response. HTTP status is recorded only as reachability, so a real WAF response does not become a false packet-drop signal.

The recurring JSON output and local state omit the target hostname, configured SNI values, ASN organization, country, and alert credentials. State lives at `${XDG_STATE_HOME:-$HOME/.local/state}/vpn-deploy/reality-target-monitor/<ENV>.json` with mode `0600`.

## Run and schedule

Run one observation manually after the point-in-time preflight:

```sh
make validate-target
make monitor-reality-target VANTAGE=filtered-cohort-a
```

The first healthy observation establishes the accepted ASN/prefix baseline. Any reachability failure, indeterminate measurement, or ASN/prefix change is unhealthy. The first unhealthy UTC day is recorded; an unhealthy observation on the next UTC day sends a high-priority ntfy alert using `watchdog_secrets`, and later unhealthy UTC days send one reminder per day until the signal recovers or the operator acknowledges a healthy metadata change. Repeated manual runs on the same UTC day update the report without advancing the strike count or sending extra reminders.

Install the daily job on the filtered probe host by passing the same technical label:

```sh
make install-operator-crons REALITY_TARGET_VANTAGE=filtered-cohort-a
```

Without `REALITY_TARGET_VANTAGE`, the installer leaves the monitor out of the managed cron block and reports that it was skipped.

## Incident response

When alerted, confirm the result from a second filtered vantage and inspect the technical ASN/prefix and reason-code changes. Do not infer that every endpoint in an ASN is globally unsafe from a single observation. If healthy DNS movement explains the change, acknowledge the current baseline explicitly:

```sh
make monitor-reality-target VANTAGE=filtered-cohort-a ACCEPT_BASELINE=1
```

Acknowledgement is refused while target-path health is not `ok`. If the target remains unsafe, use the existing `scan-targets`, `validate-target`, and filtered-vantage survival workflow to evaluate a replacement, then deploy it through the normal reviewed process. The monitor never edits SOPS, invokes deployment or promotion commands, or switches the target.

## Verdicts

- `ok` — every resolved address and configured SNI passed the path checks and the ASN/prefix sets match the accepted baseline.
- `blocked` — at least one TLS, H2, SAN, or HTTPS reachability check failed.
- `unknown` — DNS or ASN lookup was indeterminate, or a healthy target's ASN/prefix set changed and awaits operator review.
- `error` — local configuration or a required tool prevented the monitor from running.

## Bounded identity and client validation

`validate-target` emits a redacted JSON observation. `SERVER_NAMES` accepts commas
and whitespace; ASCII DNS names are lowercased, one terminal root dot is removed,
and duplicates retain first occurrence. Empty comma components, malformed labels,
more than 16 names, and more than 16 resolved addresses refuse before probing the
pair set. Every configured name is used as the actual TLS SNI and HTTP identity;
TLS trust, SAN hostname verification, TLS 1.3 and H2 ALPN must pass. Wildcards cover
one label only; the certificate Common Name cannot substitute for SAN.

`PROBE_TIMEOUT` defaults to 12 seconds and `VALIDATION_TIMEOUT` to 120 seconds
(maximum 600 each). One monotonic aggregate deadline covers the entire address/name
set, including DNS and metadata. Owned subprocess sessions are reclaimed after
success, failure, cancellation and timeout. The monitor includes secret acquisition
and alert delivery within its run deadline. A partial or timed-out observation
cannot establish a healthy baseline. Metadata failure remains indeterminate.

For owned self-steal, set these environment variables for either caller:

```sh
export TARGET_MODE=owned-public
export PUBLIC_ENDPOINT=service.example:443
export OWNED_SNI=owned.example
```

The approved public service endpoint is supplied explicitly; `xray.target` remains
node-local plumbing. The normalized configured name list must contain exactly the
owned SNI. A remote probe refuses any loopback or unspecified resolved address.
Borrowed targets use the default `TARGET_MODE=borrowed`. Neither mode selects a
replacement, publishes credentials, changes certificates, or invokes deployment.

Ordinary curl reports HTTP/TLS hygiene. To request a separate browser-shaped
ClientHello observation, provide `REALITY_CLIENT_DIR` containing the upstream
curl-impersonate **0.6.1** `curl-impersonate-chrome` binary and `curl_chrome116`
profile. Exact supported artifact hashes are embedded in the validator; unknown
or changed bytes refuse. No runtime acquisition occurs. The engine must complete
an actual HTTPS exchange to every admitted address/name pair. This is the named
Chrome116 profile, not a claim about current Chrome versions. The client check
has its own pass/fail/unavailable field; it cannot turn HTTP hygiene into browser
compatibility. `REALITY_CA_FILE` optionally supplies an explicit trust bundle.

`make test-reality-target-validation` runs all portable and native cases without
skips. The native lane requires `REALITY_TEST_CLIENT_DIR` and an isolated service
network with `REALITY_TEST_BIND=0.0.0.0` and `REALITY_TEST_PUBLIC_IP` identifying that
fixture's ingress. These are fixture controls, not production acceptance.

Promotion still requires separately authorized target ownership, a supported real
recipient handshake, approved filtered-vantage evidence and authenticated rollback
to the accepted target. Local hygiene, this named client profile and an asserted
vantage label do not establish those facts. Runtime pins and PQE HOLD are unchanged.
