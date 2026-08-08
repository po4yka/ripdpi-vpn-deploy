# Protocol-level liveness and rotation

Process state, a listening socket, and a bare TLS response do not prove that a real client can authenticate and carry traffic across a filtered path. Rotation uses a separate operator-side module that pulls authenticated data-plane probes from managed sentinels and requires sustained failure from a configured quorum. The local watchdog remains process supervision.

## Configuration

Store the operator configuration at `~/.config/vpn-provision/liveness.yaml` with mode `0600`. Sentinel IDs and policy names must describe technical path signatures, not carriers, operators, or geography.

```yaml
schema_version: 1
probe_url: https://www.gstatic.com/generate_204
expected_status: 204
probe_timeout_seconds: 15
degraded_after_ms: 3000
stale_after_seconds: 120
evaluation_interval_seconds: 120
failure_threshold: 3
otp_ttl_seconds: 3600
expected_runtime:
  sing_box: 1.13.12
  awg: 1.0.0
policies:
  - id: fullstack
    required_profiles: [p0-reality, p1-xhttp, p2-hysteria2, p2-amneziawg]
    min_failed_vantages: 2
sentinels:
  - id: tls-freeze-a
    ssh_target: sentinel-a
    policy: fullstack
  - id: udp-filtered-b
    ssh_target: sentinel-b
    policy: fullstack
```

The contract is `contract/protocol-liveness.schema.json`. Each `ssh_target` is an OpenSSH host alias with a pinned host key. The operator pulls reports with `BatchMode=yes`, `StrictHostKeyChecking=yes`, and a bounded timeout; there is no public result collector.

## Sentinel onboarding

Create a unique client with `scripts/new-client.sh` for each sentinel. Do not reuse UUIDs, short IDs, Hysteria passwords, AWG peer keys, or the one-time AWG private key between sentinels. Install the required pinned `sing-box`, `amneziawg-go`, `awg`, `awg-quick`, `ip`, `curl`, and Python runtimes through the sentinel's normal trusted package or image workflow.

Immediately after creating the client, run `make install-liveness-sentinel LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml SENTINEL=tls-freeze-a CLIENT=liveness-a` and paste the one-time AWG private key on stdin. The installer generates only that client's configurations, removes the AWG DNS hook, transfers no SOPS material, installs root-owned `0600` configuration, adds a fixed-command sudo rule for `/usr/local/sbin/vpn-protocol-liveness`, checks exact runtime versions, and requires an initial authenticated probe to pass.

The AWG adapter creates the userspace interface in the host namespace, moves only that interface into a temporary network namespace, and adds the probe address and default route inside the namespace. The userspace UDP socket retains the sentinel's normal underlay while the host routing table remains unchanged. A successful AWG verdict requires both a fresh handshake and the expected HTTP response. The namespace, interface, and userspace process are removed on success, failure, timeout, or signal.

## Decision and promotion behavior

Run `make protocol-liveness LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml` to inspect one redacted evaluation. `ok` and `throttled` prove the profile completed authenticated data-plane traffic; `blocked` contributes to rotation only when the direct control succeeds; `unknown` and `error` inhibit rotation.

For monitoring without a warm spare, run `make monitor-protocol-liveness LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml`. It stores the latest redacted evidence beneath `${XDG_STATE_HOME:-~/.local/state}/vpn-deploy/protocol-liveness`, sends ntfy alerts on unhealthy transitions and recovery using `watchdog_secrets`, retries failed delivery, and emits at most one reminder per day while the state is unchanged. Evaluator startup, timeout, and output failures become persisted `unknown` evidence and alerts instead of silently leaving stale state. Notification credentials normally come from an owner-controlled `0600` materialized secrets file; unattended runs materialize it through `decrypt-secrets.sh` and remove it immediately. Explicit `NTFY_TOPIC`/`NTFY_TOKEN` environment overrides are supported for isolated testing and operator-controlled one-shot runs.

A sentinel fails its policy only when every required logical profile is blocked. A logical profile with multiple endpoint variants remains alive when any variant succeeds; variants are executed concurrently within one bounded probe stage, and redacted per-variant verdicts remain in the evidence. A policy becomes `rotation_candidate` only when `min_failed_vantages` sentinels fail. Three consecutive two-minute candidate evaluations issue the existing OTP; no command promotes automatically.

`make promote-spare OTP=… LIVENESS_CONFIG=…` reruns the probes before consuming the OTP. Promotion is refused if liveness recovered, evidence became indeterminate, the candidate policy changed, the configuration hash changed, or provider/environment binding changed. Blue-green verification and the existing operator traffic-pivot confirmation remain mandatory.

Configure the managed cron block with `LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml make install-operator-crons`. Without `WARM_SPARE_ENV`, it runs the standalone monitor every two minutes. With `WARM_SPARE_ENV=spare`, the warm-spare watcher owns the same probe cycle and retains the OTP-gated promotion flow. Omitting `LIVENESS_CONFIG` preserves the legacy TCP-only watcher and prints a warning; that compatibility mode cannot detect targeted protocol blocking.

## Staging acceptance

First prove all four required profiles return `ok` or `throttled` from at least two sentinels. Then use staging-only endpoint overrides to verify that one blocked profile produces `degraded`, one fully blocked sentinel remains below quorum, quorum failure for three evaluations issues one OTP without promotion, and restoring any required profile invalidates that OTP. Never simulate this by changing production routes or firewall rules.
