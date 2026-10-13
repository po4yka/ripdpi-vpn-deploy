# role: observability_agent — bounded outbound telemetry sender

## Design decisions

**Exporter installation and scrape consumers share one endpoint guard** — the
monitoring role's literal private-address validator runs before standalone sender
mutation too. Both node-exporter jobs consume its normalized endpoint, including
bracketed IPv6 and explicitly approved, locally assigned Tailnet addresses.

**Binary changes activate immediately** — capture the runtime-release result before configuration work, include it in restart selection, and restore the captured release link before restarting the old generation after failed acceptance. `site.yml` always enters this lifecycle so enabled-to-disabled transitions reach cleanup.

Before changing the sender runtime contract, inspect its [cross-role and operator consumers](../../../scripts/DESIGN-NOTES.md#observability--observability-operatorpy).

**The sender is a pinned vmagent runtime** — runtime-release verifies the exact stable community archive before activation. Empty version, URL, checksum, or architecture pin is a hard failure; this role never selects a latest release. Prometheus remains the collector; the sender forces the Prometheus remote-write wire protocol.

**Different binaries have disjoint release authorities** — vmagent uses `/opt/observability-vmagent`; the historical Prometheus agent's `/opt/observability-agent` remains untouched. Reusing one `current` release symlink would invalidate the old binary's public link and make failed-cutover rollback impossible. Disable removes only the vmagent authority.

**mTLS material crosses the service boundary through systemd credentials** — systemd copies the non-secret scrape configuration and its root-only CA, certificate, and key from one immutable generation into the authoritative `%d` credential directory. vmagent reads the scrape file and explicit TLS flags from that directory without a guessed `/run/credentials` layout, embedded secret, or environment fallback. The certificate subject must equal the configured technical node ID.

**The adapter consumes schema-2 node manifests only** — it exports a bounded, redacted manifest summary to node_exporter's existing loopback textfile path. It does not run watchdog, backup, or protocol probes.

**Producer health adaptation is a separate root oneshot** — root access is used only to read the watchdog and backup roles' fixed private state files. The adapter emits bounded one-hot state and timestamps into the protected textfile group; it never invokes or edits a producer.

**Producer deadlines belong to central evaluation** — health adaptation publishes
bounded producer timestamps and their configured maximum ages, including restore
snapshot age, separately from its 180-second completion heartbeat. The collector
compares these clocks to evaluation time; renewed scrapes of an unchanged
textfile cannot renew producer evidence. Missing/future deadline pairs remain
unavailable. Private watchdog input is the canonical owner-private `0600` budget;
malformed scalar backup results and restore sources publish collection failure
rather than retaining old success.

**Required services follow the effective profile** — the health adapter publishes
reviewed unit expectations independently of discovered systemd units. Xray is
required for REALITY or XHTTP; subscription-only suppresses transports and
requires nginx. The policy selector is bounded to the supported service catalog
and intersected with these effective flags. Collector rules distinguish absent
unit evidence from an observed inactive/failed unit, without letting another
healthy service approve the missing pair.

## What's done well

- The remote-write URL is constructed as one node-bound private-IP HTTPS path; the identical literal IP is verified against the server IP SAN, without DNS routing or TLS bypass.
- vmagent is loopback-only, uses one worker, disk persistence and no in-memory bypass. The configured queue budget is 512 MiB without an age discard; pinned native chunk rounding adds 128 bytes to the effective logical bound. Queue eviction counters remain visible. Scrapes are every 60 seconds; the total 2,000-sample allowance is split 1,800 host + 150 required-service + 50 self metrics. Push status retains only bounded kind labels.
- Queue admission reserves 2 GiB of physical allocation plus the host reserve. On a shared collector filesystem it also protects the collector's remaining 2 GiB allowance and measured stop headroom; a historical guard without the shared-budget contract fails closed. Logical queue size is not a filesystem quota.
- A root-only receiver binding prevents silently draining a retained queue to another endpoint; changing a receiver requires explicit queue disposition. Dangling queues are preserved. Activation failure restores exact previous unit bytes and probes its captured runtime and loopback listener, or leaves an incoherent/previously disabled runtime stopped.
- Readiness belongs to the managed MainPID, not merely a port: its exact executable and loopback LISTEN socket inode are checked before and after HTTP 200, with stable PID/start-time identity. A competing healthy listener cannot approve a failed candidate or rollback.
- Sender, adapters and heartbeat producers share `observability-agent.slice`: 192 MiB, 10% CPU, IOWeight 10, no swap. VPN units and exporters are not moved into this slice.
- The variable-free `resource-boundary` entry point installs and activates the slice before either the sender or independent collector producers start, including collector-first convergence.
- Disable removes sender units and adapters but retains credentials, configuration, the persistent queue and historical WAL for explicit recovery, without taking ownership of node_exporter, watchdog, or producer files.
- Disable inspects exact owned unit files and stops timers and in-flight adapter services before removing binaries; a stop failure aborts removal.

Sender activation now uses the shared exact-inode publisher and staged runtime acquisition. Its private helper holds one activation lock through graceful stop, bounded native queue snapshot, selector publication, actual MainPID/executable/socket readiness and durable receipt commit. Failure or interruption restores queue bytes in place before the prior sender starts; repeated stops never overwrite the original copy. A root admission drop-in blocks unresolved publication without its live writer. Snapshot cleanup follows durable acceptance or confirmed compensation and records partial-cleanup debt. Working queue and snapshot share a filesystem and each fit 1 GiB under the existing 2 GiB admission; unknown layouts, mounts, foreign nodes and insufficient reserve refuse. The native budget profile is v1.153.0, one receiver, 512 MiB native queue, one worker, no memory queue and 1 MiB unpacked blocks. A future pin/profile change requires its budget derivation and native historical proof. Disable reconciles and retires accepted selectors before removing credential/release directories; queue and receiver binding remain retained.

The staged selection includes its previous-runtime link when supplied by runtime-release. It participates in exact compensation with the other selectors. Refusals return fixed categorical JSON without exposing private requests; Ansible never parses success fields after an unsuccessful helper exit.

- Staged executable admission has a distinct 128 MiB ceiling and requires a root-owned, single-link 0755 regular file. The shared publisher metadata-node ceiling is not an executable limit; applying it to vmagent rejects valid acquired binaries before activation.

## Pitfalls

- Pinned atomic queue writes can leave `metainfo.json.tmp.<uint64>` (at most 16 KiB) or an empty `0000000000000000.tmp.<uint64>` initial chunk. Preserve these exact private native forms through compensation under the existing count/copy budget. Readiness retries only a live inode-change race within its deadline; quiescent snapshots and foreign-authority refusals remain strict.

- Install adapter executables and queue their timer restart notifications only after durable sender acceptance. Ansible flushes notifications from rescued role attempts; a rejected first cutover must not restart adapters whose units have not been installed.

- Read-only helper admission loads shared source from bounded trusted stdin. Concatenating escaped newlines inside an Ansible expression produces literal backslashes and can prevent every role invocation from reaching activation.

- The outer failure boundary preserves the originating task name without exposing module output. Failure-injection acceptance requires the inner activation-refusal boundary plus successful restored-runtime readiness, so a preflight failure cannot impersonate a tested rollback.

- Runtime acquisition is staged. The shared publisher owns binary, credential selector and primary unit compensation; outer rescue reports the originating task without recreating exact restored selector inodes.

- Failed-activation acceptance forwards bounded mTLS payloads to a separate
  loopback Prometheus fixture using the already verified historical binary.
  The receiver accepts reordered blocks within its finite retention window:
  stopping the pinned sender can return its unsent worker block after later
  persisted blocks. The fixture uses the same policy with its one-hour retention;
  production uses seven days. Older history remains outside that window.
  It removes its unique probe before cutover and requires the exact node,
  nonce and pre-cutover sample timestamp from a bounded raw range vector after
  rollback. An instant selector can hide retained samples behind a concurrent
  stale marker when the probe is removed; queued depth can be
  zero while a retry worker holds an unsent block and is not delivery proof.
- Historical rollback failure captures bounded fixture-only query cardinalities,
  node/job categories, nonce/window matches, native sender counters and receiver
  phase counts before retirement. Handler errors add a fixed processing stage,
  backend HTTP status, bounded response category and protocol-header categories;
  backend bodies are inspected only up to 4096 bytes. Endpoint labels, raw
  payloads, header values and exception text stay out of this report. Diagnosis preserves the exact sample assertion
  and its failure; fixture cleanup and receiver restoration run even if evidence
  collection fails. Generic queued blocks alone do not establish nonce capture.
- Restart acceptance must recover exact historical samples after both clean stop and SIGKILL once persistence is observed. Retaining files, a queue-depth decrease, or fresh samples after restart cannot establish recovery. Host power-loss/fsync durability is not implied by a process-kill test.
- This role needs the monitoring and node_manifest producers to have converged before it runs; site ordering is intentionally owned by a separate change.
- Do not widen the metric regex or add a telemetry fallback without the metric contract and ingestion role changes.
- The strict native scrape parser does not support Prometheus label-name/value-length YAML keys. Apply the same bounds through native `maxLabelNameLen`, `maxLabelValueLen` and `maxLabelsPerTimeseries` flags; rejected series increment the bounded `vm_rows_ignored_total{reason}` self metric. Never disable strict parsing.
- Watchdog recovery is inferred only from its canonical consecutive-failure and hourly kick counters; it is local recovery evidence, never outside-in client-path recovery.
- `LoadCredential` source files are root-only input to systemd; do not replace it with an EnvironmentFile or put PEM content into the Prometheus template.

- Check mode runs read-only contract and capacity probes before predicting
  publication. It never creates a private credential candidate, activates units,
  or consumes stdout from commands skipped by Ansible check mode. Native candidate
  validation and readiness still run in ordinary convergence before acceptance.

Disable retires the sender's credential generations after stopping its units.
The persistent queue and its root-private receiver binding are retained together
so a later enable cannot silently reroute retained samples to another receiver.
