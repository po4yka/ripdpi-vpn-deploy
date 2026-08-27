# Change: Require UpCloud provider firewall activation

Task ID: `SEC-1787843484501357`

## Why

The UpCloud root defines firewall rules but omits the server activation flag. The current provider schema treats that flag as optional and computed; local state records an inactive firewall despite populated rules. An operator can therefore have the expected rules without provider enforcement.

## What Changes

- Managed UpCloud servers explicitly enable their provider firewall.
- Existing narrow SSH CIDRs and public listener rules remain unchanged by this source fix.
- Preserve DNS responses through explicit resolver IPv4 addresses, TCP/UDP source port 53, the primary public IPv4 destination, and the guest ephemeral port range. Replies precede both final deny rules; no unrestricted DNS ingress is added.
- A regression test rejects omission of the activation requirement.
- No breaking interface, new dependency, node replacement, or credential change is introduced.

## Capabilities

### New Capabilities

- `security/upcloud-firewall-activation`: Provider firewall activation is an explicit invariant for managed UpCloud servers.

### Modified Capabilities

- None.

## Impact

- Terraform UpCloud server resource, existing mock-provider server tests, and local provider guidance.
- Existing live nodes require a separately reviewed rollout that installs the current SSH allowlist before enabling enforcement.
