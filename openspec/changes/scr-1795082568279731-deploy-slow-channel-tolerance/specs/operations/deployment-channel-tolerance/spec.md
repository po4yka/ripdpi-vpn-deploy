## ADDED Requirements

### Requirement: REQ-OPS-CHANNEL-SESSION — Shared Ansible master survives a short stall

The deploy controller MUST give the run-owned SSH master that Ansible tasks share the options `ServerAliveInterval=15`, `ServerAliveCountMax=8` and `ConnectionAttempts=3`. Readiness checks, recovery commands and every fresh strict SSH lockout proof MUST keep the strict command with `ConnectionAttempts=1`, no master and no keepalive options.

#### Scenario: Multiplexed task path carries keepalive and connection attempts

- **WHEN** the controller prepares the Ansible SSH arguments for a selected host
- **THEN** they contain `ServerAliveInterval=15`, `ServerAliveCountMax=8` and `ConnectionAttempts=3` together with the run-owned control path

#### Scenario: Fresh strict command is unchanged

- **WHEN** the controller builds the readiness or lockout-proof SSH command for the same host
- **THEN** that command keeps `ConnectionAttempts=1`, `ControlMaster=no` and no keepalive options

### Requirement: REQ-OPS-CHANNEL-PROMPT — Longer privilege prompt wait without retries

The controller MUST pass `ansible_ssh_timeout=90` to every controller-driven playbook host, so that Ansible waits 92 seconds for the privilege-escalation prompt. The controller MUST NOT enable Ansible SSH retries, because a retry after a lost connection can run a protected-transaction task twice.

#### Scenario: Prompt wait is extended without retries

- **WHEN** the controller writes the transport variables of a playbook host
- **THEN** they set `ansible_ssh_timeout` to 90 and set no `ansible_ssh_retries`

### Requirement: REQ-OPS-CHANNEL-GATE — Measured Tailnet route before mutation

Before the source recheck and the first mutating playbook of a deploy on a host whose management address is inside `100.64.0.0/10` or `fd7a:115c:a1e0::/48` (IPv4-mapped forms included), the controller MUST measure the route with ten `tailscale ping` probes that do not stop at the first direct reply. Dry-run, the CI Tailnet handoff run and other transports MUST NOT be probed.

#### Scenario: Relayed route within bounds is admitted

- **WHEN** a deploy targets a Tailnet transport and all ten probes reply through a relay with a median of 180 ms
- **THEN** the controller reports a relayed route with a 180 ms median and continues to the playbook

#### Scenario: Dry-run, CI handoff and public transport are not gated

- **WHEN** the run is a dry-run, the CI Tailnet handoff run, or the transport is a public address or a host name
- **THEN** the controller runs no route probe

### Requirement: REQ-OPS-CHANNEL-REFUSAL — Categorical route refusal

The gate MUST refuse before that node changes with `management-route-lossy` when a probe gets no reply, with `management-route-slow` when the median round-trip time (millisecond or second replies) exceeds 400 ms, and with `management-route-unmeasured` when the CLI is missing, exits non-zero, times out or prints no parsable reply. Its report MUST name only the route kind and the median, never the address or peer name.

#### Scenario: Lost probe refuses before mutation

- **WHEN** one of the ten probes gets no reply
- **THEN** the deploy stops with `management-route-lossy` and no playbook runs

#### Scenario: Slow route refuses before mutation

- **WHEN** all probes reply and the median round-trip time is 650 ms
- **THEN** the deploy stops with `management-route-slow` and no playbook runs

#### Scenario: Missing CLI refuses

- **WHEN** the `tailscale` CLI is not on `PATH`
- **THEN** the deploy stops with `management-route-unmeasured`
