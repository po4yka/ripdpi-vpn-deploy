---
task_id: SEC-1787810718115433
change: refresh-molecule-debian13-security
commit_sha: "af555c20705258c989b3255e31d5cce3c7d8b4fc"
local: "passed"
local_evidence: "Reviewed immutable Debian image pins and the no-bypass workflow contract; repository governance-count test passed. Full local union gate passed in the implementation worktree; native image runtime evidence is the hosted CI matrix, not the local arm64 container attempt."
remote_ci: "passed"
remote_ci_evidence: "Exact main af555c20705258c989b3255e31d5cce3c7d8b4fc: CI run 33071688476 completed successfully with all 51 jobs including the hosted Molecule matrix."
dry_run: not_applicable
dry_run_evidence: No Terraform or deployment-plan surface is changed.
staging: not_applicable
staging_evidence: The published Molecule image is CI-only and has no staging deployment.
live: not_applicable
live_evidence: No production infrastructure is changed.
client: not_applicable
client_evidence: No client-facing configuration or artifact changes.
artifact: "passed"
artifact_evidence: "Fresh image-scan run 33075359774 completed successfully on af555c20705258c989b3255e31d5cce3c7d8b4fc, including enumeration and both exact Debian fd0443883979e0879e912231914df2093769d45fcb82af251704b30e2fc5c42e and Ubuntu 48e1ab7caa1e28148148576cd2f15e46fcd9d44601125bbce7f3056306f40cf1 digest scans. No ignores or bypasses were added."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DEBIAN-MOLECULE-IMAGE-SECURITY | SEC-1787810718115434 | Publisher run 33045335444 and scanned digest `sha256:fd0443883979e0879e912231914df2093769d45fcb82af251704b30e2fc5c42e` | passed remotely |
| REQ-DEBIAN-MOLECULE-DIGEST-CONSISTENCY | SEC-1787810718115435 | All 35 Debian Molecule references repinned; old digest search returned no matches | passed locally |
| REQ-DEBIAN-MOLECULE-SECURITY-NO-BYPASS | SEC-1787810718115436 | PR run 33046238741 passed after the digest contract update; no `.trivyignore` change or policy bypass was used, and publisher run 33045335444 reported the Trivy scan successful | passed remotely |
