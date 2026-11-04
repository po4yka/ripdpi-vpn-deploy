# Change: Remediate remaining audit and remediation findings

Task ID: `SEC-1793790940328939`

## Why

The 2026-11-04 audit left low findings open, and the medium remediation added new residual risks:
- The Vultr zone could not publish SPF, DMARC or CAA records.
- The recipient deny list missed benchmarking, NAT64 and 6to4 ranges.
- The production Xray unit could write its configuration directory and had no syscall filter.
- The self-steal certificate has no renewal and no expiry alert.
- The collector relay can drop accepted samples without any signal.
- The relay pin had to be written by hand.

## What Changes

- The Vultr root accepts TXT and CAA records and underscore labels.
- The recipient policy, the AWG forward drop set and the gateway answer filter deny `198.18.0.0/15`, `64:ff9b::/96` and `2002::/16`.
- The Xray unit meets the transport sandbox baseline.
- The agent health adapter reports the self-steal certificate expiry, so the existing expiry alerts cover it.
- The collector scrapes relay drop counters and alerts on drops.
- `scripts/release-inputs.py` produces the relay pin.

## Capabilities

### New Capabilities

- `security/residual-surface-hardening`: mail and CA policy records, a wider recipient deny list, a sandboxed Xray unit, and monitoring for the self-steal certificate and relay drops.

### Modified Capabilities

- None.

## Impact

- Terraform: `terraform/providers/vultr/variables.tf`.
- Ansible: `ansible/roles/xray/`, `ansible/roles/firewall/defaults/main.yml`, `ansible/roles/observability_agent/`, `ansible/roles/observability_control_plane/`.
- Scripts: `scripts/transport_destination_policy.py`, `scripts/release-inputs.py`.
- Operations: the zone records for apex SPF, `_dmarc` and CAA, and removal of the wildcard CNAME, are private tfvars changes applied after merge.
