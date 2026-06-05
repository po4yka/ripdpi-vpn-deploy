# ASN exposure denylist gate

- [ ] #task Design disabled-by-default ASN exposure denylist gate #repo/RIPDPI-VPN-DEPLOY #area/ansible #status/backlog 🔼

## Goal

Design a disabled-by-default server-side denylist gate for high-risk ASN/service-network exposure reduction without committing ranges, generated rule payloads, firewall commands, route files, or provider-specific policy.

## Why now

Public sources such as `https://github.com/C24Be/AS_Network_List` and `https://docs.google.com/spreadsheets/d/1YWS5aMEykkM9koxcZW1q_bZBi2j1UGmTbhFhOfnrd4k/edit?gid=2065371898#gid=2065371898` can inform a defensive server-hardening pattern. The deploy repo needs a safe adoption path before any runtime enforcement is considered.

## Scope

- Define feed metadata schema and policy-intent schema with placeholder fixtures only.
- Add parser validation and redacted dry-run summary design.
- Keep ingress and egress decisions separate in data model and review output.
- Require log-only/canary mode, false-positive monitoring, disabled-by-default toggles, and rollback criteria.
- Prove existing firewall render is unchanged when the gate is disabled.
- Document integration points for Ansible firewall rendering and optional `vpnd` dry-run review without adding an auto-updater.

## Out of scope

- No committed ASN rows, IP ranges, ready-to-load nftables/ipset content, route blackholes, or provider firewall rules.
- No geography-, carrier-, ISP-, or operator-named variables, files, cohorts, or comments.
- No default-on blocking behavior.
- No external vault references.

## Ship definition

- [ ] `docs/ASN-EXPOSURE-DENYLIST.md` is treated as the design boundary.
- [ ] A schema proposal exists with placeholder-only fixtures.
- [ ] Dry-run output redacts inventories and reports only counts, source URLs, policy direction, and validation status.
- [ ] Tests prove disabled-by-default behavior does not alter rendered firewall output.
- [ ] Operator docs describe review, canary, false-positive monitoring, and rollback without deployable rule payloads.
- [ ] The implementation plan explicitly answers host-originated vs forwarded-traffic scope for egress policy.
- [ ] The implementation plan states whether feed refresh is manual-reviewed artifact update or dry-run-only automation; no hidden apply path exists.

## Links

- `docs/ASN-EXPOSURE-DENYLIST.md`
- `https://github.com/C24Be/AS_Network_List`
- `https://docs.google.com/spreadsheets/d/1YWS5aMEykkM9koxcZW1q_bZBi2j1UGmTbhFhOfnrd4k/edit?gid=2065371898#gid=2065371898`
