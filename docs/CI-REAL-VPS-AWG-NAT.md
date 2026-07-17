# Recurring real-VPS AWG/NAT evidence lane

`.github/workflows/real-vps-awg-nat.yml` is a scheduled and manually
dispatchable data-plane gate. It runs on a dedicated Linux self-hosted
sentinel, connects to an owner-controlled real VPS, and fails when its private
runner contract is absent. Missing credentials or tools never become a green
skip.

The sentinel packages the exact checked-out commit with `git archive`. A
root-owned deploy hook must apply that archive to the persistent evidence VPS
through the repository's Ansible/SOPS path and return a strict receipt. The
lane rejects a server whose reported source SHA or archive digest differs from
the workflow run. The lane does not create or destroy VPS instances.

## What a PASS proves

The lane performs these operations in order:

1. Deploy the exact source archive and require matching server provenance.
2. Send exact-payload TCP and UDP round trips directly to owner-controlled
   echo services as a positive infrastructure control.
3. Create a disposable network namespace and real `amneziawg-go` client,
   then repeat both round trips through AWG.
4. Restart the VPS `awg-quick@` service, require a changed hashed systemd
   invocation ID with an unchanged config generation, wait for recovery, and
   repeat both round trips.
5. Prepare a new PSK generation transactionally, reload the server, require a
   changed config generation, and prove a fresh client using the old config
   cannot handshake or move evidence-peer/NAT counters.
6. Start the separately staged rotated client, require TCP and UDP recovery,
   fresh evidence-peer handshake/RX/TX, and NAT counter deltas, then atomically
   promote it to the next run's current config.
7. On any post-prepare failure, roll back and reload the previous generation,
   then require the previous client to recover before cleanup can be complete.
8. Stop packet capture and `amneziawg-go`, verify the namespace, interface,
   processes, scratch directory, source archive, and transactional server state
   are gone/finalized; hash three private PCAPs and the actual private event
   log before deleting them.

An exact echo round trip is bidirectional evidence: the request crosses the
AWG tunnel and server NAT, and the response returns through the same path.

## Private runner contract

The root-owned mode-0600 file `/etc/ripdpi/real-vps-awg-nat.json` has this
exact shape:

```json
{
  "version": "real_vps_awg_nat_runner_v1",
  "runnerId": "<64 random lowercase hex characters>",
  "clientConfigPath": "/etc/ripdpi/awg-evidence/current.conf",
  "rotatedClientConfigPath": "/etc/ripdpi/awg-evidence/rotated.conf",
  "clientAddress": "10.66.66.2/32",
  "tcpEchoAddress": "<owner-controlled numeric IP>",
  "tcpEchoPort": 10001,
  "udpEchoAddress": "<owner-controlled numeric IP>",
  "udpEchoPort": 10002,
  "serverControlHook": "/usr/local/libexec/ripdpi-awg-server-control",
  "serverDeployHook": "/usr/local/libexec/ripdpi-awg-deploy-source",
  "rotationHook": "/usr/local/libexec/ripdpi-awg-stage-rotation",
  "probeTimeoutSeconds": 10,
  "recoveryTimeoutSeconds": 90,
  "deployTimeoutSeconds": 900
}
```

Generate `runnerId` with `openssl rand -hex 32`. The two client configs must be
absolute, root-owned mode-0600 files, and each must contain exactly one
`PrivateKey` and one `PresharedKey`. All three hooks must be absolute,
root-owned mode-0700 executables. Both echo addresses must be globally routable
numeric IPs for owner-controlled echo services; they cannot be
private/documentation addresses or services local to the VPS. No endpoint,
key, PSK, client address, SSH alias, or raw hook output is published.

`serverDeployHook deploy SOURCE_TAR SOURCE_SHA ARCHIVE_SHA256` must verify the
archive digest, deploy that exact source through Ansible/SOPS, and emit only:

```json
{"deployedArchiveSha256":"<64 lowercase hex>","deployedSourceSha":"<40 lowercase hex>"}
```

`serverControlHook status` must emit only this JSON object:

```json
{"configGenerationSha256":"<64 hex>","deployedArchiveSha256":"<64 hex>","deployedSourceSha":"<40 hex>","interfaceUp":true,"latestHandshakeEpoch":0,"natBytes":0,"natPackets":0,"peerConfigSha256":"<64 hex>","peerRxBytes":0,"peerTxBytes":0,"serviceActive":true,"serviceInvocationSha256":"<64 hex>"}
```

The hook also accepts exactly `restart` and `reload`, performs those operations
against the dedicated VPS, and emits no output. It hashes the systemd
`InvocationID`, reports config generation and counters for the exact evidence
peer, and reads the NAT counter attached to nftables comment
`awg-nat-<interface>`. Exit 75 means infrastructure unavailable; any other
non-zero action result is a product/configuration failure.

`rotationHook prepare` stages the next server and client configs without
reloading and emits only:

```json
{"nextConfigGenerationSha256":"<64 hex>","nextPeerConfigSha256":"<64 hex>","previousConfigGenerationSha256":"<64 hex>","previousPeerConfigSha256":"<64 hex>","rotatedClientConfigSha256":"<64 hex>"}
```

`rotationHook commit` atomically promotes rotated client state to current;
`rotationHook rollback` restores the previous server/client state. Each emits
only:

```json
{"action":"commit","configGenerationSha256":"<64 hex>","currentClientConfigSha256":"<64 hex>","peerConfigSha256":"<64 hex>"}
```

`rollback` must be idempotent and safe even when `prepare` returned non-zero
or emitted a malformed receipt: the runner marks the transaction pending
before invoking `prepare` and always finalizes against its trusted pre-prepare
server/client baseline.

The runner independently hashes the client config and computes the peer config
fingerprint as SHA-256 over the ASCII domain separator
`ripdpi:awg-evidence-peer:v1:` followed by the single `PresharedKey` value. The
server hook must compute the same fingerprint for the evidence peer without
printing the key. Generations and invocation IDs are also published only as
domain-separated hashes.

## Result classification and artifacts

The uploaded artifact contains only canonical `manifest.json`:

- `PASS` means exact deployed-source provenance, all five phases, three PCAP
  digests, observed restart/reload generations, old-key rejection,
  transactional promotion, complete cleanup, fresh evidence-peer handshakes,
  positive peer RX/TX, and NAT deltas are complete.
- `PRODUCT_FAILURE` means the direct controls were healthy but AWG startup,
  exact-source deployment/configuration, restart, rotation/reload, handshake,
  NAT, or TCP/UDP recovery failed.
- `INFRA_UNAVAILABLE` means the private contract, privilege, tools, server
  deploy/control transport (hook exit 75), or direct echo controls were
  unavailable. Its fail-closed reason taxonomy distinguishes
  `MISSING_CREDENTIALS` (a current or rotated client config is absent or does
  not contain exactly one `PrivateKey` and `PresharedKey`) from
  `CONFIG_INVALID` (malformed runner JSON, unsafe paths, or missing hooks) and
  `PREREQUISITE_MISSING` (runner privilege, binaries, or source archive).

Both non-PASS classifications fail the workflow. Raw PCAPs, hook logs, config
paths, targets, and secrets stay on the runner and are deleted during cleanup.

## Local contract checks

```bash
python3 -m pytest -q \
  tests/unit/test_real_vps_awg_nat_lane.py \
  tests/unit/test_firewall_egress_policy.py
python3 scripts/render-snapshots.py
```
