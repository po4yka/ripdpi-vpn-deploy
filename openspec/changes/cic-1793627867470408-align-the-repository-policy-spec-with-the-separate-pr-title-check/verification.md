---
task_id: CIC-1793627867470408
change: cic-1793627867470408-align-the-repository-policy-spec-with-the-separate-pr-title-check
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Spec text only; no deployment plan applies.
staging: not_applicable
staging_evidence: No staging host is involved.
live: not_applicable
live_evidence: No provider, credential, repository setting or runtime mutation is included; applying the policy to GitHub is a separate operator action.
client: not_applicable
client_evidence: No emitted client document or bundle contract changes.
artifact: not_applicable
artifact_evidence: No generated artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-RPOL-LAYERS | CIC-1793628619386753 | `.github/repository-policy.json` lists `PR title` bound to GitHub Actions; `tests/unit/test_branch_protection_contract.py` pins the four contexts | pending |
| REQ-RPOL-MERGE | CIC-1793628619386753 | `.github/workflows/pr-title.yml` triggers; `ci.yml` without `edited`; `tests/unit/test_pr_title.py::test_title_edits_rerun_only_the_branch_required_title_check` | pending |
