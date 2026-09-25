---
task_id: ANS-1790316250156031
change: ans-1790316250156031-reject-public-listeners-on-the-effective-ssh-port-before-convergence
commit_sha: null
local: passed
local_evidence: "mise exec -- python3 -m pytest tests/unit/test_firewall_ssh_port_reservation.py passes 11 tests that evaluate the real firewall task with pinned ansible-core 2.21.3. Mutating the protocol filter to udp fails 6, ignoring the range upper bound fails 1, and restoring port_range-before-port precedence fails 2. Adjacent listener, firewall, security-verify and governance suites pass; ansible-lint production profile, repository yamllint, template render, snapshot diff, deploy-profile guard, tf-policy-verify and site.yml syntax-check pass. Terraform mock tests passed for upcloud, hetzner and vultr; provider downloads from github.com timed out locally for scaleway, which this change does not touch."
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The change neither alters the deploy controller nor rendered deployment input; the assert consumes existing inventory and sshd -T state and runs identically in check mode.
staging: not_applicable
staging_evidence: Source-only fail-closed guard with no external positive capability; the firewall Molecule and full-stack scenarios in protected-main CI exercise the role in a container.
live: not_applicable
live_evidence: No production rollout is implied; a correctly configured deploy renders an unchanged ruleset.
client: not_applicable
client_evidence: No client-facing transport or bundle behavior changes.
artifact: not_applicable
artifact_evidence: No bundle, schema or release artifact contract changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SSH-PORT-RESERVED | ANS-1790316534792016 | Assert "Reject public listeners on the effective SSH port" in ansible/roles/firewall/tasks/main.yml follows the single-port sshd -T assert and precedes the UFW disable and nftables render; test_check_precedes_firewall_mutation | passed locally |
| REQ-SSH-PORT-RESERVED | ANS-1790316540041401 | test_tcp_listener_on_ssh_port_fails (exact, range, padded upper-case protocol, port set alongside port_range), test_contract_without_tcp_ssh_claim_passes (empty, distinct, UDP, adjacent ranges), test_tcp_listener_without_port_fails_closed, test_failure_message_names_listener_and_port | passed locally |
| REQ-SSH-PORT-RESERVED | ANS-1790316540566345 | ansible/roles/honeypot/CLAUDE.md pitfall, ansible/roles/firewall/CLAUDE.md design decision, ansible/CLAUDE.md listener-collision pointer | passed locally |
