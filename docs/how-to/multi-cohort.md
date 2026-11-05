# Multi-cohort host

> **Status:** Current · **Type:** how-to · **Tier:** — · **Reviewed:** 2026-11-05

A single VPS can serve several cohorts at once, each with its own port, flow mode, finalmask setting, and client list, while sharing one REALITY identity (target + server_names + private key).

## When to use this

A typical mix:

| Cohort | Port | Flow mode | Why |
|---|---|---|---|
| `tls-cap-mux` | 443 | `mux` | The access network caps concurrent TLS sessions (~12); mux keeps one session |
| `alt-port-vision` | 8444 | `vision` | TCP/443 is policed on this path; the same flow on another port is not |
| `unpoliced-vision` | 9443 | `vision` | Default behaviour, no policing observed |

A single REALITY identity is what DPI active probing measures. Adding more cohort ports does not multiply your fingerprint surface — every inbound mimics the same donor site.

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
    - name: tls-cap-mux
      port: 443
      flow_mode: mux
      finalmask: true
      clients: [phone, watchdog]
    - name: alt-port-vision
      port: 8444
      flow_mode: vision
      finalmask: false
      clients: [tablet, watchdog]
    - name: unpoliced-vision
      port: 9443
      flow_mode: vision
      finalmask: false
      clients: [laptop, watchdog]
```

Properties:

* `xray.cohorts` is optional. When empty / missing, the role renders a single VLESS+REALITY inbound on `xray_port` with `vpn.xray_flow_mode`, identical to single-cohort behaviour (no diff in the generated config.json).
* The `clients` list under each cohort is **names** that reference the global `xray.clients` array. UUIDs and shortIds stay in one place.
* `flow_mode` is `vision` or `mux`. It must name a shape in `p0_reality_shapes` (`ansible/group_vars/all.yml`); the role refuses an unknown shape. `flow_mode` per cohort overrides the profile default (`vpn.xray_flow_mode`, then `p0_reality_flow_mode`). The `finalmask` default comes from the selected shape (`p0_reality_shapes.<shape>.finalmask`).
* All cohorts share `xray.target`, `xray.server_names`, and `xray.reality_private_key` — one REALITY identity, multiple ports.
* The dedicated probe client must be listed in every cohort, so the on-node authenticated probe covers every REALITY listener. Its name is `watchdog.reality_probe_client` (default `watchdog`). The watchdog role fails the deployment when a cohort does not list it (`ansible/roles/watchdog/tasks/enable.yml`).

## Firewall

The `firewall` role opens every cohort port. Without cohorts, it opens `xray_port` (`ansible/group_vars/all.yml`).

## Client emit (cohort-aware)

`scripts/emit-singbox.sh` is a thin wrapper over `scripts/client_payload.py`, which is multi-cohort aware for REALITY. When `xray.cohorts` is non-empty, it emits one REALITY outbound per cohort that lists the requested client, using that cohort's `port` and `flow_mode`. When `xray.cohorts` is empty or missing, it emits one outbound on `xray_port` with `vpn.xray_flow_mode`.

For multi-host bundles, pass `HOSTS=provider:env,...` and optionally `COHORTS=name,...`. When `COHORTS` is omitted, the emitter can infer a cohort from `ansible/inventory/generated.ini` by matching the Terraform `server_hostname` to a `vpn-<cohort>` inventory group. If a client is not listed in any configured cohort, the emitter fails instead of silently producing a bundle with the wrong port.

## Subscription bundling

If you use `subscription-host`, each device's payload should include the cohort's port. The bootstrap helper `scripts/issue-bootstrap.sh` calls `emit-singbox.sh` underneath, so bootstrap payloads inherit the same cohort-specific REALITY outbounds.

## Not multi-cohort (intentionally)

* **Multiple XHTTP localhost inbounds.** The XHTTP localhost inbound is behind nginx, which has a single public port. Keeping XHTTP as a single inbound is the right scope — splitting it gains nothing.
* **Multiple REALITY identities (target + private key) on one host.** REALITY's threat model assumes one TLS identity per IP; multiple identities on one IP would itself become a fingerprint.
* **Per-cohort xray binaries / processes.** Xray supports multiple inbounds in one config natively; running N processes for N cohorts is operational overhead with no compensating gain.
