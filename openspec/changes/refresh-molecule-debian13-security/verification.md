---
task_id: SEC-1787810718115433
change: refresh-molecule-debian13-security
commit_sha: 07b16874f67f44b3aa4b004ffe7234229b0d661d
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: "PR run 33046238741 passed at commit 07b16874f67f44b3aa4b004ffe7234229b0d661d, including pytest unit tests and the hosted Molecule matrix."
dry_run: not_applicable
dry_run_evidence: No Terraform or deployment-plan surface is changed.
staging: not_applicable
staging_evidence: The published Molecule image is CI-only and has no staging deployment.
live: not_applicable
live_evidence: No production infrastructure is changed.
client: not_applicable
client_evidence: No client-facing configuration or artifact changes.
artifact: required
artifact_evidence: "Publisher run 33045335444 built and scanned ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13@sha256:fd0443883979e0879e912231914df2093769d45fcb82af251704b30e2fc5c42e successfully."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DEBIAN-MOLECULE-IMAGE-SECURITY | SEC-1787810718115434 | Publisher run 33045335444 and scanned digest `sha256:fd0443883979e0879e912231914df2093769d45fcb82af251704b30e2fc5c42e` | passed remotely |
| REQ-DEBIAN-MOLECULE-DIGEST-CONSISTENCY | SEC-1787810718115435 | All 35 Debian Molecule references repinned; old digest search returned no matches | passed locally |
| REQ-DEBIAN-MOLECULE-SECURITY-NO-BYPASS | SEC-1787810718115436 | PR run 33046238741 passed after the digest contract update; no `.trivyignore` change or policy bypass was used, and publisher run 33045335444 reported the Trivy scan successful | passed remotely |
