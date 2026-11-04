# Deployment status — last verified snapshot

> **Status:** Snapshot (2026-11-04) · **Type:** reference · **Tier:** — · **Reviewed:** 2026-11-04

This page records the completed four-host checks at **2026-11-04 05:55 UTC**.
It replaces the 3 November snapshot. It is not a live health report. Later
source changes, deployments, provider changes and credential rotations need
their own checks. Private endpoints, identifiers and secret values remain in
the ignored operator kit. Read its current catalog before an operation.
The later [security-report update](#security-reporting-update-2026-11-04) records
the separate 09:00 UTC audit. It does not refresh the service-wide traffic,
monitoring or recovery acceptance.

## Source and fleet

| Host | Provider | Runtime purpose |
|---|---|---|
| node-a | UpCloud | P0 VLESS + REALITY + Vision |
| node-b | Scaleway | Public HTTPS site, P1 XHTTP and private monitoring collector |
| node-c | Vultr | P2 Hysteria2 and AmneziaWG |
| observer-a | UpCloud | Independent private Uptime Kuma panel and encrypted panel backups |

Hetzner remains a supported provider; no server or volume there was part of
this snapshot. Personal devices and Raspberry Pi do not host the service.
Terraform owns resources and DNS. Tailscale carries management and private
monitoring traffic. Authenticated VPN probes use public service endpoints.

Components have separate source authorities. Do not report one whole-host
revision for the observer or infer deployment from the newest `main` commit.

| Component | Accepted source at this observation |
|---|---|
| VPN core on node-a, node-b and node-c | `71dfdeaa287803edcb9c16deb14f82ffc304ee9f` |
| Node agents, collector and Kuma application | `1fe52a17681115fc8d1f9af55a66c6d8a310ef75` |
| Operator-kit backup controller | `d6c19565ba906a20335dbf3b8a810c3de8d59442` |
| Observer host kernel prerequisites, retained from earlier acceptance | `11fe97ba8c973e5af2dc8aedc20c908248c3344b` |

Core source includes [PR #473](https://github.com/po4yka/ripdpi-vpn-deploy/pull/473)
and the subsequent maintenance changes in
[PR #481](https://github.com/po4yka/ripdpi-vpn-deploy/pull/481).
Monitoring includes [PR #482](https://github.com/po4yka/ripdpi-vpn-deploy/pull/482).
The kit controller includes
[PR #483](https://github.com/po4yka/ripdpi-vpn-deploy/pull/483).
Observer firewall-loader policy retains its separately recorded source; the
Kuma application revision does not replace that authority.

## Runtime and hardening

The core transactions passed deployment, verification, source-drift, security,
smoke and authenticated protocol gates, with plaintext cleanup. The final
read-only checks found required units active, no failed systemd units and no
pending reboot on all four hosts. Boot identities did not change during this
verification. Static captured files and their ownership/modes matched the
previously accepted configuration; the bound SOPS inputs were unchanged.

The 3 November version inventory remains historical: Xray v26.10.31, Hysteria
2.13.0, rclone 1.75.2+go1.27.3-1, vmagent 1.155.0, Prometheus 3.15.1,
Tailscale 1.104.4 and Kuma 2.5.9. This final check did not repeat package
advisory queries, a kernel upgrade or a reboot drill. The earlier
CVE-2026-98432 record reported mitigations on kernel 6.8.0-147, not a patched
kernel. Do not use that historical record as a current vendor-advisory verdict.
The normal [Xray release policy](xray-release-line.md#production-rollout-policy)
still applies to future promotion.

## Transport activation

The server producer changes and paired Android changes in
[PR #709](https://github.com/po4yka/RIPDPI/pull/709) are merged. A debug APK was
prepared without an embedded private bundle. It was not installed on a physical
device or published as a production client release in this acceptance scope.

| Capability | Source capability | Recorded activation |
|---|---|---|
| Bounded XHTTP pool | Typed `stream-up` profile, 1–4 carriers per endpoint | Off; no tuned recipient adoption accepted |
| Payload failover | Version 2 exact-body policy with two independent owned HTTPS controls | Off; controls and installed paired client unavailable |
| TCP reserve selection | REALITY/XHTTP candidates checked first after active Hysteria2 payload failure under the explicit policy | Policy off; automatic recovery not accepted on a device |

Ordinary TCP service reachability passed. It does not prove automatic failover.
AmneziaWG remains outside the imported selector pool. All-candidate failure must
retain the encrypted selection rather than select direct. Use
[XHTTP delivery profiles](xhttp-delivery-profiles.md),
[the bundle contract](ripdpi-bundle.md#ripdpipayload_failover) and
[owned control probes](../how-to/payload-throttle.md) before activation.

## Functional and monitoring checks

- Fresh REALITY, XHTTP, Hysteria2 and AmneziaWG cloud-sentinel checks passed
  authenticated traffic and tunnel DNS. AmneziaWG had a fresh handshake.
- All nine expected scrape targets were UP. Six source-identity series matched.
  Evidence was fresh and rule evaluation was healthy. Queue and drop counts
  were zero; the components remained within their existing resource caps.
- Kuma had three node monitors and one pipeline monitor, all fresh and UP.
  The panel-only deployment has no Telegram delivery or human-receipt claim.
- Current component status checks passed for all three agents, the collector
  and the observer. No new node, disk or provider access rule was added.

One node-a push attempt failed during the backup window. Its next normal timer
run succeeded before final acceptance. No failed state was reset to hide it.
These observations prove the recorded cloud vantage and point-in-time state.
They do not prove a physical Android session, a filtered access path, new load
admission or an extended soak. The earlier public-site TLS checks remain dated
3 November evidence; the final check did not repeat them.

## Configuration and recovery

Encrypted configuration captures were checked by decryption and full manifest
comparison on all four hosts. Static file comparison covered 457 files on
node-a, 503 on node-b, 482 on node-c and 189 on observer-a. Secret/configuration
parity reused the prior acceptance only after checking unchanged bound inputs.
Temporary plaintext from the component checks was removed.

A fresh Kuma backup and scheduled recovery completed. The job uploaded and
read back the exact private encrypted object, decrypted it, checked its full
manifest and verified SQLite integrity with WAL included. Its temporary
workspace was clean, the recovery timer was active and the primary Kuma
application was active. This did not start a second application. The earlier
isolated database/image startup test remains separate evidence.

The refreshed complete operator-kit offsite snapshot was downloaded, decrypted
and manifest-verified: **3,277 files**, with anonymous download denied. Working
identities and temporary runtime files were excluded. The private catalog was
corrected to point to accepted component sources and receipts. Historical
attempts and recovery material were retained. The earlier VPN restic restore
checks were not repeated by this final observer/kit operation.

The catalog and delivery acknowledgement record the snapshot they describe.
Post-upload acknowledgements are separate from that snapshot; a backup does
not claim to contain its own receipt. See
[fleet maintenance](../how-to/fleet-maintenance.md#seal-and-verify-the-operator-kit)
and [observer recovery](observability-operations.md#scheduled-download-and-sqlite-recovery)
for the separate verification scopes.

## Security reporting update (2026-11-04)

[PR #486](https://github.com/po4yka/ripdpi-vpn-deploy/pull/486) added the daily
repository checks and private systemd report. The workflow is active on the
default branch. At this update, no scheduled or manual daily-security run had
been observed. Hosted scan artifacts, issue updates and notification delivery
remain unverified. These scans inspect repository inputs, not the live fleet.

The owner separately approved the report-only audit on the three VPN nodes.
The first run retained a CLI error and no assessed units because `security`
rejects `--no-legend`. [PR #491](https://github.com/po4yka/ripdpi-vpn-deploy/pull/491)
removed that flag. The corrected role was applied from
`fdb0f760827a4adffa3032d1fe0da5d104b5acdc`; its role and playbook files match
the merged source `4a980d5a883c9049d693df6caade98e920e4c7f6`.

Preview and `make security-audit` passed on all three nodes. Direct readback at
**2026-11-04 09:00 UTC** verified fresh `systemd-security.txt` reports:

| Host | Analyzer result | Assessed service units | Failed units | Lynis warnings |
|---|---|---|---|---|
| node-a | rc=0 | 52 | 0 | 2 |
| node-b | rc=0 | 55 | 0 | 2 |
| node-c | rc=0 | 53 | 0 | 2 |

Each systemd report was owned by `root:root` with mode 0640. Lynis collection
succeeded; its warnings were not suppressed. The role installed its existing
Lynis dependency and the `menu` package. This is collection acceptance, not a
clean-security verdict. Isolation scores describe configuration, not a service
vulnerability finding.

SSH/nftables configuration hashes, core manifests and boot IDs matched the
pre-audit state. No core deployment, credential change, Cloudflare change or
new client-traffic acceptance was part of this run. The observer was outside
this three-node audit. Failed-attempt and successful evidence are retained in
an encrypted bundle; the operator catalog indexes the scoped receipt.

Use [security checks](../how-to/security-checks.md) for the separate workflow
and host-audit procedures. The audit role is not a `site.yml` deployment step
and does not install a recurring host timer.

## Evidence and refresh boundary

The private kit retains `receipts/final-state-20261104/final-delivery.json` and
its bound protocol, monitoring, configuration, Kuma recovery and offsite
receipts. The final delivery receipt SHA-256 is
`51ff63c7ac9e503339582b4246ace32033443ceceb1f3f00f569dc113777cc4e`.
This public summary contains categorical results only.

No repository source changed for those live final checks. No new full local
build gate or hosted CI run was claimed. Earlier local Mac gate failures remain
failures; earlier hosted Linux success remains evidence of its exact tree.
Neither establishes the current running state by itself. Source hardening
merged after the recorded component revisions needs its own deployment receipt.

To refresh this snapshot, obtain authorization for the exact live scope, follow
[deployment acceptance](../how-to/deploy.md#acceptance-scope-and-completion),
record current component revisions and authenticated traffic, and repeat only
the affected security, monitoring and recovery checks. Keep secret values,
endpoints and raw diagnostics in the private operator kit. A documentation
update alone does not refresh a live observation or require redeployment.
