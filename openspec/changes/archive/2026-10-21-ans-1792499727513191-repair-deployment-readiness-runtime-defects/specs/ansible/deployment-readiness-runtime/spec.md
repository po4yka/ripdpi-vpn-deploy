## Purpose

Keep routine maintenance, host packages, forwarded device traffic, watchdog
recovery and runtime pins from causing outages or crossing the documented
security boundaries on every production deployment profile.

## ADDED Requirements

### Requirement: REQ-DRR-ROTATE — Rotate Xray logs through guarded recovery

Xray log rotation MUST request guarded generation recovery whenever the
protected transport egress generation owns Xray. It MUST use the transport
egress preparation predicate and MUST NOT depend on the optional
`vpn.enable_transport_egress` key.

#### Scenario: A production profile omits the optional toggle

- **WHEN** the rotation policy renders for any `group_vars/vpn-*.yml` profile
  that enables Xray REALITY, XHTTP or Hysteria and is not subscription-only
- **THEN** the post-rotation action calls the generation controller with
  `--unit xray.service`
- **AND** it never calls `systemctl restart xray.service`

#### Scenario: No protected frontend is enabled

- **WHEN** the profile is subscription-only or disables every protected frontend
- **THEN** the policy keeps the direct restart and propagates its failure

### Requirement: REQ-DRR-RESOLVER — Keep the host resolver package set

The AmneziaWG role MUST NOT install `resolvconf`. Server interface
configurations MUST NOT set `DNS=`.

#### Scenario: AWG converges on a host with systemd-resolved

- **WHEN** the role installs its build and runtime packages
- **THEN** the package list does not contain `resolvconf`
- **AND** apt has no reason to remove `systemd-resolved` or `libnss-resolve`

### Requirement: REQ-DRR-AWGDEST — Refuse private AWG forwarding destinations

The firewall MUST drop forwarded packets that enter an AmneziaWG interface and
target an address in the canonical recipient deny policy, before the rule that
accepts new AWG flows to the uplink. The firewall list MUST equal the IPv4 and
IPv6 deny lists in `scripts/transport_destination_policy.py`.

#### Scenario: A device requests the metadata service

- **WHEN** an authenticated AWG device opens a flow to `169.254.169.254`
- **THEN** the forward chain drops it with a counter before the uplink accept

#### Scenario: The canonical policy changes

- **WHEN** a range is added to or removed from the canonical deny policy
- **THEN** a unit regression fails until the firewall list matches

#### Scenario: Ordinary recipient traffic

- **WHEN** a device opens a flow to a public destination
- **THEN** the existing uplink accept rule and conntrack replies still apply

### Requirement: REQ-DRR-WATCHDOG — Withhold restarts after failed validation

The watchdog MUST report a failed configuration validation as a red probe and
alert as before. It MUST NOT restart or recover a unit in a run where that
unit's configuration validation failed.

#### Scenario: nginx validation fails above the threshold

- **WHEN** `nginx -t` fails and the failure count reaches `fail_threshold`
- **THEN** the run records that the restart was withheld and does not call
  `systemctl restart nginx.service`
- **AND** the run stays red and alert rate limits still apply

#### Scenario: Xray validation fails above the threshold

- **WHEN** the Xray server validator fails and the threshold is reached
- **THEN** the run does not call the generation controller for `xray.service`

#### Scenario: A liveness failure with a valid configuration

- **WHEN** a unit is inactive or its listener is absent and validation passes
- **THEN** the existing bounded restart or guarded recovery still runs

### Requirement: REQ-DRR-HYSTERIA — Require a stable Hysteria pin

The Hysteria role MUST refuse a `hysteria.version` that does not match
`^v[0-9]+[.][0-9]+[.][0-9]+$` before it downloads or publishes a runtime.

#### Scenario: A pre-release pin

- **WHEN** `hysteria.version` is `v2.9.0-rc1` or empty
- **THEN** the pre-flight assertion fails before any acquisition task
