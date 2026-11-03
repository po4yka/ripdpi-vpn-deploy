# Deployment status — last verified snapshot

> **Status:** Snapshot (2026-11-03) · **Type:** reference · **Tier:** — · **Reviewed:** 2026-11-03

This page records the security-remediation deployment and final checks completed
on **2026-11-03**. It replaces the August deployment snapshot. It is not a live
health report. Later source changes, provider changes and credential rotations
need their own checks. Private endpoints, identifiers and secret values remain
in the ignored operator kit.

## Source and fleet

The three VPN nodes run core source
`464c5a5dce47d7945b70e8587248410df1dff9de`, merged in [PR #477](https://github.com/po4yka/ripdpi-vpn-deploy/pull/477).
The tested PR tree and merged tree matched. The [merged-source Linux CI run](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/41527356199)
completed with **81 successful jobs**, no failures and no skipped jobs.
Later commits on `main` are not evidence of further production deployment.

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

Monitoring components have separate source authorities. Do not report one
whole-host revision for the observer:

| Component | Accepted source |
|---|---|
| VPN core, node agents, collector and firewall loader lifecycle | `464c5a5dce47d7945b70e8587248410df1dff9de` |
| Kuma application deployment | `67c3ef3adc484b8d782ddcf3365c6d90b04e18d6` |
| Observer host kernel prerequisites | `11fe97ba8c973e5af2dc8aedc20c908248c3344b` |

## Runtime and hardening

| Component | Verified deployment |
|---|---|
| Xray | v26.10.31 |
| Hysteria | 2.13.0, rebuilt with Go 1.27.3 |
| rclone | 1.75.2+go1.27.3-1 |
| vmagent | 1.155.0, built with Go 1.27.3 |
| Collector Prometheus | 3.15.1, built with Go 1.27.3 |
| Tailscale | 1.104.4; installed package and APT preference agree on all four hosts |
| Kuma | 2.5.9, scanned architecture-specific pinned image; matching database/image restore passed |

Xray was updated in serial canaries on node-a, node-b and node-c, with
checks and retained rollback after each. The owner approved a one-time
exception to the 48-hour staging soak; the normal
[Xray release policy](xray-release-line.md#production-rollout-policy) still applies.
The current RIPDPI engine passed TCP, Vision and UDP interoperability tests
against the new server. Those tests did not require a client-engine change.
P0 probes use Xray; incompatible sing-box REALITY profiles are refused.

All four hosts had no failed systemd units and no pending reboot in the final
capture. Key-only SSH and private admin listeners were verified. Operator API
credentials and CA signing keys were absent from the captured server configuration.
MPTCP was disabled. An early input rule dropped IPv4 TCP packets with IP options.
Firewall loader stop/reload preserved independently owned tables and timed sets.

The CVE-2026-98432 kernel fix remained pending at this observation. Installed
kernel 6.8.0-147 used the verified mitigations above; it was not reported as
patched. A later vendor release requires fresh review and deployment. There was
no production reboot test after installation of the kernel guard.
Distribution restic, Docker and containerd compiler versions were recorded
separately; they were not all rebuilt with Go 1.27.3. The backup TLS path used
the patched rclone child process.

## Functional and monitoring checks

- REALITY, XHTTP, Hysteria2 and AmneziaWG passed authenticated cloud-sentinel
  traffic and DNS checks. AmneziaWG had a fresh handshake.
- Each VPN node passed the final security and smoke checks.
- Owned site names resolved through two independent DNS-over-HTTPS resolvers.
  HTTPS returned the expected HTML and CSS with a trusted chain and hostname.
  HTTP redirected to HTTPS. The observed certificate expires on 2027-01-27.
- Metrics were fresh, expected target identities matched and rule evaluation
  was healthy. Remote-write queue and drop checks passed.
- Kuma had three node monitors and one pipeline monitor, all UP. The panel-only
  deployment has no Telegram bots or human-notification delivery claim.
- The panel UI bound only to host loopback. The private push ingress exposed
  no public administration route.

These results prove the recorded cloud vantage. They do not prove a new
physical Android session, every personal client or a filtered access path.
Previously accepted resource observations were retained; no long load test
or extended soak was repeated for this final acceptance.

## Configuration and recovery

The final capture covered **1,805 files on four hosts**. It was encrypted and
checked by decrypting and comparing its manifest. The operator audit checked
**47 SOPS documents**, current per-node authority, four Terraform states and
their encrypted recovery copies. Source recovery from the encrypted bundle
chain passed. No unexpected plaintext secret files were found in the scanned
local scope. Direct-tool SSH and age working identities remained documented
mode-0600 exceptions protected by FileVault.

Each VPN node completed a fresh backup, offsite copy and restore check. The
current Kuma image passed an isolated database restore without network or
published ports. The complete operator-kit offsite snapshot was downloaded,
decrypted and manifest-verified: **2,864 files**, with anonymous download denied.
Private data used the private backup bucket. The separate public bucket held
only a constant health object, not configuration or backups.

The operator kit holds exact resource IDs, paths, checksums, component profiles,
SSH pins, grant records and restore evidence. Its catalog identifies current
sources separately from failed attempts and superseded preparation. Post-upload
acknowledgements are recorded separately from the uploaded snapshot, so a backup
does not claim to contain its own delivery receipt.

## Evidence and refresh boundary

The private kit's `catalog.json` points to the final delivery record
`receipts/security-remediation-20261102/final-delivery-acceptance-pr477.json` and
the underlying live, source, configuration and recovery receipts. This public
summary includes categorical results only.

The full local `make check` was not green: it retained known Mac environment
failures. Eight tool-version failures passed when rerun with the pinned
Prometheus tool. The successful hosted Linux run remains separate evidence;
it does not turn a failed local command into a pass. The final APT security
candidate query used the trusted host cache, not a new repository refresh or
a general operating-system upgrade.

To refresh this snapshot, obtain authorization for the exact live scope, follow
[deployment acceptance](../how-to/deploy.md#acceptance-scope-and-completion),
record current component revisions and authenticated traffic, and repeat only
the affected security, monitoring and recovery checks. Keep secret values,
public endpoints and raw diagnostics in the private operator kit. A documentation
update alone does not refresh a live observation or require redeployment.
