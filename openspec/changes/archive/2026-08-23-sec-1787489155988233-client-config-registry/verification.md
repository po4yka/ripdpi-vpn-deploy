---
task_id: SEC-1787489155988233
change: sec-1787489155988233-client-config-registry
commit_sha: 5be2ac838e264e9d0176af855d7be24fdaef3a54
local: passed
local_evidence: "make ci-fast green in worktree (actionlint, zizmor 1.29.0, cloud-init schema, tf-test 20+18+20+17 bats passed, yamllint, pytest 962 passed / 2 skipped incl. new test_client_registry.py and test_client_drift.py, shellcheck); taskctl validate (11 tasks, 53 steps); openspec validate 8/8; governance count updated to (1017 collected)."
remote_ci: passed
remote_ci_evidence: "PR po4yka/ripdpi-vpn-deploy#89 branch CI green before squash merge (61 checks pass, 1 skip); merged as 5be2ac8."
dry_run: not_applicable
dry_run_evidence: "No Terraform or Ansible changes in the registry change itself; the follow-up subscription-host enablement was deployed with a targeted ANSIBLE_LIMIT run (vpn-p1-scaleway-pl-waw-1) after a full site.yml dry-run."
staging: not_applicable
staging_evidence: "Delivery plane co-location follows the v1 default (SUBSCRIPTION-HOST-SEPARATION.md); no separate staging node exists."
live: passed
live_evidence: "2026-08-23 against the production fleet. Onboarded device 'registry-canary' via new-client.sh (xray/hysteria/AWG peers + client_registry entry, AWG private-key recovery copy present). Deployed subscription-host on vpn-p1-scaleway-pl-waw-1 (tcp/8444 listener added to scaleway tfvars public_listeners; terraform apply 0 add/1 change/0 destroy). Issued multi-host singbox token (HOSTS=upcloud:p0-upcloud,scaleway:p1-scaleway,vultr:p2-vultr); fetch over TLS returned HTTP 200 with outbounds for both transport hosts. make client-drift -> current; simulated an outputs change in the recorded identity -> stale ('changed: outputs', exit 1); refresh via bare --refresh-token reused format+expires and the multi-host host list from the registry; drift returned to current; revocation appended the token hash to /var/lib/vpn-subscription/revoked on the delivery host and subscription.revoked_tokens in SOPS; subsequent fetch returned HTTP 410 and registry status moved to 'revoked'."
client: passed
client_evidence: "Payload-level device verification: the refreshed subscription fetch returns a sing-box document whose outbound set matches the recorded issuance options (p0-reality-upcloud-p0-upcloud + fallback resolving to the p0 node's Terraform `server_ipv4`, p2-hysteria2-vultr-p2-vultr resolving to the p2 node's `server_ipv4`), proving the registry-resolved refresh did not fall back to a default single-host payload. A physical third-party device import remains an operator-side check outside this repository's reach."
artifact: passed
artifact_evidence: "Registry snapshot fixtures committed with tests (tests/fixtures/secrets-sample.yml, re-encrypted tests/fixtures/secrets-sample.sops.yaml; test_client_registry.py 5 passed incl. the multi-host issuance regression). Audit trail retained: issuance audit entries under secrets/local/audits plus the encrypted registry entry itself records options and lifecycle transitions for 'registry-canary' (issued -> delivered -> revoked)."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-REGISTRY-RECORD | SCR-1787489427509997 | `tests/unit/test_secrets_schema.py::test_registry_missing_field_names_device` and `::test_registry_rejects_unknown_status_and_format`; live onboarding of one device wrote a complete entry | passed |
| REQ-REGISTRY-LIFECYCLE | SCT-1787489427528995 | `tests/unit/test_client_registry.py::test_fresh_issuance_records_registry_entry` covers the write side; the live run observed issued -> delivered -> revoked on one device | passed |
| REQ-REFRESH-OPTIONS | SCT-1787489427528995 | `tests/unit/test_client_registry.py` option-resolution matrix (registry reuse, override echo, ignored emitter environment, unregistered fail-closed); `make shellcheck` clean; the live bare refresh reused format+expires and the recorded multi-host list | passed |
| REQ-PRIVATE-KEY-RECOVERY | SCR-1787489427509997 | `new-client.sh` writes `clients[*].awg_private_key` at generation time; `tests/unit/test_secrets_schema.py` pins the field in the registry entry contract; the live onboarding confirmed the recovery copy present in the encrypted document | passed |
| REQ-DRIFT-CHECK | TST-1787489427553290 | `tests/unit/test_client_drift.py` verdict matrix (`current` / `stale` on source and outputs / `unknown`) plus CLI exit codes; live `make client-drift` returned current, stale after a forced outputs change, current again after refresh | passed |
| REQ-REGISTRY-SECURITY | DOC-1787489427574672 | Registry keys appear only in SOPS-gated scripts and the secrets schema, never in a git-tracked document or on the delivery host; live revocation landed the hash and the registry status in one SOPS edit and the next fetch returned HTTP 410 | passed |

## Evidence categories

### Local

Required. `make ci-fast` green on the implementation commit, including new
coverage, option-resolution, and drift-verdict tests.

### Remote CI

Required. Branch CI workflow green (shellcheck, pytest, gitleaks) before
merge.

### Dry-run

Not required — no Terraform or Ansible changes.

### Staging

Not required — no server-side behavior change; delivery host untouched.

### Live

Required. Onboard one test device against the production fleet, then:
shred `secrets/local/clients/<device>/**`, decrypt-recover the AWG key,
`make client-drift CLIENT=<device>` → `current`, force an outputs change →
`stale`, refresh via registry-resolved options, revoke → fetch returns
revoked response.

### Client

Required. One device imports the refreshed subscription payload and confirms
the expected format/hosts are active (no default single-host singbox
fallback).

### Artifact

Required. Registry rendering snapshot fixtures committed with tests; audit
log entries showing reused vs overridden options retained as redacted
evidence in the task record.
