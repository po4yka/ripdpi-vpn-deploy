# observability_kuma — independent private observer

## Design decisions

- This role runs only on one explicitly admitted existing independent host. It
  installs no Docker, nginx, age, firewall, private-network enrollment, or VPN
  baseline. Missing existing dependencies or separate private backup storage
  fail admission before convergence.
  Both the canonical playbook and isolated operator inventory use the
  `observability-kuma` group; the role rejects membership in the VPN group.
- Uptime Kuma 2.5.5, stable release dated 2026-09-16, uses the upstream
  `2.5.5-slim-rootless` architecture manifests. Defaults pin the verified linux
  amd64 and arm64 image digests, never a floating tag. Image updates require a
  quiesced encrypted backup before switching the container image.
- The container exposes port 3001 only through host loopback 13001. Existing
  authenticated operator access (for example an existing SSH tunnel) is required
  for the upstream setup/login UI. Do not expose that port, websocket endpoint,
  setup, or status pages to senders. The private IP:9444 vhost admits exact node
  source addresses and only GET `/api/push/<token>` without query parameters.
- Configure monitors through the pinned upstream authenticated UI; do not write
  SQLite or add a third-party provisioning dependency. Create one node monitor
  per enrolled node plus one pipeline and one delivery monitor: five for three
  nodes, twelve for ten. Set a distinct random 20–128-character URL-safe token
  through the authenticated editor and save it in its matching SOPS
  `push_monitors` entry. The role does not claim the monitors are configured.
- In the UI set node/pipeline heartbeat interval 120 seconds, retries 0, retry
  interval 120 seconds; delivery interval/retry interval 540 seconds, retries 0.
  Disable upside-down and maintenance for these monitors. Select the native
  Telegram integration using the distinct secondary credential for every
  monitor. Set repeat notifications to three failed checks (not three seconds).
  Missing-signal timing and repeats must be observed on the pinned runtime;
  configuration alone cannot establish the 180/600-second acceptance bounds.
- Producers include `tasks/producers.yml` on enrolled hosts and consume
  systemd credentials. Node producers require every declared local service;
  pipeline producers require fresh expected node scrapes, Alertmanager scrape,
  healthy recent rule evaluations, and a newly consumed relay canary receipt.
  Delivery producers call the real relay canary and require an increasing edit
  sequence plus a fresh daily send receipt. No cached success extends freshness.
- Success requires exactly the upstream JSON `{"ok": true}`. HTTP 200 alone,
  a status page, redirect, stale receipt, failed service or missing target cannot
  produce a success heartbeat. The observer CA verifies the private IP SAN.
- Aggregate producers run in `observability-agent.slice`; producer convergence
  installs and activates that bounded slice before any timer, including a
  collector-first installation without a running agent. The observer container
  is limited to 512 MiB, 0.25 CPU, 128 processes and no swap. Application
  logs are disabled (zero retained bytes) because database/notification errors
  could contain secrets. nginx suppresses both access and request-bearing error
  logs for only this vhost. Producer errors are categorical.

## What's done well

- TLS certificate/key and vhost are published as one validated generation.
  Shared nginx configuration is checked before reload; previous ingress links
  survive a failed activation. No unrelated default or VPN site is removed.
- Data and backups are secret material. Daily backup stops the role-owned
  service, archives the whole data directory including any SQLite WAL files,
  encrypts the stream with age directly to separate existing storage, and
  restores the previous running state even on failure. The manifest retains
  the matching architecture-specific image and ciphertext checksum.
  Disable stops the backup timer and active backup before the final observer
  stop, so a backup cannot restart an intentionally disabled observer. Rotation
  also quiesces both backup units before changing image/configuration and only
  restarts the timer after successful convergence; failure leaves it stopped.
- Restore consumes an explicit backup ID and a systemd `age-identity`
  credential. It rejects archive traversal, links and special files, bounds
  extracted size to 3 GiB, creates a unique data directory, and starts a
  `--network none` instance without published ports. The actual application
  JSON endpoint is verified before stopping it. Both datasets are retained.
  Extraction keeps directories root-owned until all writes finish, then changes
  ownership bottom-up; the restore unit deliberately lacks CAP_DAC_OVERRIDE.
- `molecule/runtime/run.py` is an explicit build-gated disposable Docker test,
  not a live provisioner. It uses the image's bundled Socket.IO client with
  upstream setup/login/add events, checks early/late scheduler phases and the
  full delivery deadline, then checks restart persistence and age-encrypted
  offline restore with authenticated monitor reads. It removes only its own
  uniquely named test containers, volumes and ephemeral keys.

## Pitfalls

- Source tests, API acknowledgement and configured notification credentials do
  not prove human receipt, independent-host admission, VPN performance, or
  production delivery. A healthy process is not an alert evaluator witness.
- Application database encryption is not provided by SOPS. Keep the live data
  directory and any isolated restore directory private; backup encryption
  protects only the backup. Never run both restored and original monitors with
  outbound access. A container downgrade does not downgrade the database.
- The restore unit intentionally requires an operator-provisioned private
  `/etc/observability-kuma/restore-age-identity`; this role never creates a
  decryption identity. Invoke `observability-kuma-restore@<backup-id>.service`
  only after the separate credential and restore action is authorized.
- Both Telegram integrations still share Telegram. A send-only defect can take
  26 hours plus the delivery detection window to be noticed. Both observer and
  collector loss means no guaranteed notification. A private-path outage is not
  proof that the VPN protocol is down.
- Container filesystem quota is not claimed: the role admits 3 GiB allowance
  plus max(5 GiB, 20%) free reserve and requires measured storage behavior.
  Failed actual capacity/load/restart tests stop deployment, never raise limits.
- Production monitor setup, missing-push drills, credential rotation, actual
  secondary delivery and human receipt remain separately authorized acceptance.
