---
task_id: SEC-1787810718115433
change: refresh-molecule-debian13-security
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No Terraform or deployment-plan surface is changed.
staging: not_applicable
staging_evidence: The published Molecule image is CI-only and has no staging deployment.
live: not_applicable
live_evidence: No production infrastructure is changed.
client: not_applicable
client_evidence: No client-facing configuration or artifact changes.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DEBIAN-MOLECULE-IMAGE-SECURITY | SEC-1787810718115434 | Publisher run, exact GHCR digest, and Trivy HIGH/CRITICAL scan | pending |
| REQ-DEBIAN-MOLECULE-DIGEST-CONSISTENCY | SEC-1787810718115435 | Repository-wide old-digest search and changed Molecule references | pending |
| REQ-DEBIAN-MOLECULE-SECURITY-NO-BYPASS | SEC-1787810718115436 | `.trivyignore` diff, workflow policy review, and hosted image scan | pending |
