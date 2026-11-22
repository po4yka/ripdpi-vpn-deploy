---
task_id: TFR-1795259722029222
change: tfr-1795259722029222-listener-contract-address-family
commit_sha: e2ac65e33e
local: required
local_evidence: "make tf-test (upcloud 91, hetzner 61, vultr 80, scaleway 55 passed), make tf-policy-verify (92 passed), make snapshot-check (200 match, unchanged), affected pytest files passed; make -k -j 4 check: every target passed except load-sensitive tests that passed serially and three defects fixed and rerun with make task-check validate ci-fast-scripts. make molecule-test ROLE=firewall could not start locally: the amd64 Molecule image is unreachable under the arm64 Colima VM, so CI provides that run."
remote_ci: passed
remote_ci_evidence: "PR 670 (head 3416229839): the pytest shards were cancelled by a superseding run, so the PR rollup did not complete; the merged tree is covered by main CI. Main CI run 44923464687 on 696cab2c64, which contains all four follow-up changes and the refreshed debian13 Molecule image (PR 674): 84 of 84 jobs passed on 2026-11-21, including the four pytest groups, native runtime integration, native transport runtime acceptance and native four-transport acceptance lanes, every Molecule group and the Trivy scans of the refreshed images. The firewall Molecule group passed."
dry_run: passed
dry_run_evidence: "make plan on the staging node rendered only an IPv4 provider rule for nginx-xhttp 8443 (family ipv4) and the listener_family policy passed; make dry-run at 90442f787 passed with public_listener_families {nginx-xhttp: ipv4} in the node extra vars (PR 677 admitted that key after the first dry-run reported 'family differs: contract ipv4, runtime dual'). Production dry-runs at b56ed6434 passed after PR 676 fixed a pre-family contract crash in the retained AWG policy task."
staging: required
staging_evidence: "Partial, 2026-11-22: one disposable UpCloud node vpn-ci-staging-acc1 (device-full-staging, source 90442f787) was provisioned with a pinned SSH host-key seed, Tailnet-enrolled (lock-signed key), ownership-migrated and deployed; the data plane converged (xray, hysteria, nginx, AWG active). The controller then refused the disposable four-profile proof (onboarding-refused): the generated staging certificate is self-signed and the operator Colima executor does not trust it, while the liveness profiles require verified TLS. The node was destroyed through make staging-destroy with verified provider absence. Observed on the node: the only nftables accept for 8443 was 'meta nfproto ipv4 tcp dport 8443 accept'. Not done: an external IPv6 probe (no IPv6 vantage was available) and provider-edge enforcement, because the staging recipe keeps the provider firewall disabled in phase 1."
live: required
live_evidence: "pending: next production deploy after the operator states a family; existing tfvars omit family, which keeps every provider rule key and attribute"
client: not_applicable
client_evidence: No client contract changes.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-LISTENER-FAMILY-FIELD | TFR-1795259793636372 | `listener_family_rejects_unknown_value` in every `terraform/providers/*/tests/firewall.tftest.hcl`; unchanged existing tf-test runs and snapshots for absent family | local pass |
| REQ-LISTENER-FAMILY-LAYERS | TFR-1795259877267081 | `firewall_opens_only_the_stated_listener_family` per provider root; `single_family_listener_must_avoid_the_return_range` (UpCloud); `terraform/policy/listener_family_test.rego`; `test_single_family_listener_is_accepted_only_on_its_family` and `test_hopping_redirect_follows_the_range_family` | local pass; staging pending |
| REQ-LISTENER-FAMILY-AGREEMENT | TFR-1795259837898750 | `test_listener_family_must_agree_with_absent_meaning_dual` (contract check); `test_listener_accept_must_match_its_contract_family` and the cdn-front, SSH and Tailnet family cases in `test_security_verify_listeners.py` | local pass |
