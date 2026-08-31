# Change: Preserve return traffic through the UpCloud stateless firewall

Task ID: `SEC-1788187456764401`

## Why

The UpCloud Public & Utility firewall is stateless. The current Terraform root
defines inbound listener and SSH rules followed by terminal drops, but it does
not define the inbound half of server-initiated TCP/UDP flows. Enabling that
ruleset can therefore break cloud-init package installation, DNS/NTP and VPN
forwarding. The existing draft PR110 adds only DNS replies and remains unsafe;
this replacement change is based on current main and does not merge or apply
PR110.

## What Changes

- Add an explicit disabled-by-default provider-firewall activation input.
- Add a reviewed dual-stack TCP/UDP return-path matrix and DHCP bootstrap rules
  before terminal inbound drops.
- Add Terraform regressions for activation, rule shape, ordering and invalid
  ephemeral ranges.
- Document and exercise a two-phase staging promotion: create with the provider
  firewall disabled, verify the guest stateful firewall, then enable and repeat
  network acceptance.

## Capabilities

### New Capabilities

- `upcloud-stateless-return-path`: safely activate the UpCloud Public & Utility
  firewall while preserving server-initiated traffic.

### Breaking Changes

- Terraform becomes the explicit owner of `upcloud_server.vpn.firewall` with a
  default of `false`. Any existing environment that intentionally enabled the
  provider firewall outside Terraform must set
  `enable_provider_firewall=true` before its next apply; otherwise the reviewed
  plan will disable that external setting.

### Modified Capabilities

- None.

## Impact

- Terraform: `terraform/providers/upcloud` only.
- Operator docs and staging verification evidence.
- No production apply, provider resource creation or PR110 integration is
  authorized by this source change.
