# Protocol-level liveness and rotation

Process state, a listening socket, and a bare TLS response do not prove that a real client can authenticate and carry traffic across a filtered path. Rotation uses a separate operator-side module that pulls authenticated data-plane probes from managed sentinels and requires sustained failure from a configured quorum. The local watchdog remains process supervision.

## Passive fleet inspection

`make inspect INSPECT_HOSTS=node-a,node-b` reads only those exact names from an
existing generated INI inventory. Set `INSPECT_INVENTORY` and
`INSPECT_KNOWN_HOSTS` to explicit existing files for an isolated operator context.
No default fleet, wildcard expansion, Terraform, decryption, Ansible, bootstrap
wait, protocol probe, watchdog, or restic command is involved.

Each host must declare `ansible_host`, `ansible_user`, `ansible_port`, and a private
`ansible_ssh_private_key_file`. Inventory plugins and connection options are not
evaluated. Keys and known-hosts files must be operator-owned; links, writable
parents, SSH expansion tokens and whitespace-bearing SSH paths are rejected.
A root-owned sticky temporary parent is allowed, but its selected child still
must be owner-controlled.

SSH ignores user configuration (`-F /dev/null`), agents, proxy commands,
multiplexing, forwarding and local commands. It never accepts a new key. Optional
paired variables `inspection_transport_host` and `inspection_host_key_alias`
select a direct transport and the original host identity; nonstandard ports use
the existing `[identity]:port` pin. The alias is a name/address, not a bracketed
known-hosts entry. Existing noninteractive sudo access to `/usr/bin/python3` is
required; inspection does not grant it.

The collector runs from SSH stdin with Python `-I -B -S`. It reads root-owned
bounded regular files, selected `systemctl show` properties and `ss -H -lntu`.
AWG instance names come from the managed `awg-quick.target` dependencies. Reports
contain no process arguments, journal, raw stderr, secrets or snapshot IDs.
SSH accounting, audit records and access times may still change; no managed
state is explicitly changed.

Versioned JSON separates services, listeners, deployed source and restore
evidence. `observed` describes collection, not client connectivity. Exit 1 means
a failed service, stale/unknown required observation, unavailable host or invalid
report; exit 2 means invalid local input. All inputs are checked before contacting
the first host. Connections have a 10-second connect and 30-second total deadline,
without retries or fallback.

Latest backup freshness remains `unknown`: no safe standalone latest-snapshot
metadata exists. A restore marker records its own source and snapshot time, not
the newest backup. Restore evidence is stale after 35 days; its snapshot age is
separately stale after 36 hours. Future evidence is unknown. An active timer is
not backup proof, and a local marker is not offsite restore proof. `make verify`
remains **active** and its watchdog may restart services; use `inspect` when only
observation is authorized.

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
  sing_box: 1.13.16
  xray: 26.3.27
  awg: 1.0.0
  awg_toolchain: "<64-character source-input digest from the installed toolchain>"
policies:
  - id: fullstack
    required_profiles: [p0-reality, p1-xhttp, p2-hysteria2, p2-amneziawg]
    min_failed_vantages: 2
sentinels:
  - id: tls-freeze-a
    ssh_target: sentinel-a
    ssh_transport_host: sentinel-direct
    ssh_host_key_alias: sentinel-a
    policy: fullstack
    vantage: external
    awg_target: {provider: vultr, environment: prod, instance: awg0}
  - id: udp-filtered-b
    ssh_target: sentinel-b
    policy: fullstack
    vantage: filtered
    awg_target: {provider: vultr, environment: prod, instance: awg0}
```

The contract is `contract/protocol-liveness.schema.json`. Replace the toolchain
placeholder with the actual installed source-input digest. Fullstack configuration
without the Xray pin, explicit AWG provider/environment/instance and vantage is
rejected; it does not fall back to an older installation format. Each `ssh_target`
is an operator-controlled OpenSSH alias with an existing host-key pin. Optional
paired `ssh_transport_host` and `ssh_host_key_alias` preserve that identity on a
direct transport. Active sentinel commands disable proxy commands, multiplexing,
forwarding, local commands and password authentication, but still read the
operator's alias configuration. This differs from passive `inspect` isolation.
There is no public result collector.

## Sentinel onboarding

Create a unique client with `scripts/new-client.sh` for each sentinel. Do not reuse
UUIDs, short IDs, Hysteria passwords or AWG keys between sentinels. The client
registry must mark it issued, delivered or active. Install pinned sing-box and
Xray, plus ip, curl and Python through the sentinel's trusted image workflow.
AWG uses the immutable source-built toolchain managed by
`scripts/install-real-vps-awg-client-tools.py`; the sentinel verifies its canonical
manifest, tree and binary hashes beneath
`/opt/ripdpi-real-vps-awg-nat/toolchains/<source-input-digest>`. A PATH binary or
matching version banner alone is insufficient. Toolchain installation is a
separate authorized action; onboarding does not download or install runtimes.

From a clean committed checkout, explicitly supply the target mapping, for example
`make install-liveness-sentinel HOSTS=vultr:prod COHORTS=fullstack LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml SENTINEL=tls-freeze-a CLIENT=liveness-a`.
Supply the one-time AWG private key on stdin. Interactive input is prompted only
after terminal echo is disabled; a pipe or redirected private file needs no prompt.
Terminal settings are restored after a read error or Ctrl-C, and unavailable echo
control refuses input. Onboarding decrypts
once into a private temporary directory, invokes both canonical client emitters,
matches the supplied key to the selected peer, and validates generated profiles
with real local parsers before any remote writes. REALITY and Hysteria2 use
sing-box; XHTTP uses Xray with verified TLS. No full secrets document, server
private key or another client's credentials reach the sentinel.

Installation stages a complete private generation, then starts a bounded detached
systemd job. A shared lock serializes install and probe. Pending state snapshots
the previous launcher, engine, sudo rule and current generation before activation.
A failed initial authenticated probe restores that state. A committed receipt
bound to the exact generation, runner and public profile is required before the
controller publishes its assignment. Lost SSH leaves public pending metadata;
retry first reconciles the same generation's receipt. Queueing a job is not
success. The probe deadline is the per-request timeout multiplied by the control
plus logical profile count, with 240 seconds for bounded setup and cleanup
(315 seconds for default fullstack, at most 540). SSH collection adds a
20-second transport margin. The job and monitor have a
600-second limit; receipt reconciliation has 660 seconds. Runtime files are sealed root-owned (directories/executable runner 0500,
configuration 0400). The sudo rule permits only the fixed no-argument launcher.

The AWG adapter creates the userspace interface in the host namespace, moves only that interface into a temporary network namespace, and adds the probe address and default route inside the namespace. The userspace UDP socket retains the sentinel's normal underlay while the host routing table remains unchanged. A successful AWG verdict requires both a fresh handshake and the expected IPv4 HTTPS response on port 443. The namespace, interface, and userspace process are removed on success, failure, timeout, or signal. Existing interfaces are never adopted or removed. All curl calls disable curlrc and ambient proxies; SOCKS calls also override NO_PROXY bypass.

`make liveness-profile-check` exercises both canonical emitters and the real
pinned sing-box/Xray parsers. It is mandatory in `make ci-fast` and hosted CI.
Loopback and parser tests do not establish external four-protocol acceptance.
Reports separate controller revision, runner hash, client generation, public
profile digest, runtime versions and declared vantage. Deployed server identity
remains unknown unless collected separately; the controller SHA is not a server
SHA. IPv4 HTTPS evidence does not prove UDP payload, IPv6, Android, filtered-path
quorum, rotation or offsite restore.

## Decision and promotion behavior

Run `make protocol-liveness LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml` to inspect one redacted evaluation. `ok` and `throttled` prove the profile completed authenticated data-plane traffic; `blocked` contributes to rotation only when the direct control succeeds; `unknown` and `error` inhibit rotation.

For monitoring without a warm spare, run `make monitor-protocol-liveness LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml`. It stores the latest redacted evidence beneath `${XDG_STATE_HOME:-~/.local/state}/vpn-deploy/protocol-liveness`, sends ntfy alerts on unhealthy transitions and recovery using `watchdog_secrets`, retries failed delivery, and emits at most one reminder per day while the state is unchanged. Evaluator startup, timeout, and output failures become persisted `unknown` evidence and alerts instead of silently leaving stale state. Notification credentials normally come from an owner-controlled `0600` materialized secrets file; unattended runs materialize it through `decrypt-secrets.sh` and remove it immediately. Explicit `NTFY_TOPIC`/`NTFY_TOKEN` environment overrides are supported for isolated testing and operator-controlled one-shot runs.

A sentinel fails its policy only when every required logical profile is blocked. A logical profile with multiple endpoint variants remains alive when any variant succeeds; variants are executed concurrently within one bounded probe stage, and redacted per-variant verdicts remain in the evidence. A policy becomes `rotation_candidate` only when `min_failed_vantages` sentinels fail. Three consecutive two-minute candidate evaluations issue the existing OTP; no command promotes automatically.

`make promote-spare OTP=… LIVENESS_CONFIG=…` reruns the probes before consuming the OTP. Promotion is refused if liveness recovered, evidence became indeterminate, the candidate policy changed, the configuration hash changed, or provider/environment binding changed. Blue-green verification and the existing operator traffic-pivot confirmation remain mandatory.

Configure the managed cron block with `LIVENESS_CONFIG=~/.config/vpn-provision/liveness.yaml make install-operator-crons`. Without `WARM_SPARE_ENV`, it runs the standalone monitor every two minutes. With `WARM_SPARE_ENV=spare`, the warm-spare watcher owns the same probe cycle and retains the OTP-gated promotion flow. Omitting `LIVENESS_CONFIG` preserves the legacy TCP-only watcher and prints a warning; that compatibility mode cannot detect targeted protocol blocking.

## Staging acceptance

First prove all four required profiles return `ok` or `throttled` from at least two sentinels. Then use staging-only endpoint overrides to verify that one blocked profile produces `degraded`, one fully blocked sentinel remains below quorum, quorum failure for three evaluations issues one OTP without promotion, and restoring any required profile invalidates that OTP. Never simulate this by changing production routes or firewall rules.
