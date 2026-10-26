---
task_id: OPS-1792927264049641
change: ops-1792927264049641-rebuild-cloud-vpn-service-with-automatic-https-renewal
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-BCNI-SIZE | OPS-1792928402362900 | Not yet run | required |
| REQ-BCNI-OBSERVER | OPS-1792928402362900 | Not yet run | required |
| REQ-BCNI-PROMOTION | OPS-1792928404361547 | Focused cloud-scope and native-onboarding checks pass; live protocol acceptance pending | required |
| REQ-BCNI-UFW | OPS-1792928402362900 | Disabled package wrapper regression added; cloud enrollment pending | required |
| REQ-MTLS-AUTHORITY | OPS-1792928402860448 | Not yet run | required |
| REQ-PROTO-RTA-CANDIDATE | OPS-1792928402860448 | Not yet run | required |
| REQ-MTLS-ACTIVATE | OPS-1792928402860448 | Not yet run | required |
| REQ-PIS-READ | OPS-1792928403354199 | Not yet run | required |
| REQ-PIS-BOUNDARY | OPS-1792928403354199 | Not yet run | required |
| REQ-IRBO-OBSERVER | OPS-1792928403861188 | Not yet run | required |
| REQ-IRBO-DELIVERY | OPS-1792928403861188 | Not yet run | required |
| REQ-IRBO-SCOPE | OPS-1792928404361547 | Not yet run | required |

## Evidence boundaries

Operator API issuance and vault readback exist as private operational evidence;
they do not accept any source or deployed service requirement above. No paid
server or DNS change existed at planning time. The rollout has now provisioned
one disposable and one permanent cloud node. The disposable node has been retired
with provider absence evidence. Strict SSH, cloud-init readiness and recovery
installation passed for the permanent node. Tailnet enrollment,
runtime deployment and DNS cutover remain open. Client acceptance uses dedicated
cloud probe identities; personal devices and filtered-network acceptance are
outside this run. The owner selected panel-only monitoring and provider account
notifications; no Telegram delivery or human receipt is claimed. Hosted evidence
requires the exact final source revision and remains open until observed.
