# Multi-cohort host

A single VPS can serve several cohorts at once, each with its own port,
flow mode, finalmask setting, and client list, while sharing one REALITY
identity (target + server_names + private key).

## When to use this

A typical mix:

| Cohort | Port | Flow mode | Why |
|---|---|---|---|
| `home-isp` | 443 | `mux` | Avoid the ~12-concurrent-TLS rule on RU home ISPs (`tls-policing-home-isps`) |
| `mobile`   | 8444 | `vision` | TCP/443 elsewhere on the IP is policed; mobile is fine on a different port |
| `foreign`  | 9443 | `vision` | Default behaviour, no policing observed |

A single REALITY identity is what TSPU active-probing measures. Adding
more cohort ports does not multiply your fingerprint surface — every
inbound mimics the same donor site.

## Schema

In `prod.secrets.sops.yaml` (alongside the existing `xray.clients`):

```yaml
xray:
  # existing top-level keys (version, sha256, target, server_names,
  # reality_*, xhttp_path, clients) are unchanged.

  clients:
    - { name: phone,   uuid: …, short_id: … }
    - { name: laptop,  uuid: …, short_id: … }
    - { name: tablet,  uuid: …, short_id: … }
    - { name: watchdog, uuid: …, short_id: … }

  cohorts:
    - name: home-isp
      port: 443
      flow_mode: mux
      finalmask: true
      clients: [phone, watchdog]
    - name: mobile
      port: 8444
      flow_mode: vision
      finalmask: false
      clients: [tablet, watchdog]
    - name: foreign
      port: 9443
      flow_mode: vision
      finalmask: false
      clients: [laptop, watchdog]
```

Properties:

* `xray.cohorts` is optional. When empty / missing, the role renders a
  single VLESS+REALITY inbound on `xray_port` with `vpn.xray_flow_mode`,
  identical to single-cohort behaviour (no diff in the generated
  config.json).
* The `clients` list under each cohort is **names** that reference the
  global `xray.clients` array. UUIDs and shortIds stay in one place.
* `flow_mode` and `finalmask` per cohort override the global toggles.
* All cohorts share `xray.target`, `xray.server_names`, and
  `xray.reality_private_key` — one REALITY identity, multiple ports.
* The dedicated `watchdog` client must be listed in every cohort. The role
  refuses to deploy a cohort that the on-node authenticated probe cannot
  exercise.

## Firewall

The `firewall` role automatically opens every cohort port. The single-
port fallback uses `xray_port` (group_vars) as before.

## Client emit (cohort-aware)

`scripts/emit-singbox.sh` is multi-cohort aware for REALITY. When
`xray.cohorts` is non-empty, it emits one REALITY outbound per cohort
that lists the requested client, using that cohort's `port` and
`flow_mode`. When `xray.cohorts` is empty or missing, it keeps the
legacy single-outbound behavior on `xray_port` with
`vpn.xray_flow_mode`.

For multi-host bundles, pass `HOSTS=provider:env,...` and optionally
`COHORTS=name,...`. When `COHORTS` is omitted, the emitter can infer a
cohort from `ansible/inventory/generated.ini` by matching the Terraform
`server_hostname` to a `vpn-<cohort>` inventory group. If a client is
not listed in any configured cohort, the emitter fails instead of
silently producing a bundle with the wrong port.

## Subscription bundling

If you use `subscription-host`, each device's payload should include
the cohort's port. The bootstrap helper `scripts/issue-bootstrap.sh`
calls `emit-singbox.sh` underneath, so bootstrap payloads inherit the
same cohort-specific REALITY outbounds.

## Not multi-cohort (intentionally)

* **Multiple XHTTP localhost inbounds.** The XHTTP localhost inbound
  is behind nginx, which has a single public port. Keeping XHTTP as a
  single inbound is the right scope — splitting it gains nothing.
* **Multiple REALITY identities (target + private key) on one host.**
  REALITY's threat model assumes one TLS identity per IP; multiple
  identities on one IP would itself become a fingerprint.
* **Per-cohort xray binaries / processes.** Xray supports multiple
  inbounds in one config natively; running N processes for N cohorts
  is operational overhead with no compensating gain.
