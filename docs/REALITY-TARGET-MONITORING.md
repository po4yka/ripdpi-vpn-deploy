# REALITY active-target ASN monitoring

`make validate-target` is a point-in-time hygiene check. A target that passed it can later become unsafe when the filtered path begins dropping traffic associated with one of the target's hosting prefixes. `make monitor-reality-target` closes that gap with an observed-path signal; it is not a global ASN reputation service and does not contain a permanent ASN denylist.

## Signal and vantage

Run the monitor from a filtered client path, never from the VPN server or an unfiltered operator workstation. The required `VANTAGE` value is a technical cohort label using letters, digits, dot, underscore, or hyphen; do not use carrier, operator, or geographic names. Each run decrypts the active target in a protected temporary file, resolves every IPv4 address, maps each address to its ASN and prefix through `scripts/probe-asn.sh`, and checks every configured SNI for TLS 1.3, H2 ALPN, certificate SAN coverage, and an HTTPS response. HTTP status is recorded only as reachability, so a real WAF response does not become a false packet-drop signal.

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
