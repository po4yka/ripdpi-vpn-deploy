---
task_id: CIC-1787209937108078
change: cic-1787209937108078-restore-dependency-pr-ci-compatibility
commit_sha: aeb30b8eb8a6b301a89e6c8b264a2c2154586309
local: passed
local_evidence: "pytest -q tests/unit/test_molecule_image_pins.py and yamllint for all Molecule scenario files passed."
remote_ci: passed
remote_ci_evidence: "GitHub Actions CI run 32356133238 passed on main."
dry_run: not_applicable
dry_run_evidence: CI-only change; no infrastructure plan is changed.
staging: not_applicable
staging_evidence: CI-only change; no staging deployment is authorized.
live: not_applicable
live_evidence: CI-only change; no live deployment is authorized.
client: not_applicable
client_evidence: No client-facing behavior changes.
artifact: passed
artifact_evidence: "Debian 13 digest sha256:0de09c528cdbf83545420a1b3a9524af9f38d65fc1b28ff6a8af1eff052987da and Ubuntu 24.04 digest sha256:48e1ab7caa1e28148148576cd2f15e46fcd9d44601125bbce7f3056306f40cf1 passed Trivy in CI run 32354855463."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CIC-1787209937108078-001 | CIC-1787209937108079 | pinned taskctl validation and hosted task-contract job | passed |
| REQ-CIC-1787209937108078-002 | CIC-1787209937108080 | published digest and Trivy HIGH,CRITICAL scan | passed |
