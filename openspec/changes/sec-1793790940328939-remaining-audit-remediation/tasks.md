# SEC-1793790940328939: Remediate remaining audit and remediation findings

## Objective

The remaining low audit findings and the residual risks from the medium remediation are closed in source.

## Ownership

- `terraform/providers/vultr/`, `scripts/transport_destination_policy.py`, `ansible/roles/firewall/defaults/main.yml`, `ansible/roles/xray/templates/xray.service.j2`, `ansible/roles/observability_agent/`, `ansible/roles/observability_control_plane/`, `scripts/release-inputs.py`, their tests, snapshots and docs.

## Execution

- [ ] SEC-1793791408648983 Accept TXT and CAA records in the Vultr zone #bug @item:SEC-1793790940328939
- [ ] SEC-1793791827276913 Deny benchmarking, NAT64 and 6to4 recipient destinations #bug @item:SEC-1793790940328939
- [ ] SEC-1793792244192848 Apply the transport sandbox baseline to the Xray unit #bug @item:SEC-1793790940328939
- [ ] SEC-1793792655608435 Alert on self-steal certificate expiry and relay drops, and generate the relay pin #bug @item:SEC-1793790940328939

## Verification

- Focused unit, Terraform, promtool, snapshot and sandbox checks; remote CI. Rollout to the fleet and the DNS record changes follow the reviewed deploy and plan procedures after merge.
