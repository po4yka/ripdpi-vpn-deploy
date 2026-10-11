# Ansible roles audit — 2026-10-09

## Result and review boundary

**44 confirmed code/contract/test defects: 11 P1, 32 P2, 1 P3.** A further **15 investigation or improvement points** are separated below, including two split-hop packet-path concerns requiring Linux acceptance. “Confirmed” means a verified source mechanism or isolated reproduction, not an observed production incident. An all-role audit cannot guarantee the absence of other defects.

Reviewed commit: `28783a7e1d48a0c192db4da06cf23b9d9a9d5637`, branch `chore/agent-config-modernization`. This is a review of the full role implementation at that snapshot, not attribution to that branch. Root and two sub-agents divided all 37 roles; cited findings were vetted by the root reviewer, and the major observability/watchdog findings received an independent challenge.

Implementation source, task state, existing plans and infrastructure were not changed. This report is the only new repository artifact. The pre-existing untracked `.worktrees/` entry was preserved. No plaintext secrets, generated live inventory, Terraform state, SSH, provider APIs, deployment, commits or PR operations were used.

Priority definitions: P1 = serious security, availability or recovery failure under the named trigger; P2 = concrete lifecycle/contract/correctness defect; P3 = lower-impact evidence/quality defect. Effort includes regression coverage: S = hours, M = about a day, L = several days. Fix risk describes what remediation could disrupt. All confirmed entries have HIGH confidence in the described mechanism; explicit runtime gaps remain attached.

## Finding index

| ID | Priority | Finding | Effort | Fix risk |
|---|---|---|---|---|
| F44 | P1 | Xray log rotation sends an unsupported clean-exit signal | S/M | MED |
| F01 | P1 | Xray startup repair crosses the runtime-to-root boundary | M | MED |
| F02 | P1 | Subscription restart recreates missing revocation authority as empty | S | LOW |
| F03 | P1 | Share-bundle tasks expose bearer tokens in Ansible results | S | LOW |
| F04 | P1 | Baseline disables the DNS stub without replacing resolver ownership | S/M | MED |
| F05 | P1 | Backup inputs assume disabled transports are installed | S | LOW/MED |
| F06 | P1 | Control-plane revocation and ingress changes never reload running nginx | S/M | MED |
| F07 | P1 | Public dead-man TLS accept can block before request bounds apply | M | MED |
| F08 | P1 | Dead-man replay state is incompatible with generation rotation | M | MED/HIGH |
| F09 | P1 | A stalled watchdog notification can stop supervision indefinitely | S | LOW/MED |
| F10 | P1 | Watchdog notification credentials enter child argv and environment | S/M | MED |
| F11 | P2 | Subscription-only TLS has no role owner | M | MED |
| F12 | P2 | Evidence SSH account is excluded by baseline AllowUsers | M | HIGH |
| F13 | P2 | Existing Tailnet check mode skips probes then parses empty output | S | LOW |
| F14 | P2 | Strict egress misses XHTTP-only and Snell-only proxy requirements | S | MED |
| F15 | P2 | Internal package_updates.enabled=false leaves enabled policy installed | S | LOW |
| F16 | P2 | Internal sshd-jail disable leaves the active jail unchanged | S | LOW |
| F17 | P2 | Fail2Ban ban actions hide all nftables failures | S | MED |
| F18 | P2 | Firewall replacement erases active ban membership | M | MED/HIGH |
| F19 | P2 | Fallback XHTTP logs traffic the primary path suppresses | S | LOW |
| F20 | P2 | Cloudflare real-IP trust escapes its own vhost | S | LOW/MED |
| F21 | P2 | Geodata refresh publishes half a pair before validating the other half | M | MED |
| F22 | P2 | Failed nginx validation leaves invalid live files installed | M/L | MED/HIGH |
| F23 | P2 | Baseline's BBR exception masks unrelated sysctl failures | S | LOW/MED |
| F24 | P2 | CDN AOP scenario cannot reach its advertised runtime assertions | S/M | LOW |
| F25 | P2 | Realm schema is unsupported by the exact pinned sing-box release | M | MED |
| F26 | P2 | AWG runtime and unit upgrades do not restart existing instances | S/M | MED |
| F27 | P2 | AWG instance removal does not retire runtime or private config | M | MED |
| F28 | P2 | Naive HTTP/3 UDP is absent from the socket contract | S/M | MED |
| F29 | P2 | Realm alpha pin lacks production rejection | S | LOW |
| F30 | P2 | WARP installation has no exact package-version contract | S/M | MED |
| F31 | P2 | Probe service-unit changes are reloaded but not applied to processes | S | LOW/MED |
| F32 | P2 | Site-level disable skips cleanup rather than converging absence | M/L | MED/HIGH |
| F33 | P2 | Observability check mode consumes outputs that its commands never produce | M | MED |
| F34 | P2 | Observability Prometheus pin updates omit service restart | S/M | MED |
| F35 | P2 | Policy detector heartbeat depends on traffic arrival | S/M | LOW |
| F36 | P2 | Policy detector retains inactive source keys without a bound | S/M | LOW/MED |
| F37 | P2 | Policy metric temporary path can overwrite another producer's file | S/M | LOW/MED |
| F38 | P2 | Watchdog checks a base REALITY port absent from valid cohort layouts | S | LOW/MED |
| F39 | P2 | Watchdog state publication can truncate its recovery budget | S/M | LOW/MED |
| F40 | P2 | Dead-man rollback restores a config link but not complete authority | M | MED/HIGH |
| F41 | P2 | Unchanged control-plane convergence consumes the prior rollback pointer | S | LOW/MED |
| F42 | P2 | Malformed protocol evidence can preserve last-good fresh metrics | S/M | LOW |
| F43 | P3 | WARP recovery test asserts a counter it changes itself | M | LOW |

## Confirmed findings

### F44 — P1 — Xray log rotation sends an unsupported clean-exit signal

**Evidence:** `ansible/roles/monitoring/templates/logrotate-xray.j2:10`; `ansible/roles/xray/templates/xray.service.j2:25`; `ansible/roles/geodata/templates/vpn-xray-geodata-activate.sh.j2:8-26`.

Daily rotation sends SIGHUP to the supported/example v26.3.27 runtime, which registers only SIGINT/SIGTERM. Go's unhandled HUP terminates the process; systemd on-failure does not restart clean SIGHUP exits. Xray can remain down until watchdog threshold/budget recovery or manual action. The geodata helper assumes all 26.4+ versions support HUP, but exact v26.4.17 and v26.5.3 source scans also show no handler.

**Remediation and regression:** Use a supported, exact-pin-tested logger lifecycle or controlled restart with its connection interruption explicit; remove the unverified version threshold. Force real log rotation and geodata activation, require listener recovery and writes to the new log inode.

**Confidence / effort / fix risk:** HIGH / S/M / MED. **Observed evidence:** Exact upstream source and primary Go/systemd semantics verified; Linux/systemd runtime reproduction unavailable.

### F01 — P1 — Xray startup repair crosses the runtime-to-root boundary

**Evidence:** `ansible/roles/xray/templates/xray.service.j2:22`; `ansible/roles/xray/tasks/main.yml:100-103`.

The runtime owns the log directory and can replace its directory entries. The privileged startup hook follows access/error-log paths with root chown/chmod. After a runtime compromise, a restart can change ownership or permissions of an unrelated root file. The systemd + prefix bypasses the unit's user, capability and filesystem restrictions.

**Remediation and regression:** Remove privileged pathname repair or use root-owned log-entry parents and a no-follow, inode-checked helper. Test a synthetic outside-target symlink and prove its metadata is unchanged.

**Confidence / effort / fix risk:** HIGH / M / MED. **Observed evidence:** Source and primary systemd semantics verified; no exploit against a host.

### F02 — P1 — Subscription restart recreates missing revocation authority as empty

**Evidence:** `ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2:83-88,440-441`.

A missing deny list correctly returns unavailable during requests, but startup creates an empty file. Previously revoked tokens with surviving payloads become usable after restart.

**Remediation and regression:** Serving code must require safely provisioned revocation state. Test revoked payload → lost revocation file → restart and require refusal throughout.

**Confidence / effort / fix risk:** HIGH / S / LOW. **Observed evidence:** Reproduced with a rendered helper and temporary synthetic state.

### F03 — P1 — Share-bundle tasks expose bearer tokens in Ansible results

**Evidence:** `ansible/roles/subscription-host/tasks/share-bundles.yml:18-43`.

Token-bearing paths and loop dictionaries are returned without no_log. A friendly loop label does not redact path/dest/item values under verbose or structured callbacks. These tokens grant access to recipient material.

**Remediation and regression:** Apply no_log and diff suppression to token-bearing directory/copy operations. Run synthetic-token uploads under verbose callbacks and assert complete token absence.

**Confidence / effort / fix risk:** HIGH / S / LOW. **Observed evidence:** Confirmed source-level disclosure path; no real tokens accessed.

### F04 — P1 — Baseline disables the DNS stub without replacing resolver ownership

**Evidence:** `ansible/roles/baseline/tasks/main.yml:50-60`; `ansible/roles/baseline/handlers/main.yml:7-10`.

On supported Ubuntu hosts using the stock stub resolv.conf symlink, restarting resolved removes the listener still referenced by the resolver file. Baseline neither repoints the file nor installs the promised replacement. DNS downloads, upstream resolution and probes fail.

**Remediation and regression:** Inspect resolver ownership, atomically select the non-stub resolved file or provision the intended resolver, and validate controlled DNS resolution after handler flush. Test with AWG disabled and the stock symlink.

**Confidence / effort / fix risk:** HIGH / S/M / MED. **Observed evidence:** High-confidence conditional source defect; stock-image Linux runtime not reproduced.

### F05 — P1 — Backup inputs assume disabled transports are installed

**Evidence:** `ansible/roles/backup/templates/vpn-backup.sh.j2:146-169`; `ansible/roles/backup/molecule/default/converge.yml:13-55`.

The input array always includes Xray, Hysteria, Snell, nginx and watchdog paths. Narrow profiles lack several of them. Restic produces an incomplete snapshot and exits 3; set -e stops retention, integrity checks and remote replication. Fixture-created placeholder directories hide most of this.

**Remediation and regression:** Derive required paths from the effective profile. Missing enabled-service inputs must fail; disabled inputs must be omitted. Run real restic across P0, P1-web, subscription-only and full profiles without fake directories.

**Confidence / effort / fix risk:** HIGH / S / LOW/MED. **Observed evidence:** Real local restic temporary-fixture missing-path check returned 3.

### F06 — P1 — Control-plane revocation and ingress changes never reload running nginx

**Evidence:** `ansible/roles/observability_control_plane/tasks/enable.yml:137-158,365-394`; `ansible/roles/observability_control_plane/handlers/main.yml:14-18`.

TLS/CA/CRL and ingress configuration are replaced without notification or explicit reload. state:started leaves existing workers on their old SSL context and node mapping. New handshakes can continue accepting an identity revoked in the newly installed CRL.

**Remediation and regression:** Track authority/config changes, validate a complete candidate and explicitly reload before acceptance. Test a previously accepted certificate becoming rejected on a new connection after CRL rotation.

**Confidence / effort / fix risk:** HIGH / S/M / MED. **Observed evidence:** Source confirmed and independently challenged by a second reviewer. Established-connection persistence is not the claimed defect.

### F07 — P1 — Public dead-man TLS accept can block before request bounds apply

**Evidence:** `ansible/roles/observability_deadman/files/observability-deadman.py:66-70,848-857,918-921`.

TLS wraps the listening socket with default handshake-on-accept behavior. The synchronous accept path has no handshake timeout. Handler timeouts and the four-request semaphore run afterward. An incomplete handshake can stop legitimate pulse acceptance while systemd still sees a running process.

**Remediation and regression:** Bound accepted sockets before TLS negotiation and use a bounded worker pool covering handshake/header/body work. Test incomplete handshakes alongside legitimate pulses and require prompt serviceability.

**Confidence / effort / fix risk:** HIGH / M / MED. **Observed evidence:** Reproduced using the actual BoundedPulseServer class, local sockets and temporary generated TLS material.

### F08 — P1 — Dead-man replay state is incompatible with generation rotation

**Evidence:** `ansible/roles/observability_deadman/files/observability-deadman.py:396-425`; `ansible/roles/observability_control_plane/files/observability-deadman-pipeline.py:342-380,727-749`.

The sender clears generation-bound pulse state and restarts sequencing at 1. The receiver retains one global last_sequence and validates generation syntax without comparing the configured generation. A legitimate new generation is rejected until its counter overtakes the old one; an advancing correctly signed wrong-generation pulse is accepted.

**Remediation and regression:** Bind replay state to an explicitly authorized generation transition and preserve replay rejection within each authority epoch. Test an old high counter → new generation sequence 1, rejected old/wrong-generation pulses and rollback.

**Confidence / effort / fix risk:** HIGH / M / MED/HIGH. **Observed evidence:** Both mismatched-generation acceptance and fresh-generation sequence rejection reproduced offline.

### F09 — P1 — A stalled watchdog notification can stop supervision indefinitely

**Evidence:** `ansible/roles/watchdog/templates/vpn-watchdog.sh.j2:285-316`; `ansible/roles/watchdog/templates/vpn-watchdog.service.j2:6-13`.

Notification curl calls have no connect/total bounds. The oneshot unit sets no TimeoutStartSec, whose default for oneshots is unlimited. A stalled notification prevents state publication and completion; later timer firings cannot start another instance.

**Remediation and regression:** Bound every external call and set a whole-unit deadline sized for all probes/cleanup. Test a local stalled notification endpoint and require a completed failed run plus a subsequent timer run.

**Confidence / effort / fix risk:** HIGH / S / LOW/MED. **Observed evidence:** Source and primary systemd timeout semantics verified.

### F10 — P1 — Watchdog notification credentials enter child argv and environment

**Evidence:** `ansible/roles/watchdog/templates/vpn-watchdog.env.j2:5-14`; `ansible/roles/watchdog/templates/vpn-watchdog.sh.j2:285-303`.

Notification tokens are exported and expanded into curl -H/-d arguments. Process inspection can expose them to another local account where argv is visible. Mode 0600 on the environment file does not protect a spawned command line. The separate REALITY probe configuration remains root-only.

**Remediation and regression:** Use LoadCredential and a sender that reads credentials internally without placing them in argv/environment. Test process metadata with synthetic notification credentials and assert absence.

**Confidence / effort / fix risk:** HIGH / S/M / MED. **Observed evidence:** Confirmed source path; no real credentials read or reproduced.

### F11 — P2 — Subscription-only TLS has no role owner

**Evidence:** `ansible/roles/subscription-host/templates/subscription.conf.j2:12-13`; `ansible/roles/subscription-host/tasks/main.yml:7-57`; `ansible/playbooks/site.yml:277-278`.

Clean subscription-only hosts skip nginx-xhttp but still reference its TLS files. The subscription role never installs those files; Molecule supplies them in pre_tasks. nginx validation therefore cannot converge an empty delivery host.

**Remediation and regression:** Provide a shared or independent TLS delivery contract before nginx validation. Test clean subscription-only HTTPS with no transport role.

**Confidence / effort / fix risk:** HIGH / M / MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F12 — P2 — Evidence SSH account is excluded by baseline AllowUsers

**Evidence:** `ansible/roles/baseline/templates/sshd_config.d-hardening.conf.j2:24`; `ansible/roles/real-vps-awg-nat/tasks/server.yml:110-115,237-243`.

Baseline admits only ansible_user. Recurring AWG evidence creates a distinct forced-command account without extending or verifying that policy. Normal hardened nodes reject it before its restricted command can run.

**Remediation and regression:** Add the account through the recoverable SSH authority contract and verify its effective context. Test successful forced-command authentication while shell and forwarding remain denied.

**Confidence / effort / fix risk:** HIGH / M / HIGH. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F13 — P2 — Existing Tailnet check mode skips probes then parses empty output

**Evidence:** `ansible/roles/tailnet-management/tasks/main.yml:67-116`.

The status/preferences commands omit check_mode:false. On an installed host --check skips them and their JSON-dependent guards fail on empty stdout.

**Remediation and regression:** Execute these read-only probes in check mode with changed_when:false. Test Running and NeedsLogin paths with the actual task graph and prove no enrollment writes.

**Confidence / effort / fix risk:** HIGH / S / LOW. **Observed evidence:** Exact task fragment reproduced --check JSON failure (exit 2) with a synthetic installed Tailnet response.

### F14 — P2 — Strict egress misses XHTTP-only and Snell-only proxy requirements

**Evidence:** `ansible/roles/firewall/templates/nftables.conf.j2:28,186-209`; `ansible/group_vars/vpn-p1-web.yml:10-14`.

The proxy egress predicate recognizes REALITY, Hysteria and Naive only. A supported XHTTP-only profile or Snell-only profile with strict egress loses arbitrary client TCP/UDP destinations.

**Remediation and regression:** Derive proxy egress from the complete effective transport contract. Test XHTTP-only/Snell-only packet paths and a non-proxy default-drop control.

**Confidence / effort / fix risk:** HIGH / S / MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F15 — P2 — Internal package_updates.enabled=false leaves enabled policy installed

**Evidence:** `ansible/roles/package_updates/tasks/main.yml:60-73`; `ansible/roles/package_updates/templates/51ripdpi-unattended-upgrades.j2:3-5`.

The false flag skips policy rendering, including the template's already implemented disabled values. An enabled→disabled transition retains automatic updates even when the role still executes.

**Remediation and regression:** Always reconcile the policy; gate package installation separately. Verify enabled→disabled→disabled effective APT settings and idempotence.

**Confidence / effort / fix risk:** HIGH / S / LOW. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F16 — P2 — Internal sshd-jail disable leaves the active jail unchanged

**Evidence:** `ansible/roles/intrusion_prevention/tasks/main.yml:96-104`; `ansible/roles/intrusion_prevention/templates/fail2ban-sshd.local.j2:4`.

The role skips rendering on sshd.enabled=false, retaining its prior enabled=true jail and omitting restart notification.

**Remediation and regression:** Render disabled state or remove the owned jail and reconcile the runtime. Exercise actual enabled→disabled transitions and Fail2Ban status.

**Confidence / effort / fix risk:** HIGH / S / LOW. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F17 — P2 — Fail2Ban ban actions hide all nftables failures

**Evidence:** `ansible/roles/intrusion_prevention/templates/action.d/nftables-ripdpi.conf.j2:13-14`.

Both actions suppress stderr and force success. Missing sets, permission failures and other unexpected errors leave offenders unblocked while Fail2Ban records successful enforcement.

**Remediation and regression:** Distinguish expected membership races from actual failures and propagate categorical errors. Inject an nft failure and verify it is not recorded as a successful ban.

**Confidence / effort / fix risk:** HIGH / S / MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F18 — P2 — Firewall replacement erases active ban membership

**Evidence:** `ansible/roles/firewall/templates/nftables.conf.j2:7,41-59`; `ansible/roles/firewall/tasks/main.yml:426-430`.

An ordinary firewall update destroys the filter table and recreates empty dynamic sets. Fail2Ban keeps its prior logical bans, and unchanged intrusion-prevention configuration does not reapply them. Policy-offender membership is also lost.

**Remediation and regression:** Preserve bounded dynamic state or explicitly restore verified membership after replacement. Ban IPv4/IPv6 addresses, change an unrelated firewall field, and verify enforcement and remaining TTL.

**Confidence / effort / fix risk:** HIGH / M / MED/HIGH. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F19 — P2 — Fallback XHTTP logs traffic the primary path suppresses

**Evidence:** `ansible/roles/nginx-xhttp/templates/site.conf.j2:46-47,121-135,154`.

The fallback transport location lacks access_log off and inherits its server's access log. Enabling fallback records transport request/session paths unlike the primary listener.

**Remediation and regression:** Apply the primary transport's logging boundary to fallback. Test synthetic fallback transport requests absent from logs while ordinary public-site requests remain logged.

**Confidence / effort / fix risk:** HIGH / S / LOW. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F20 — P2 — Cloudflare real-IP trust escapes its own vhost

**Evidence:** `ansible/roles/cdn-front/templates/cdn-front.conf.j2:6`; `ansible/roles/cdn-front/templates/refresh-cf-prefixes.sh.j2:143-146`.

The include is at http scope, so its header/source trust is inherited by co-resident direct and subscription vhosts. Requests from trusted proxy ranges can rewrite attribution and per-IP rate-limit keys on those separate surfaces.

**Remediation and regression:** Move the include into the CDN server and validate the refresh candidate in that context. Test the same forwarded header across CDN/direct/subscription listeners.

**Confidence / effort / fix risk:** HIGH / S / LOW/MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F21 — P2 — Geodata refresh publishes half a pair before validating the other half

**Evidence:** `ansible/roles/geodata/templates/vpn-geodata-refresh.sh.j2:8-21`.

A successful geosite replacement followed by failed geoip download/checksum leaves mixed generations on disk and skips activation. A later restart consumes that unreviewed pair.

**Remediation and regression:** Stage and verify both files before recoverable paired publication. Test second-download/checksum failure and activation failure preserving the previous complete pair.

**Confidence / effort / fix risk:** HIGH / M / MED. **Observed evidence:** A rendered refresh using a controlled second-download failure exited 22 and left new-geosite with old-geoip.

### F22 — P2 — Failed nginx validation leaves invalid live files installed

**Evidence:** `ansible/roles/nginx-xhttp/tasks/main.yml:103-123,221-247`; `ansible/roles/subscription-host/tasks/main.yml:37-57`; `ansible/roles/cdn-front/tasks/main.yml:87-107`; `ansible/roles/observability_control_plane/tasks/enable.yml:137-158,365-388`.

Roles overwrite live TLS/config/link state before nginx -t without restoring prior bytes on failure. Existing workers may continue, but a reboot or restart loads the invalid tree left by a rejected deployment.

**Remediation and regression:** Use a shared candidate/validate/publish/compensate contract for the complete nginx tree. Apply a bad key/config to a working fixture, require failure, unchanged prior disk state and a successful subsequent restart.

**Confidence / effort / fix risk:** HIGH / M/L / MED/HIGH. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F23 — P2 — Baseline's BBR exception masks unrelated sysctl failures

**Evidence:** `ansible/roles/baseline/tasks/main.yml:121-128`.

Any nonzero sysctl --system result is accepted whenever stderr mentions the congestion-control key, even if other mandatory hardening settings also failed.

**Remediation and regression:** Handle optional congestion control separately and require other settings to apply. Test BBR-only failure versus BBR plus an unrelated hardening failure.

**Confidence / effort / fix risk:** HIGH / S / LOW/MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F24 — P2 — CDN AOP scenario cannot reach its advertised runtime assertions

**Evidence:** `ansible/roles/cdn-front/molecule/cdn-on/converge.yml:67-81`; `ansible/roles/cdn-front/molecule/cdn-on/verify.yml:38-53`.

The installed synthetic PEM is not a parseable certificate. After repairing it, assertions still search the vhost file for directives in the include. This branch's integration scenario is unusable.

**Remediation and regression:** Generate a valid ephemeral CA/client pair and inspect effective nginx configuration. Require the full cdn-on scenario to distinguish accepted and rejected client authentication.

**Confidence / effort / fix risk:** HIGH / S/M / LOW. **Observed evidence:** The scenario's exact PEM failed openssl x509 parsing (exit 1). Full Molecule was not run.

### F25 — P2 — Realm schema is unsupported by the exact pinned sing-box release

**Evidence:** `ansible/roles/hysteria-realm/templates/config.json.j2:7-25`; `ansible/roles/hysteria-realm/defaults/main.yml:21`; `ansible/roles/hysteria-realm/molecule/default/converge.yml:68`.

The template emits realm-service under inbounds with auth_token/limits. The exact tagged runtime instead registers hysteria-realm as a service using users. Synthetic Molecule check validates JSON syntax only and misses native schema rejection.

**Remediation and regression:** Implement the pinned top-level services schema and supported credential/quota fields. Run the exact pinned sing-box check plus authenticated rendezvous; do not substitute json.tool.

**Confidence / effort / fix risk:** HIGH / M / MED. **Observed evidence:** Exact pinned upstream schema/registration verified. A supplemental render was rejected by locally installed sing-box 1.13.16; that is not exact-pin execution.

### F26 — P2 — AWG runtime and unit upgrades do not restart existing instances

**Evidence:** `ansible/roles/amneziawg/tasks/main.yml:147-156,178-198,200-222`.

Source-build changes are ignored and unit changes notify daemon reload only. Configuration renders are the sole restart trigger. With unchanged config, the old daemon and process sandbox remain active despite a new pin/unit.

**Remediation and regression:** Aggregate runtime-build and unit changes into the existing restart path. Test pin-only and unit-only transitions via lifecycle/PID evidence, followed by unchanged convergence.

**Confidence / effort / fix risk:** HIGH / S/M / MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F27 — P2 — AWG instance removal does not retire runtime or private config

**Evidence:** `ansible/roles/amneziawg/tasks/instances.yml:13`; `ansible/roles/amneziawg/tasks/main.yml:200-224`; `ansible/roles/amneziawg/handlers/main.yml:15-18`.

Convergence creates and starts current members only. Removed/renamed owned interfaces, separately enabled services and private config remain, including restart-on-boot and address-reuse hazards.

**Remediation and regression:** Maintain an ownership-scoped previous-instance set, stop/disable obsolete units, then remove their config. Test two→one, rename, reboot and preservation of unrelated WireGuard interfaces.

**Confidence / effort / fix risk:** HIGH / M / MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F28 — P2 — Naive HTTP/3 UDP is absent from the socket contract

**Evidence:** `ansible/roles/naive/templates/Caddyfile.j2:7`; `ansible/templates/listener-manifest.json.j2:157-164`.

Caddy enables h3 but the manifest declares TCP only. Naive and Hysteria using their default port can pass the protocol-aware preflight while both need UDP/443. Provider and guest exposure contracts also omit Naive UDP.

**Remediation and regression:** Either restrict this role to h1/h2 or model/authorize UDP at every layer and reject collisions. Test manifest collision and real co-resident socket ownership.

**Confidence / effort / fix risk:** HIGH / S/M / MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F29 — P2 — Realm alpha pin lacks production rejection

**Evidence:** `ansible/roles/hysteria-realm/defaults/main.yml:21`; `ansible/roles/hysteria-realm/tasks/main.yml:5-28`; `ansible/playbooks/site.yml:313-315`.

The deliberate alpha pin is selectable in prod by a toggle plus research approval. No role-level environment guard enforces the repository's staging-only prerelease rule.

**Remediation and regression:** Reject prod plus alpha before any mutation, following the Snell guard pattern. Test prod refusal before download/user creation and permitted staging.

**Confidence / effort / fix risk:** HIGH / S / LOW. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F30 — P2 — WARP installation has no exact package-version contract

**Evidence:** `ansible/roles/warp-outbound/tasks/main.yml:68-73`.

The repository signing-key pin authenticates origin but apt name:cloudflare-warp state:present chooses a mutable repository version. Identical source and secret inputs can recreate different runtimes.

**Remediation and regression:** Require an exact approved package version and verify installed identity. Test missing-pin rejection and an approved package transition.

**Confidence / effort / fix risk:** HIGH / S/M / MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F31 — P2 — Probe service-unit changes are reloaded but not applied to processes

**Evidence:** `ansible/roles/probe-matrix-target/tasks/main.yml:175-192`.

Both probe units notify only daemon reload; state:started retains their existing processes. Unit-only sandbox or execution changes are reported converged without applying the new process context.

**Remediation and regression:** Restart the affected service after unit changes. Test a unit-only transition, effective process properties and an idle repeated converge.

**Confidence / effort / fix risk:** HIGH / S / LOW/MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F32 — P2 — Site-level disable skips cleanup rather than converging absence

**Evidence:** `ansible/playbooks/site.yml:275-357`; `ansible/roles/observability_agent/tasks/main.yml:24-59`; `ansible/roles/node_manifest/templates/manifest.json.j2:59-77`.

Disabled roles are omitted. In particular, observability_agent's implemented disable block cannot run from ordinary site deployment. Existing sender units, WAL and credentials remain; other toggle-owned units/config similarly persist while the manifest reports disabled intent. Firewall closure is not service retirement.

**Remediation and regression:** Invoke lifecycle reconciliation for owned roles even when disabled, with explicit ownership and preservation boundaries. Test full→minimal and sender-on→off transitions, including units, credentials and manifest truth.

**Confidence / effort / fix risk:** HIGH / M/L / MED/HIGH. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F33 — P2 — Observability check mode consumes outputs that its commands never produce

**Evidence:** `ansible/roles/observability_agent/tasks/main.yml:216-241`; `ansible/roles/observability_control_plane/tasks/enable.yml:123-134`; `ansible/roles/observability_deadman/tasks/enable.yml:79-100`.

Agent tempfile is skipped under --check, leaving the next path access undefined. Receiver df and dead-man certificate commands skip, then assertions consume empty output. Source assertions cover nominal guards but not these actual predictive paths.

**Remediation and regression:** Run read-only probes in check mode; keep staging/publication/service actions predictive without fake artifacts. Execute complete enabled-role --check on fresh and existing namespaces and prove zero mutation.

**Confidence / effort / fix risk:** HIGH / M / MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F34 — P2 — Observability Prometheus pin updates omit service restart

**Evidence:** `ansible/roles/observability_agent/tasks/main.yml:165-204,588-596`; `ansible/roles/observability_control_plane/tasks/enable.yml:80-99,326-333`.

runtime-release publishes a changed binary but sender and receiver restart predicates consider only units/config links/activity. A version-only update can leave the old process serving even after successful local readiness.

**Remediation and regression:** Capture runtime_release_changed before later includes overwrite it and include it in activation. Test unchanged config with a new pin, verify running version/PID, then idempotence.

**Confidence / effort / fix risk:** HIGH / S/M / MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F35 — P2 — Policy detector heartbeat depends on traffic arrival

**Evidence:** `ansible/roles/policy-ratelimit/templates/policy-ratelimit.py.j2:249-260`; `ansible/roles/observability_control_plane/templates/observability-alert-rules.yml.j2:125-134`.

Publication happens only inside the loop receiving yielded log lines. A quiet process neither initializes nor refreshes metrics. Once traffic stops, the control-plane timestamp rule can classify the still healthy detector as stale.

**Remediation and regression:** Publish on an independent cadence, including before the first input, and report real tail/enforcement failures separately. Test startup and extended zero-traffic periods with fresh success timestamps.

**Confidence / effort / fix risk:** HIGH / S/M / LOW. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F36 — P2 — Policy detector retains inactive source keys without a bound

**Evidence:** `ansible/roles/policy-ratelimit/templates/policy-ratelimit.py.j2:120-126,148-156`.

Per-IP deques are bounded, but dictionary keys are never globally expired or capped. Each distinct actionable source remains forever even after its time window or ban is over, growing resident memory for the long-running service.

**Remediation and regression:** Expire inactive keys and cap cardinality with explicit behavior at capacity. Test many one-shot synthetic sources across expired windows without losing correct within-window bans.

**Confidence / effort / fix risk:** HIGH / S/M / LOW/MED. **Observed evidence:** A direct rendered-module check retained all 1,000 source keys after synthetic events spread across roughly 33 hours.

### F37 — P2 — Policy metric temporary path can overwrite another producer's file

**Evidence:** `ansible/roles/policy-ratelimit/templates/policy-ratelimit.py.j2:184-190,222-225`; `ansible/roles/monitoring/tasks/main.yml:65-72`.

The root producer opens a predictable .prom.tmp in the shared group-writable textfile directory without O_EXCL/no-follow. Another producer can precreate a symlink and make that write truncate a different writable metrics file. Sticky directory mode prevents unlink replacement, not following the temporary path.

**Remediation and regression:** Use exclusive random temporary files plus checked directory descriptors/ownership, matching the hardened adapters. Test a preexisting synthetic temporary symlink and require the other producer's bytes to remain unchanged.

**Confidence / effort / fix risk:** HIGH / S/M / LOW/MED. **Observed evidence:** A temporary-file symlink check changed the synthetic other producer's file, confirming the follow-through write. No host or real metrics touched.

### F38 — P2 — Watchdog checks a base REALITY port absent from valid cohort layouts

**Evidence:** `ansible/roles/watchdog/templates/vpn-watchdog.sh.j2:148-156,211-215`; `ansible/roles/xray/templates/config.json.j2:8-9,61-71`.

Valid nonempty cohorts replace the normal xray_port listeners, but watchdog still unconditionally tests XRAY_PORT and labels its loopback TCP failure as a wedge. If none uses that base port, healthy authenticated cohort probes coexist with a failure that eventually restarts Xray.

**Remediation and regression:** Use the effective probe manifest for every listener-dependent check. Test healthy cohorts that deliberately exclude xray_port and require no restart or false wedge notification.

**Confidence / effort / fix risk:** HIGH / S / LOW/MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F39 — P2 — Watchdog state publication can truncate its recovery budget

**Evidence:** `ansible/roles/watchdog/templates/vpn-watchdog.sh.j2:27-44,311-317`; `ansible/roles/observability_agent/files/observability-agent-health-adapter.py:224-257`.

The script overwrites the canonical state directly. Interruption/disk failure can leave partial or empty counters, which later runs default to zero. This loses rate-limit history and gives the health adapter partial evidence.

**Remediation and regression:** Atomically publish a checked, fsynced complete state through a private temporary file; preserve prior bytes on failure. Inject interruption/write failure and verify intact budget counters and parseable adapter evidence.

**Confidence / effort / fix risk:** HIGH / S/M / LOW/MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F40 — P2 — Dead-man rollback restores a config link but not complete authority

**Evidence:** `ansible/roles/observability_deadman/tasks/enable.yml:258-290,348-362,402-435`.

Credential inputs, verifier and units are overwritten outside the retained config generation. On failed activation, rescue repoints the old config and restarts using those new files. A credential/unit-caused failure cannot restore the previous working authority, despite the rollback message.

**Remediation and regression:** Bind credentials/verifier/units into immutable authority generations or snapshot the full mutable set with exact prior service state. Inject bad unit and failed credential rotation; prove old authority readiness and identity after rollback.

**Confidence / effort / fix risk:** HIGH / M / MED/HIGH. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F41 — P2 — Unchanged control-plane convergence consumes the prior rollback pointer

**Evidence:** `ansible/roles/observability_control_plane/tasks/enable.yml:305-314`.

previous.yml is repointed to current on every converge, even when no new generation is being activated, and the write is forced changed=false. After A→B followed by unchanged B, previous no longer points to A.

**Remediation and regression:** Update previous only when activating a distinct verified candidate. Test A→B→unchanged-B retaining previous=A, plus failed-C rollback.

**Confidence / effort / fix risk:** HIGH / S / LOW/MED. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

### F42 — P2 — Malformed protocol evidence can preserve last-good fresh metrics

**Evidence:** `ansible/roles/observability_control_plane/files/observability-protocol-liveness-adapter.py:103-119,333-369`.

Validation calls set(candidate_policies) before validating element scalar types. A mapping/list element raises TypeError rather than AdapterError; main bypasses malformed-state publication and leaves the existing healthy exposition untouched. Similar set-before-element-validation patterns deserve a bounded sweep.

**Remediation and regression:** Validate element types before set operations and normalize malformed inputs into the redacted error contract. Test nested container inputs replacing prior healthy output with malformed evidence.

**Confidence / effort / fix risk:** HIGH / S/M / LOW. **Observed evidence:** Valid fixture execution exited 0. A nested candidate value then exited 1 with TypeError, preserving the previous metrics byte-for-byte.

### F43 — P3 — WARP recovery test asserts a counter it changes itself

**Evidence:** `ansible/roles/warp-outbound/molecule/default/converge.yml:79-104`; `ansible/roles/warp-outbound/molecule/default/verify.yml:49-77`.

The scenario invents a retry-counter environment and increments that counter in verification after a successful curl fixture. No production role handler owns the claimed recovery behavior. This proves the fixture, not WARP recovery.

**Remediation and regression:** Replace the invented success assertion with stateful CLI/health fixtures exercising actual role outcomes or an explicit fail-closed behavior. Retain the genuine warp=off rejection check.

**Confidence / effort / fix risk:** HIGH / M / LOW. **Observed evidence:** Source verified; runtime evidence and qualifications are described in the validation section.

## Investigation and improvement points

These are not included in the 44 confirmed-defect count. Conditional configuration mechanisms, capability gaps and unverified runtime consequences are stated separately.

### I01 — P2 candidate — Split-hop IPv6 can bypass Node B

**Evidence:** `ansible/roles/split-hop-ingress/templates/split-hop-ingress.conf.j2:6,14`; `ansible/roles/split-hop-ingress/templates/policy.nft.j2:4-6`; `ansible/roles/probe-matrix-target/templates/xray.json.j2:8`.

The inet classifier marks both families, but routing rules/routes/AllowedIPs cover IPv4 only and the freedom outbound permits IPv6. Implement full dual-stack tunnel policy or explicitly refuse IPv6 before egress. Test real dual-stack destinations proving upstream traffic exits B and accepted-client replies exit A. No Linux packet-path reproduction was possible.

**Confidence / effort / fix risk:** HIGH configuration gap; Linux acceptance pending / M / MED.

### I02 — P2 candidate — Split-hop IPv4 rerouting may retain an inadmissible public source

**Evidence:** `ansible/roles/split-hop-ingress/templates/policy.nft.j2:5-6`; `ansible/roles/split-hop-egress/templates/split-hop-egress.conf.j2:29`; `ansible/roles/probe-matrix-target/templates/xray.json.j2:8`.

Sockets select a main-table source before the output-route hook applies a mark. Rerouting retains that source while B's WireGuard peer accepts only A's private address. A handshake can succeed while data is dropped. Confirm with two Linux namespaces; use source binding/socket routing or narrowly scoped SNAT rather than widening the peer ACL.

**Confidence / effort / fix risk:** MED / M / MED.

### I03 — P2 candidate — DNS bridge recursion is not protected by the loopback ACL alone

**Evidence:** `ansible/roles/dns-morph-bridge/templates/dns-morph-bridge.yaml.j2:11-17`; `ansible/roles/dns-morph-bridge/templates/unbound-fwd.conf.j2:14-15`; `ansible/roles/dns-morph-bridge/CLAUDE.md:57`.

The public bridge forwards ordinary queries as localhost, which Unbound permits. Its ACL no longer checks the original source. Additional unpublished-daemon controls may change actual exposure. Exercise unauthenticated public recursion and bounded responses against the real bridge; enforce public-source/rate/response policy at that boundary.

**Confidence / effort / fix risk:** MED / M / MED.

### I04 — P2 candidate — Xray archive/source modes share incompatible immutable release identity

**Evidence:** `ansible/roles/xray-runtime/tasks/main.yml:93-98,100-123`; `ansible/roles/runtime-release/tasks/main.yml:171-211`.

Source publication targets the same version path as archive publication while the archive receipt remains. If source bytes differ, switching back at the same version fails the archive digest invariant. Reproduce archive→source→archive and isolate mode/source identity in managed release namespaces or explicitly refuse the transition before mutation.

**Confidence / effort / fix risk:** MED / M / MED.

### I05 — P2 candidate — Security-only update origins need effective-policy verification

**Evidence:** `ansible/roles/package_updates/templates/51ripdpi-unattended-upgrades.j2:8-21`.

The fragment adds origins without clearing preexisting distro/provider policies. Inspect effective APT/unattended-upgrades merging on exact supported OS images with an intentionally broader existing policy. Only then decide what policy reconciliation is required.

**Confidence / effort / fix risk:** MED / S/M / MED.

### I06 — P2 candidate — Bearer routes may leak through nginx error logs despite access_log off

**Evidence:** `ansible/roles/subscription-host/templates/subscription.conf.j2:45-71,94`.

Rate-limit and upstream errors may include request URIs in the warning-level error log. No actual nginx log reproduction was performed. Exercise both failures with synthetic tokens and require bearer absence from all logs while retaining categorical diagnostics.

**Confidence / effort / fix risk:** MED / S/M / MED.

### I07 — P3 — Subscription audit and consumed-token history have no retention bound

**Evidence:** `ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2:102-105,244-300`.

Read-audit appends and consumed-token tombstones accumulate. Define log rotation and tombstone compaction tied to proven payload retirement. Test bounded storage without resurrecting consumed tokens from old mirror generations.

**Confidence / effort / fix risk:** HIGH; magnitude depends on issuance / M / MED.

### I08 — P3 — Interrupted publication can lose the notification needed for activation

**Evidence:** `ansible/roles/nginx-xhttp/tasks/main.yml:221-250`; `ansible/roles/geodata/tasks/main.yml:43-57`.

A controller death after installing desired bytes but before activation leaves old runtime state. A retry sees unchanged files and may emit no notification. Track desired versus activated generations and test interruption followed by complete convergence. Geodata's timer mitigates eventual delay, not convergence-time proof.

**Confidence / effort / fix risk:** HIGH source window; crash test pending / M / MED.

### I09 — P3 — Self-steal TLS staging is shared across controller invocations

**Evidence:** `ansible/roles/reality-self-steal/defaults/main.yml:5`; `ansible/roles/reality-self-steal/tasks/configure.yml:52-69,158-163`.

A fixed staging directory is overwritten and deleted by every invocation. Overlapping controllers could validate another candidate and remove another run's state. Verify the enclosing deployment lock; if concurrency is permitted, use unique stages and serialized publication, with an interleaved rotation test.

**Confidence / effort / fix risk:** MED pending enclosing serialization / S/M / LOW/MED.

### I10 — P3 — Naive cannot express independent multiple-device credentials

**Evidence:** `ansible/roles/naive/templates/Caddyfile.j2:31`.

The role and schema expose one global credential pair despite guidance against sharing across clients. A per-device list and issuance/revocation contract would enable independent access. Test removing one device without disrupting another. No deployed shared credentials were observed.

**Confidence / effort / fix risk:** HIGH capability limitation; no observed reuse / M / MED.

### I11 — P3 — Policy tailing does not recover from same-inode truncation

**Evidence:** `ansible/roles/policy-ratelimit/templates/policy-ratelimit.py.j2:230-246`.

The read offset resets only after inode replacement. Manual truncation or an externally installed copytruncate policy loses inputs until file size overtakes the old offset. The repository's own rotation uses rename/create, so this is a robustness opportunity, not its current rotation behavior. Test same-inode truncation and inode replacement separately.

**Confidence / effort / fix risk:** HIGH conditional source defect / S / LOW.

### I12 — P3 — Failed dead-man recovery notification is not rescheduled

**Evidence:** `ansible/roles/observability_deadman/files/observability-deadman.py:753-775,778-793`.

Incident state is cleared before recovery delivery succeeds; completion clears the pending event even on failure. With fresh pulses and a recent successful canary, recovery is not retried after the reminder interval. Persist notification intent separately from incident health. Test failed recovery followed by fresh pulses and eventual one-time recovery delivery.

**Confidence / effort / fix risk:** HIGH reproduced / S/M / MED.

### I13 — P3 — Honeypot event totals are sampled but described as total volume

**Evidence:** `ansible/roles/honeypot/templates/honeypot.py.j2:174-190`; `ansible/roles/honeypot/defaults/main.yml:24-29`.

The event cap returns before incrementing minute and total counters, contradicting the default's claim that counts include every event. Either count observations independently of bounded logging, expose a dropped/sampled count, or label the metric as sampled. Test traffic above the event cap while retaining bounded logs.

**Confidence / effort / fix risk:** HIGH / S / LOW.

### I14 — P3 — Monitoring accepts an unrestricted listener override without preflight

**Evidence:** `ansible/roles/monitoring/tasks/main.yml:17-28`; `ansible/roles/monitoring/defaults/main.yml:3`.

The private-binding requirement is only a default; the supplied listener is copied directly. Add a fail-before-write private-listener contract consistent with the supported loopback/Tailnet boundary and sender scrape target. Test wildcard/public rejection and approved addresses. This is a misconfiguration guard, not evidence of public metrics on the fleet.

**Confidence / effort / fix risk:** MED defensive contract gap / S / LOW/MED.

### I15 — P3 — Opt-in audit severity gate does not require successful collection

**Evidence:** `ansible/roles/security_audit/tasks/lynis.yml:9-24,43-50`.

The optional high-findings assertion searches stdout but accepts unavailable or failed scanning with empty output. Default non-blocking reporting is documented and should remain. If the opt-in gate is meant as acceptance, distinguish scan-unavailable from no-high-findings and verify actual Lynis warning output before changing detection.

**Confidence / effort / fix risk:** MED improvement; non-blocking default is intentional / S/M / LOW/MED.

## Coverage

| Reviewer scope | Roles covered |
|---|---|
| Transport/runtime consumers | amneziawg, xray, xray-runtime, hysteria, hysteria-realm, naive, snell, dns-morph-bridge, reality-self-steal, probe-matrix-target, split-hop-egress, split-hop-ingress, cascade-egress, cascade-ingress, warp-outbound |
| Host/network/web/recovery | baseline, firewall, network-exposure-gate, tailnet-management, package_updates, intrusion_prevention, nginx-xhttp, subscription-host, cdn-front, geodata, backup, real-vps-awg-nat |
| Observability/runtime foundation | monitoring, honeypot, policy-ratelimit, watchdog, observability_agent, observability_control_plane, observability_deadman, runtime-release, security_audit, node_manifest |

Review covered root/subtree guidance; tasks, handlers, defaults, metadata where present; deployed scripts/configuration/service units; relevant Molecule scenarios and unit tests; and directly interacting site/listener/schema/firewall contracts. Supporting upstream checks were limited to exact runtime schema, signal, privilege and routing semantics needed to resolve findings.

No additional role-local defect was confirmed in the deliberately blocked cascade scaffolds, network-exposure-gate, runtime-release foundation, node_manifest, hysteria or Snell beyond the cross-role findings. This is not a defect-free certification. Runtime-release's ownership, receipts, descriptor-bound namespace checks and compensating publication are useful patterns to preserve. SSH transaction/recovery guards are substantially stronger than nginx/geodata's nontransactional publication.

## Observed validation

Five pytest batches produced **1,343 passing test executions and two environment failures**. These are execution counts, not a claim of unique test IDs or full-repository coverage.

| Batch | Outcome | Time |
|---|---|---|
| Watchdog, monitoring, honeypot, policy detector, node manifest, agent adapters/render | 153 passed, no skips | 29.58s |
| Firewall/baseline/geodata/CDN/subscription/backup/Tailnet | 157 passed | 63.33s |
| SSH transactions, Tailnet firewall sets, exposure gate, recurring AWG provisioning | 448 passed | 47.73s |
| Transport lifecycle/configuration/pinning/probe/Snell | 63 passed | 34.91s |
| Dead-man, receiver/alerting/gateway/protocol adapters/runtime-release | 522 passed, 2 environment failures | 488.18s |

The last command accidentally included the explicitly Linux `native_runtime` cases instead of using the portable marker selection. Their observed failures are reported, not suppressed:

- `test_observability_telegram_delivery.py::test_alertmanager_v0281_enforces_the_webhook_request_timeout`: `ALERTMANAGER_BIN` absent.
- `test_observability_protocol_liveness_adapter.py::test_adapter_accepts_shared_textfile_directory_and_publishes_collector_readable_output`: unprivileged Mac cannot set supplementary groups/UID/GID; reader subprocess returned 77 (`capability-unavailable`).

No product regression is inferred from those two platform failures. Exact Linux runtime acceptance remains required.

Other observed checks:

- Repository-configured offline `ansible-lint`: production profile passed, **0 failures / 0 warnings**, 482 files processed / 535 encountered. The first invocation lacked repository role/config paths and failed role discovery; rerunning with the correct environment resolved that setup error.
- `mise exec -- python3 scripts/render-snapshots.py`: **139 templates matched committed goldens**.
- Local exact `ansible.builtin.tempfile --check` probe: skipped, corroborating F33's missing candidate path.
- Isolated checks: subscription revocation startup reset, real-restic missing input, Tailnet check-mode parsing, partial geodata pair, invalid AOP PEM, policy history retention, metric temporary symlink, dead-man TLS accept and generation mismatch/reset, malformed protocol evidence, failed recovery retry behavior.
- Synthetic self-steal TLS identity check accepted the correct hostname and rejected the wrong hostname.
- No full `make check`, live acceptance, or full Molecule matrix was claimed. Docker daemon at the local Colima socket was unavailable. Linux systemd/network namespaces, real pinned Realm execution, client-path transport behavior, public firewall reachability, backup remote acceptance, and notification human receipt were not established.

### Exact pytest commands

Run from the repository root with the pinned mise Python. Commands below record what was observed, including the final command's native-runtime selection mistake.

```sh
mise exec -- python3 -m pytest -q -p no:cacheprovider tests/unit/test_policy_ratelimit.py tests/unit/test_watchdog_protocol_probe.py tests/unit/test_watchdog_templates.py tests/unit/test_xray_observability.py tests/unit/test_monitoring_logrotate.py tests/unit/test_honeypot_log_rotation.py tests/unit/test_honeypot_rolling_metrics.py tests/unit/test_honeypot_dual_stack.py tests/unit/test_honeypot_connection_deadline.py tests/unit/test_node_manifest.py tests/unit/test_observability_agent_adapter.py tests/unit/test_observability_agent_health_adapter.py tests/unit/test_observability_agent_health_render.py tests/unit/test_observability_agent_render.py --fail-on-skip

mise exec -- python3 -m pytest -q tests/unit/test_firewall_egress_policy.py tests/unit/test_baseline_sysctl_recovery.py tests/unit/test_baseline_vps_packages.py tests/unit/test_geodata_activation.py tests/unit/test_cdn_prefix_refresh.py tests/unit/test_subscription_mirror.py tests/unit/test_subscription_expiry.py tests/unit/test_backup_stage_status_contract.py tests/unit/test_backup_restore_drill_contract.py tests/unit/test_tailnet_management.py

mise exec -- python3 -m pytest -q tests/unit/test_sshd_transaction.py tests/unit/test_sshd_bundle.py tests/unit/test_sshd_migrate.py tests/unit/test_sshd_ownership.py tests/unit/test_firewall_tailnet_sets.py tests/unit/test_network_exposure_gate.py tests/unit/test_real_vps_awg_nat_provisioning.py

mise exec -- python3 -m pytest -q tests/unit/test_amneziawg_reload_contract.py tests/unit/test_amneziawg_check_mode.py tests/unit/test_transport_config_lifecycle.py tests/unit/test_probe_matrix_provisioning.py tests/unit/test_warp_pin_contract.py tests/unit/test_xray_xhttp_only.py tests/unit/test_snell_candidate.py

mise exec -- python3 -m pytest -q -p no:cacheprovider tests/unit/test_observability_deadman.py tests/unit/test_observability_deadman_pipeline.py tests/unit/test_observability_control_plane_generation.py tests/unit/test_observability_control_plane_render.py tests/unit/test_observability_telegram_delivery.py tests/unit/test_observability_silence_gateway.py tests/unit/test_observability_authority_snapshot.py tests/unit/test_observability_contract.py tests/unit/test_observability_protocol_liveness_adapter.py tests/unit/test_observability_control_plane_alerting.py tests/unit/test_observability_control_plane_expected_targets.py tests/unit/test_observability_topology.py tests/unit/test_runtime_release_contract.py tests/unit/test_runtime_release_consumers.py --fail-on-skip
```

For a portable rerun of the last batch, add `-m 'not native_runtime'`. To close its two gaps, use the repository's disposable Linux native-runtime lane with its pinned Alertmanager binary and UID/GID capabilities; do not run the entire workstation suite as root.

### Exact static commands

```sh
ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg" ANSIBLE_ROLES_PATH="$PWD/ansible/roles" ANSIBLE_COLLECTIONS_PATH="$PWD/.ansible/collections" mise exec -- ansible-lint --offline ansible/roles
mise exec -- python3 scripts/render-snapshots.py
```

## Recommended remediation order

1. Add behavior regressions and fix the small high-impact security/availability paths: F01–F10 and F44. Treat DNS, SSH authority and TLS changes as their documented lifecycle contracts.
2. Repair real candidate validation and socket contracts: F25, F28, F29, F11, F14. Realm must pass the exact native parser before rendezvous is credited.
3. Implement ownership-aware retirement and activation reconciliation: F15–F18, F26–F27, F31–F34. Cover enabled→disabled, pin-only, unit-only, rename and repeated convergence explicitly.
4. Add complete candidate publication/rollback for nginx, geodata and dead-man authority: F21–F22, F39–F41. Failure-path characterization must precede shared transaction refactoring.
5. Repair detector health/evidence and misleading fixtures: F19–F20, F23–F24, F35–F38, F42–F43. Accept split-hop only after I01/I02 real two-node packet evidence.

The long-term refactor worth the cost is one repository-owned nginx candidate/publication/rollback interface and one lifecycle state contract per role. The benefit is preventing the repeated validation-after-overwrite, missed activation and stale-disable failures. Its cost is a multi-role change plus Linux failure-injection coverage; it should follow targeted regressions, not replace the small urgent fixes with an untested rewrite. No implementation plans, portfolio items or lifecycle transitions were created by this audit.

## Considered and rejected / qualified

- Realm TLS staleness from missing Ansible notify alone was rejected: upstream TLS file-watch behavior prevents that conclusion without a specific event-path reproduction.
- Cascade's refusal-only/disabled scaffold is intentional and was not credited as runnable transport or reported as an accidental activation defect.
- Synthetic fixtures are appropriate for isolating role mechanics. The findings concern fixtures that accept unsupported native schema, cannot parse their own certificate, or assert behavior they create themselves.
- The site's protocol-aware collision preflight was preserved; F28 identifies a missing UDP declaration, not absence of a collision system.
- Policy detector same-inode truncation is I11, not the repository's current rename/create rotation. Idle freshness has a separate confirmed timestamp alert path in F35.
- Default non-blocking security_audit reporting is intentional. Collection-success semantics for the opt-in assertion remain I15.
- Standard proxy conventions, retained Prometheus TSDB on disable, default-off telemetry/research, per-device S3/S4 refusal and accepted runtime process-death boundaries were not treated as defects.
- Local dependency/runtime fixtures and passed static checks were not presented as fleet deployment, exact-pin transport acceptance, outside-in reachability or human notification receipt.
