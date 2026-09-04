# role: observability_agent — bounded outbound telemetry sender

## Design decisions

**The sender is a pinned Prometheus Agent runtime** — runtime-release verifies the exact archive before activation. Empty version, URL, checksum, or architecture pin is a hard failure; this role never selects a latest release.

**mTLS material crosses the service boundary through systemd credentials** — systemd copies the non-secret Prometheus configuration and its root-only CA, certificate, and key from one immutable generation into the authoritative `%d` credential directory. Prometheus loads `%d/prometheus.yml`, whose relative TLS paths resolve beside that configuration without a guessed `/run/credentials` layout, embedded secret, environment-file fallback, or invalid credential-directory chdir. The certificate subject must equal the configured technical node ID.

**The adapter consumes schema-2 node manifests only** — it exports a bounded, redacted manifest summary to node_exporter's existing loopback textfile path. It does not run watchdog, backup, or protocol probes.

**Producer health adaptation is a separate root oneshot** — root access is used only to read the watchdog and backup roles' fixed private state files. The adapter emits bounded one-hot state and timestamps into the protected textfile group; it never invokes or edits a producer.

## What's done well

- The remote-write URL is constructed as one node-bound HTTPS path and SNI is supplied separately, so DNS routing cannot silently change the mTLS name.
- Prometheus Agent is loopback-only, caps queue shards at four, and bounds WAL retention time.
- Disable removes the sender's unit, configuration, credentials, adapter, and WAL without taking ownership of node_exporter, watchdog, or producer files.

## Pitfalls

- This role needs the monitoring and node_manifest producers to have converged before it runs; site ordering is intentionally owned by a separate change.
- Do not widen the metric regex or add a telemetry fallback without the metric contract and ingestion role changes.
- Watchdog recovery is inferred only from its canonical consecutive-failure and hourly kick counters; it is local recovery evidence, never outside-in client-path recovery.
- `LoadCredential` source files are root-only input to systemd; do not replace it with an EnvironmentFile or put PEM content into the Prometheus template.
