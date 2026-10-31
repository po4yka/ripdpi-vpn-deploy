# Change: Anonymize decoy-site nginx access logs

Task ID: `SEC-1793428368283759`

## Why

Item 9 of the traffic-privacy audit: the public decoy vhosts still write
nginx's default `combined` access log. Every ordinary request to the P1 site
(`vpn-xhttp.access.log`, `vpn-xhttp-fallback.access.log`) and to the loopback
REALITY self-steal site (`reality-self-steal.access.log`) therefore records the
client address, the HTTP user and the user agent, and monitoring keeps fourteen
daily rotations of it. The XHTTP transport locations already log nothing, so
the remaining ledger describes visitors and probers of the decoy, which the
threat model's "the device, not the node" promise does not need and a seized
node should not carry. The parent change `SEC-1793386547449444` left this item
out of scope; it is closed here on its own.

## What Changes

- The nginx-xhttp primary and fallback vhosts and the reality-self-steal vhost log through role-named formats (`vpn_public`, `vpn_self_steal`) that carry no client address, remote user, referer or user agent; the XHTTP, bearer-path and redirect servers stay at `access_log off`. These formats landed on `main` through `SEC-1793428673775693` while this change was in flight; this change keeps them, pins the layout contract and closes the remaining items below.
- The formats keep the `combined` field layout (placeholders for the removed fields), so the watchdog `nginx_403_spike` detector and the probing summary still read the status code from the same position without a parser change; a rendered test runs the detector's `awk` over rendered-format lines, and another loads both site files into one `nginx -t`.
- Monitoring's package-wide nginx logrotate policy keeps seven daily rotations instead of fourteen, the same retention as the Xray policy.
- No BREAKING change: no variable, secret, listener, schema or operator input changes; existing log files keep their names and rotate normally.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `security/traffic-metadata-and-decoy-identity`: adds the decoy access-log anonymity and retention requirements to the capability that the in-flight parent change `sec-1793386547449444-traffic-metadata-and-fleet-fingerprint` introduces (ADDED delta; no main spec exists yet).

## Impact

Ansible role `monitoring` (`logrotate-nginx.j2`) and role notes; the nginx-xhttp and reality-self-steal site templates as already merged; watchdog detector contract covered by a new rendered test; the nginx logrotate golden. No Terraform, cloud-init, secrets, vpnd, client-contract or live-host change. Nodes pick the new format up on their next deployment through the existing compensated nginx transaction.
