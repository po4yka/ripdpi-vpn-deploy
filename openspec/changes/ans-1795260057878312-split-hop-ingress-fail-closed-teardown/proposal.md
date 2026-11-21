# Change: Make split-hop ingress flows fail fast after the tunnel stops

Task ID: `ANS-1795260057878312`

## Why

The fleet audit of 2026-11-20 found that the split-hop ingress tunnel `PostDown` flushes its policy routing table. The nftables guards then drop marked traffic that would leave outside the tunnel, so nothing leaks, but a device or a frontend waits for a timeout instead of an error. A kept `unreachable` route makes forwarded device flows fail at once, but a local TCP `connect` does not fail on a reroute error, and `reject` is not available in the postrouting guard that holds the local boundary. Change `ans-1795163654691828-udp-node-audit-hardening` declined this fix, because it changes the ingress policy tables and their retirement, and split-hop has several open changes and no live pair to test against.

## What Changes

- The policy routing table keeps an `unreachable` default route while the tunnel is down, so forwarded marked flows get an ICMP error.
- Local frontend connections that the policy marks for Node B are rejected in a hook where `reject` is available, before the postrouting guard, while the tunnel is down.
- Retirement of the role removes the kept route and the rule together, so a disabled split-hop leaves no table behind.

## Capabilities

### New Capabilities

- `network/split-hop-ingress-teardown`: the behaviour of split-hop ingress traffic while the tunnel is down and after the role retires.

### Modified Capabilities

- None

## Impact

- Ansible: the split-hop ingress tunnel configuration, policy ruleset, policy loader and retirement tasks.
- Coordination: the open split-hop changes that edit the same policy file.
- Evidence: needs a disposable Node A and Node B pair.
