# Audit: silent-failure on an unverified or unstable external contract

Status: audit completed 2026-06-11; current dispositions reviewed 2026-07-26
Method: multi-agent audit, one analyst per control plus an independent adversarial verifier per verdict. Upstream behaviour (Xray-core, sing-box, restic, rclone, openssl, check-host.net, node_exporter) verified against source/docs, not assumed.

> Historical audit snapshot. The verdicts below describe the 2026-06-11 code,
> not the current implementation. As of 2026-07-26, policy-ratelimit is
> explicitly scoped away from REALITY probe defence; authenticated protocol
> liveness is a separate sentinel contract; kill-switch route/direct and
> address-family leaks are tested; the monitoring textfile collector is wired;
> backup has recency checks and an isolated restore drill; certificate
> matching compares DER public keys; and `burn-check.sh` replaces stale
> reachability metrics with explicit error gauges on every exit. Preserve the
> original findings below as the rationale for those controls.

## Failure class

A control is in scope if its effectiveness depends on something it does **not itself verify** — a third-party log-string format, a tool's exit code, a file's presence, a parsed field, an upstream tool's behaviour — **and** its failure mode is **silent**: the service stays active/listening, metrics look healthy, but the control does nothing.

Every control examined under this lens failed. The shared root cause is a coupling to an external contract that was assumed rather than asserted, with no canary that fires when the coupling is wrong. A counter pinned at zero, an `exit 0`, or a never-written textfile all read as "healthy / nothing to report" instead of "detector is dead."

## Audit-date verdict summary

| # | Control | Contract it silently depends on | Verdict | Conf. | Cross-check |
|---|---------|--------------------------------|---------|-------|-------------|
| 1 | `policy-ratelimit` daemon (`ansible/roles/policy-ratelimit/templates/policy-ratelimit.py.j2`) | Xray access.log emits `REJECT`/`rejected`/`graylist` for probers or blackholed traffic | **BROKEN** | high | agreed |
| 2 | `watchdog` transport-liveness (`ansible/roles/watchdog/templates/vpn-watchdog.sh.j2`) | A live local socket implies a working REALITY transport end-to-end | **BROKEN** | high | agreed |
| 3 | `watchdog` `active_probing` class (same file, lines 84-90) | Same `REJECT|graylist` grep on access.log | **BROKEN** | high | agreed |
| 4 | `check-singbox-killswitch.py` (K1-K5) | Only `route.final` reaches direct egress; TUN family coverage need not be checked | **BROKEN** | high | agreed |
| 5 | `honeypot` detection pipeline (`honeypot.py.j2` → `probing-summary-remote.py` → `monitoring`) | Textfile is scraped, an alert rule exists, a consumer pages on a spike | **BROKEN** | high | agreed |
| 6 | `backup` role (`ansible/roles/backup/templates/vpn-backup.sh.j2`) | `restic backup` exit 0 ⇒ restorable repo; `rclone size` ⇒ today's snapshot uploaded | **BROKEN** | high | agreed |
| 7 | `check-certs.sh` modulus match | `openssl rsa -modulus` yields a comparable value for the served key | **BROKEN** | high | agreed |
| 8 | `burn-check.sh` metrics freshness | An early `exit 2` still leaves a fresh/alertable textfile signal | **BROKEN** | high | agreed |

Seven controls, eight findings (watchdog splits into two). All `BROKEN`. No `VERIFIED`, no `UNVERIFIABLE-WITHOUT-LIVE-NODE` — every verdict was statically decidable from repo + upstream source. The seed hypothesis is **confirmed and generalizes**: the `REJECT|graylist` log-token coupling is dead in two places, and the same "trust an unverified external contract, fail silent" pattern recurs across detection, verification, and backup controls.

## Current disposition

`BROKEN` elsewhere in this document is the audit-date verdict. This table is
the maintained current layer; code tests establish repository contracts, not
live production effectiveness.

| # | Control | Current status | Repository evidence |
|---|---|---|---|
| 1 | policy-ratelimit scope | **RESOLVED** | `policy-ratelimit.py.j2` now matches real blackhole/VLESS-reject signals, disclaims REALITY probe defence, and exposes a dead-contract gauge; `test_policy_ratelimit.py` pins the contract. |
| 2 | watchdog transport liveness | **RESOLVED** | Node-local authenticated completion is separated from the client-path quorum/OTP authority in `PROTOCOL-LIVENESS.md`; `test_watchdog_protocol_probe.py` covers the local probe. |
| 3 | watchdog log classifier | **RESOLVED** | Real block/rejected tokens and `policy_reject_spike` semantics replaced the false active-probing class; watchdog render tests pin it. |
| 4 | sing-box kill switch | **RESOLVED** | `check-singbox-killswitch.py` traverses route rules/groups, rejects direct/bypass resolution, and requires unified TUN address-family coverage; `test_check_killswitch.py` covers failures. |
| 5 | honeypot alert pipeline | **PARTIAL** | Monitoring now scrapes the shared textfile directory and reports/metrics exist, but threshold paging and alert routing remain operator-owned outside this repository. |
| 6 | backup integrity | **RESOLVED** | Backup runs integrity/recency/remote checks and a scheduled isolated restore drill; focused backup contract tests and Molecule exercise them. |
| 7 | certificate key match | **RESOLVED** | `check-certs.sh` compares key-type-independent DER public-key digests; `test_check_certs_key_match.py` prevents RSA-only regression. |
| 8 | burn-check metric freshness | **RESOLVED** | An EXIT trap atomically rewrites the textfile on every path; API and incomplete-run gauges distinguish an indeterminate check from a healthy result. |

---

## 1. `policy-ratelimit` — log-token coupling is dead

**Current status: RESOLVED by scope correction and executable contract tests.**

**Contract.** The daemon tails `/var/log/xray/access.log` and bans IPs whose lines match `EVENT_RE = (REJECT|rejected|graylist)`. Effectiveness depends on Xray-core emitting one of those substrings for (a) external probers whose REALITY handshake fails, or (b) authenticated clients routed to the `block` blackhole.

**Contract owner.** Xray-core (XTLS/Xray-core). Version is operator-supplied (`ansible/roles/xray/defaults/main.yml` `version: ""`), so the relevant invariant is the access-log *line format*, which has been stable since the v2ray-core fork.

**Why it is BROKEN (source-level):**
- `common/log/access.go` defines exactly two status constants: `AccessAccepted = "accepted"` and `AccessRejected = "rejected"`. Neither is uppercase `REJECT`; `graylist` is not an Xray concept at all.
- Case (b) — blackholed traffic: `app/dispatcher/default.go` keeps `Status = accepted` and sets the detour to the outbound tag. The line is `from tcp:<IP>:<port> accepted tcp:<dest> [vless-reality -> block]`. The word `block` appears only inside the detour brackets; the status is `accepted`. `EVENT_RE` cannot match it. (config.json.j2:151 confirms the blackhole tag is literally `block`; BitTorrent/QUIC-443/RFC1918 route there.)
- Case (a) — REALITY handshake failure: `proxy/vless/inbound/inbound.go` forwards the failed handshake to `realitySettings.target` (steal-oneself) **before any `AccessMessage` is constructed**. No log line is written, so the daemon never sees external probers.
- `loglevel: "warning"` does **not** suppress access logs: `app/log/log.go` routes `*log.AccessMessage` unconditionally, gating only `*log.GeneralMessage` by severity. Loglevel is a red herring here — the token simply never appears.
- The only path that ever writes `rejected` is a post-TLS VLESS header parse failure (already-authenticated client sending a malformed header) — irrelevant to the prober threat model.

**Silent failure mode.** Daemon runs, counters stay at `vpn_policy_ratelimit_events_total 0` / `bans_total 0`, `policy_offenders` is never populated. An operator reads the zero as "no probing," not "detector dead." The role's `CLAUDE.md` ("per-IP rate limit on failed handshakes") describes a capability that does not exist.

**Remediation.**
- *Recommended (covers real probers):* move rate-limiting to nftables on the REALITY port, independent of any app log — e.g. `tcp dport 443 ct state new meter probe_meter { ip saddr timeout 60s limit rate over 20/minute } add @policy_offenders { ip saddr timeout 300s }`. This fires before REALITY runs, so it sees actual probers.
- *Partial (authenticated blackhole traffic only):* change `EVENT_RE` to match the real token, e.g. `re.compile(r"\[.*?->\s*block\]")`. Does **not** cover probers (no log line exists for them).
- Add a meta-alert: `vpn_policy_ratelimit_events_total == 0` for a long window should page "detector may be broken," not be read as quiet.
- Correct the role `CLAUDE.md` to state REALITY handshake failures are invisible to a log-tailer.

---

## 2 & 3. `watchdog` — process-liveness masquerading as transport-liveness, plus the same dead grep

**Current status: both findings RESOLVED.** Node-local authenticated checks and
client-path rotation authority are separate; the classifier uses real policy
rejection signals rather than claiming external probe visibility.

**Finding 2 — transport-liveness. Contract.** The probes (`systemctl is-active xray`, `ss -lnt | grep :PORT`, `xray run -test -config`, `</dev/tcp/127.0.0.1/PORT`) are assumed to prove the public REALITY transport works. The role `CLAUDE.md` claims "probes hit the public surface, not internals" — false.

**Why it is BROKEN.** None of the four probes performs a TLS/REALITY handshake. All four pass green when: the node's IP is blocked at transit; a rotated `privateKey`/`shortId` is in SOPS but not yet applied (old config still listening); or `realitySettings.target` is unreachable (probe-forwarding silently fails). `</dev/tcp/127.0.0.1/PORT` proves only that a socket accepts a TCP connection on loopback — it never sends a ClientHello. The verifier's strongest rescue (a crashed misconfig would not be listening) covers only process death, which `is-active` already covers redundantly; it does not cover the degraded-but-running modes that are the actual threat.

**Finding 3 — `active_probing` class.** Lines 84-90 grep the same access.log for `REJECT|graylist`. Identical analysis to control #1: the tokens never appear, so `recent_reject` is always 0 and the `active_probing` alert class never fires regardless of probe volume. (Verifier note: the dispatcher's separator is `->`, not `>>` as the analyst wrote — immaterial, since neither contains `REJECT`/`graylist`.)

**Silent failure mode.** Watchdog reports all-OK and never pages while real clients cannot connect; active-probing waves pass undetected. Two independent silent failures in one script.

**Remediation.**
- Add a real handshake probe against the public IP:443, minimum `openssl s_client -connect <ip>:443 -servername <server_names[0]> -brief` (proves TLS terminates); ideally a VLESS+REALITY check (candidate `vpnd probe` subcommand).
- Change the grep to a token Xray actually emits: `grep -c -E ' rejected | -> *block\]'` (lowercase, bracket-aware), and fix the `graylist` reference in `docs/RUNBOOK-incident.md`.
- Correct the role `CLAUDE.md` "public surface" claim.

**Resolution (2026-07-10).** The watchdog's local diagnostics and self-dial can validate node configuration but remain explicitly non-authoritative for transit reachability. `docs/PROTOCOL-LIVENESS.md` defines the separate rotation signal: managed client-path sentinels complete authenticated traffic through REALITY, XHTTP, Hysteria2, and AmneziaWG; an operator-side evaluator requires fresh direct controls, a configurable failed-vantage quorum, and three consecutive failures before issuing an environment- and policy-bound OTP. Unknown, stale, malformed, authentication, dependency, and sub-quorum results cannot trigger promotion, and the OTP is revalidated before the existing operator-confirmed blue-green flow starts.

---

## 4. `check-singbox-killswitch.py` — passes vacuously on the normal Android flow

**Current status: RESOLVED by fail-closed route-graph and address-family checks.**

**Contract.** The K1-K5 rules assume the only path to direct/cleartext egress is `route.final`, and that TUN address-family coverage need not be checked. Effectiveness depends on sing-box's documented behaviour: `route.rules[]` are evaluated before `route.final`, and `auto_route` only captures families with a configured TUN prefix.

**Why it is BROKEN (two leaks, both reproduced):**
- **Leak 1 — `route.rules[]` never read.** `check()` (lines 48-53) reads only `route.final`. `emit-singbox.sh --per-app-bypass` injects `route.rules[0] = {package_name:[...], outbound:"direct"}`. With `route.final == "select"`, K3 passes and the checker prints "OK" while every named Android app egresses in cleartext. This is the **normal operator flow**, not an adversarial edge case.
- **Leak 2 — IPv6 not checked.** The positive-case fixture `tests/fixtures/singbox-killswitch-valid.json` has only `inet4_address` on the TUN; `inet6_address` is never referenced by the checker. On any dual-stack device, IPv6 bypasses the tunnel and the checker still returns OK. The baseline "valid" fixture is itself IPv6-leaky.

The verifier's rebuttals (LAN exemption by design; Android-only; possibly-IPv4-only intent) all fail: the checker has no mechanism to assert any of those invariants, so it cannot distinguish a deliberate exemption from an accidental leak — both return OK. (Evidence gap noted: sing-box rule-ordering/TUN-family contracts are inferred from the `emit-singbox.sh` comments and routing-engine convention rather than a cited sing-box source commit; the *code-level* facts — checker never reads `route.rules[]` or `inet6_address` — are certain regardless.)

**Remediation.**
- Add K3b: iterate `route.get("rules", [])`; flag any rule whose `outbound` resolves to a direct-type egress (build the set of `type=="direct"` tags from `outbounds` and check rule outbounds against it). Add a negative test with an injected per-app-bypass rule.
- Add K1c: flag a TUN inbound with no `inet6_address`; give the fixture a real `inet6_address` so the baseline is non-leaky.

---

## 5. `honeypot` — listens, counts, and notifies no one

**Current status: PARTIAL.** Textfile collection and writer access are repaired;
threshold paging and alert routing remain an explicit operator-owned boundary.

**Contract.** Four stacked contracts must all hold for a probe spike to reach a human: (1) node_exporter scrapes `/var/lib/node_exporter/textfile`; (2) a Prometheus server + alert rule fires on `vpn_honeypot_*`; (3) `probing-summary-remote.py` notifies on a threshold; (4) the operator cron produces an active alert, not a passive log line.

**Why it is BROKEN — all four fail independently:**
1. `ansible/roles/monitoring/tasks/main.yml:21-24` sets node_exporter `ARGS` to `--web.listen-address=… --collector.systemd --collector.processes --no-collector.wifi`. **No `--collector.textfile.directory`.** The honeypot writes to `/var/lib/node_exporter/textfile` (a non-default path); the metrics are never scraped.
2. No Prometheus server, alert rule, or alertmanager exists anywhere in the repo (`find … -iname '*.rules*' -o -iname 'alertmanager*'` → empty). `monitoring/CLAUDE.md` confirms "No alerting included — by design."
3. `scripts/probing-summary-remote.py` `main()` unconditionally `return 0` (line 204); no threshold check, no notification call.
4. `install-operator-crons.sh` runs `make probing-summary 2>&1 | logger -t vpn-probing` — output swallowed by syslog, no exit-code gate, and the cron is opt-in (manual install on a workstation).

**Silent failure mode.** Honeypot accepts connections, increments counters, writes its textfile — `systemctl status honeypot` is green — while no metric reaches a scraper and no human is ever paged. Detection produces a report someone must remember to open.

**Remediation.** Close all four: add `--collector.textfile.directory=/var/lib/node_exporter/textfile` to the node_exporter ARGS; add a threshold + ntfy/Pushover call (reuse the watchdog's path) in `probing-summary-remote.py`; gate the cron on a threshold exit code; ideally ship a Prometheus rule (`vpn_honeypot_events_60min > threshold`) so the alert path is infrastructure, not operator discipline.

---

## 6. `backup` — fire-and-forget; no integrity check, no recency check

**Current status: RESOLVED by integrity, recency, remote, and isolated restore-drill contracts.**

**Contract.** `restic backup` exit 0 ⇒ a consistent, restorable repository; `rclone size <remote> >/dev/null` exit 0 ⇒ today's snapshot was transferred.

**Contract owner.** restic and rclone — neither version-pinned (`apt: state: present`).

**Why it is BROKEN:**
- `restic backup` verifies only the pack files it writes *this run*; it does **not** re-verify pre-existing packs, index cross-references, or prior-snapshot trees. A disk-full or interrupted write can exit 0 with an inconsistent repo. `set -euo pipefail` cannot catch what restic reports as success. There is **no `restic check`** anywhere in `ansible/` or `scripts/` (confirmed: zero matches).
- `rclone size` reports aggregate byte count for whatever is at the path and exits 0 if the path is reachable — it never inspects modification time or snapshot recency. A stale 6-month-old remote copy passes. The inline comment "Verify the remote copy exists and is non-empty for today's snapshot" (vpn-backup.sh.j2:41) is incorrect.
- No automated `restic check` or restore test in cron, systemd, molecule, or CI. `RUNBOOK-restore.md` documents a manual quarterly dry-run — prose guidance, not an enforced control.

**Silent failure mode.** `vpn-backup.timer` shows green daily; the repo may be silently corrupt or the remote silently stale; discovered only at restore time, after a node has burned.

**Remediation.** Add `restic check` after `forget --prune` (fails the unit on corruption); add weekly `restic check --read-data-subset=10%` on a separate timer; replace the `rclone size` block with a recency assertion — `restic -r rclone:<remote> snapshots --last 1 --json | jq -e '.[0].time > (now - 86400)'`; automate a `restore latest --dry-run` verification on a weekly timer.

---

## 7. `check-certs.sh` — EC cert/key mismatch is structurally undetectable

**Current status: RESOLVED by key-type-independent public-key digest comparison.**

**Contract.** The modulus guard `if [[ -n "$cm" && -n "$km" && "$cm" != "$km" ]]` (line 101) depends on `openssl rsa -noout -modulus` (line 100) producing a comparable value for the served key.

**Why it is BROKEN (empirically proven in-session):**
- The stack serves **EC** certs (acme.sh v3+ defaults to P-256; `ansible/molecule/full-stack/test-secrets.yaml` labels material "Real ECDSA P-256"; the nginx cipher list leads with `ECDHE-ECDSA-*`; no `--keylength rsa:` anywhere).
- For an EC key, `openssl rsa -noout -modulus` exits 1 (suppressed by `|| true`) → `km` is **empty**. But `openssl x509 -noout -modulus` on an EC cert exits 0 with the non-empty string `Modulus=No modulus for this public key type` → `cm` is **non-empty**. The guard requires both non-empty, so it is **permanently disabled** for the production cert type. A cert paired with an entirely wrong EC key passes "OK — certs healthy."
- The author anticipated EC partially (comment line 97) but wrongly assumed `cm` would also be empty.
- Secondary checks confirmed *not* silent: date parse handles space-padded days; missing CA-chain verification is a documented scope limit; SAN wildcard regex is correct for single-level.

**Silent failure mode.** `check-certs.sh` and `make verify` pass; nginx then fails every TLS handshake at runtime (process up, port open, all sessions broken).

**Remediation.** Replace the RSA-only modulus check with a key-type-agnostic public-key comparison:
```sh
cm="$(printf '%s\n' "$cert" | openssl x509 -noout -pubkey 2>/dev/null | openssl pkey -pubin -noout -text 2>/dev/null | sha256sum || true)"
km="$(printf '%s\n' "$key"  | openssl pkey -noout -pubout 2>/dev/null | openssl pkey -pubin -noout -text 2>/dev/null | sha256sum || true)"
[[ -n "$cm" && -n "$km" && "$cm" != "$km" ]] && report "cert public key does not match private key"
```
Works for RSA, P-256/P-384, and X25519. Update the line-97 comment.

---

## 8. `burn-check.sh` — early `exit 2` freezes the metrics at the last healthy state

**Current status: RESOLVED.** Every exit path now atomically refreshes the
textfile. `vpn_burn_api_error` reports check-host API failures,
`vpn_burn_run_error` reports a run that ended before classification, and
per-node/summary reachability series are omitted when no valid result exists.
Regression tests cover an API failure, a healthy result, and a completed
reachability failure so a burned-path verdict is not mislabeled as a probe
execution error.

**Contract.** On `exit 2` (check-host.net rejects the request / returns no `request_id`), the script terminates at line 43 — **before** the Prometheus textfile write block at line 74. Effectiveness depends on a downstream staleness alert on `vpn_burn_last_run_unixtime` to notice the freeze.

**Why it is BROKEN:**
- `curl -fsS` treats HTTP 429/4xx (check-host.net rate-limiting a cron) as a non-zero exit; `set -euo pipefail` aborts before line 74. `vpn_burn.prom` is never rewritten, so `vpn_burn_failed_nodes` and `vpn_burn_last_run_unixtime` retain their last *healthy* values (e.g. `0 failed`). node_exporter keeps exporting the stale green gauge. No `trap … EXIT` writes a sentinel.
- The assumed downstream staleness alert **does not exist** in the repo (no PrometheusRule, no `*.rules`, no reference to `vpn_burn_last_run_unixtime` outside the script). The only failure signal is `logger -t vpn-burn` in syslog, which has no automated path to anything.
- The pending-node jq logic is **correct** and not the bug: a `null` node yields `{}`, `select(.address==null)` is true, so pending nodes are conservatively counted as failures. (A separate tuning weakness — 1 of 3 RU nodes blocked with `FAIL_THRESHOLD=2` reports healthy — is noted but is configuration, not a contract breach.)

**Silent failure mode.** check-host.net rate-limits the cron; every subsequent run exits 2; the dashboard shows the IP reachable indefinitely while it may be burned.

**Remediation.** Add a `trap '_write_error_metrics' ERR EXIT` that always advances `vpn_burn_last_run_unixtime` and writes a `vpn_burn_api_error 1` gauge on abnormal exit (set `0` in the success path). Pair with a Prometheus rule `vpn_burn_api_error == 1 for: 35m` (just over the cron interval). This converts a silent freeze into an explicit, alertable error.

---

## Generalization & systemic recommendations

The eight findings share one shape: **a control trusts an external contract it never asserts, and its failure is indistinguishable from "all quiet."** Fixing the eight individually is necessary but not sufficient; the class will regrow without structural guards.

1. **Every counter that can read "0 = healthy" needs a liveness assertion.** `policy-ratelimit`, both watchdog signals, and the honeypot all present a dead detector as a quiet one. Add "this detector has seen at least one event in N days, or it is presumed broken" meta-checks, or inject a synthetic event on deploy and assert it is counted.

2. **Pin the upstream log/format contracts and test them.** The `REJECT|graylist` token is the canonical instance: it never matched any Xray release. A render-time or molecule test that feeds a known Xray access-log sample through the regex would have caught it. Do the same for any control that greps third-party output.

3. **Verification must exercise the real surface, not a proxy for it.** A loopback TCP open is not a REALITY handshake; `restic backup` exit 0 is not `restic check`; `rclone size` is not snapshot recency; `openssl rsa -modulus` is not an EC key comparison; a static `route.final` read is not a `route.rules[]` scan. Each fix replaces a proxy signal with a direct one.

4. **Make the alert path infrastructure, not operator discipline.** The honeypot and burn-check both terminate in `logger` with no automated escalation. "Alerting is operator-side" (monitoring/CLAUDE.md) means a real probe wave or a burned IP reaches no one unless someone proactively reads a report. At minimum, wire threshold-driven ntfy/Pushover (the watchdog already has the code) into the honeypot and burn-check paths.

5. **A skipped check must be loud.** The EC modulus guard and the burn-check early-exit both *skip silently*. Prefer fail-closed: when a check cannot run (EC key in an RSA-only path, API unreachable), emit an explicit "could not verify" finding rather than passing.

### Methodology note

This audit is static + source-verified; it did not run against a live node. Every verdict was nonetheless statically decidable — the failures are in code and upstream contracts, not in runtime tuning — so none were classified `UNVERIFIABLE-WITHOUT-LIVE-NODE`. Confirming the *fixes* (e.g. that an nftables meter actually bans a prober, or that a REALITY handshake probe distinguishes a blocked IP) will require a live node and is out of scope for this report, which audits only.
