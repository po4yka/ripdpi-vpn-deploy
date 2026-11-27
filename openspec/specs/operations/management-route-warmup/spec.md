# operations/management-route-warmup Specification

## Purpose
Establish the relayed Tailnet path to a node before the controller's first SSH command in a preview or deploy, refuse a route that cannot carry the run before it starts, and keep a running session through the reply gap that follows a change of the operator's home relay region.

## Requirements

### Requirement: REQ-OPS-ROUTE-WARMUP — Warm-up probe before readiness

Before the readiness probe of a `dry-run` or `deploy` on a Tailnet transport, the controller MUST send one `tailscale ping` that accepts a relayed reply and waits up to 30 s, and MUST NOT count it in the route measurement. When it gets no reply, the controller MUST refuse with `management-route-unreachable` before any SSH command to that host.

#### Scenario: Cold relay path is established before readiness

- **WHEN** a dry-run targets a Tailnet transport and the warm-up probe replies through a relay after 23 s
- **THEN** the controller measures the route and then runs the readiness probe

#### Scenario: Unreachable route refuses before SSH

- **WHEN** the warm-up probe gets no reply within 30 s
- **THEN** the run stops with `management-route-unreachable` and no SSH command reaches the host

### Requirement: REQ-OPS-ROUTE-SCOPE — Only operator Tailnet transports are probed

A Tailnet transport is a management address inside `100.64.0.0/10` or `fd7a:115c:a1e0::/48`, IPv4-mapped forms included. The CI Tailnet handoff run, public addresses and host-name transports MUST NOT get a warm-up or measurement probe.

#### Scenario: CI handoff and public transport are not probed

- **WHEN** the run is the CI Tailnet handoff run, or the transport is a public address or a host name
- **THEN** the controller sends no warm-up probe and no measurement probe

### Requirement: REQ-OPS-ROUTE-BOTH-MODES — Route measurement in dry-run and deploy

After the warm-up probe and before the readiness probe, the controller MUST measure the route of a `dry-run` with the same ten probes, thresholds and refusal categories (`management-route-lossy`, `management-route-slow`, `management-route-unmeasured`) as a `deploy`. A refusal MUST stop the run before the first playbook, and the report MUST name only the route kind and the median.

#### Scenario: Lossy route refuses a dry-run before its playbook

- **WHEN** a dry-run on a Tailnet transport gets nine replies to ten measurement probes
- **THEN** the run stops with `management-route-lossy` and no playbook runs

#### Scenario: Measured route is reported in both modes

- **WHEN** a dry-run or a deploy measures ten relayed replies with a 180 ms median
- **THEN** the controller reports a relayed route with a 180 ms median and continues

### Requirement: REQ-OPS-ROUTE-SILENCE — Shared master outlasts a relay home change

The run-owned SSH master that Ansible tasks share MUST use `ServerAliveInterval=15` and `ServerAliveCountMax=20` in both `dry-run` and `deploy`, so that a session survives 300 s without a reply. The controller MUST NOT enable Ansible SSH retries in either mode. Readiness checks, recovery commands and every fresh strict SSH lockout proof MUST keep the strict command with `ConnectionAttempts=1`, no master and no keepalive options.

#### Scenario: Shared master carries the longer silence budget

- **WHEN** the controller prepares the Ansible SSH arguments for a selected host in either mode
- **THEN** they contain `ServerAliveInterval=15` and `ServerAliveCountMax=20` and set no `ansible_ssh_retries`

#### Scenario: Strict commands are unchanged

- **WHEN** the controller builds the readiness or lockout-proof SSH command for the same host
- **THEN** that command keeps `ConnectionAttempts=1`, `ControlMaster=no` and no keepalive options
