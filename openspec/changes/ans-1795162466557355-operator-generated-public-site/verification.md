---
task_id: ANS-1795162466557355
change: ans-1795162466557355-operator-generated-public-site
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
client: not_applicable
client_evidence: "No client, bundle or transport contract changes."
artifact: not_applicable
artifact_evidence: "No release artifact."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SITE-IDENTITY | ANS-1795162712291937 | `tests/unit/test_public_site_bundle.py`: existing identity and unsafe origin refuse without a write | pending |
| REQ-SITE-BUILD | ANS-1795162712291937 | `tests/unit/test_public_site_bundle.py`: repeated build digests, symbolic link refusal | pending |
| REQ-SITE-SCHEDULE | ANS-1795162712291937 | `tests/unit/test_public_site_bundle.py`: interval bounds, start date, one article for each generation | pending |
| REQ-SITE-UNIQUE | ANS-1795162712291937 | calibrated samples in `tests/unit/test_public_site_bundle.py`; production preflight case in `tests/unit/test_public_site_contract.py`; failing dry run | pending |
| REQ-SITE-PUBLISH | ANS-1795162729645051 | publisher run against a fixed clock in `tests/unit/test_public_site_bundle.py`; Molecule `public-site`; staging request sequence | pending |
| REQ-SITE-ISOLATION | ANS-1795162729645051 | rendered unit assertions; hostile archive case; `systemd-analyze security` on staging | pending |
| REQ-SITE-ROLLBACK | ANS-1795162729645051 | Molecule `nginx-xhttp` and `reality-self-steal`; forced activation failure on staging | pending |
| REQ-SITE-LIVE | ANS-1795162761685232 | `tests/unit/test_model_news.py` with a bundle shell and declared sources | pending |
| REQ-SITE-RUNWAY | ANS-1795162712291937 | status output for a fixed clock; dry-run warning | pending |
| REQ-SITE-LAYOUT | ANS-1795162748588038 | old-layout refusal case in `tests/unit/test_public_site_contract.py`; absent Make target | pending |
