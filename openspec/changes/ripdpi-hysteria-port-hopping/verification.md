---
task_id: OPS-1792820562787120
change: ripdpi-hysteria-port-hopping
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No runtime or provider change.
staging: not_applicable
staging_evidence: No staging resource mutation in this source delivery.
live: not_applicable
live_evidence: No fleet deployment or live credential action authorized.
client: required
client_evidence: Native source 764d7519483e5879d3ae58c1b532723df16dbfbd passed all eleven controlled Hysteria peer cases with actual Kotlin serializer inputs. Final client PR and main checks remain required.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-HY-COMPATIBILITY | OPS-1792820856126759 | Targeted recipient payload tests and full local gate | required |
| REQ-AUDIT-HY-COMPATIBILITY | OPS-1792820857234441 | Paired client real-server hopping, IPv6, Salamander and import tests | required |
| REQ-DR-HOPPING-ADMISSION | OPS-1792820856126759 | Positive policy parity and atomic failure tests | required |
| REQ-DR-HOPPING-ADMISSION | OPS-1792820858662402 | Exact producer and client PR and main terminal hosted checks | required |

## Current source evidence

- Targeted recipient hopping, payload boundary, bundle schema, transport semantics, host selection and Hysteria audit tests: 307 passed.
- Documentation checks: 10 passed. The generated hopping bundle passed semantic validation.
- Task contracts and strict OpenSpec validation passed. Independent source review found no code defect.
- The full local check exposed two local tool mismatches: setuptools 84.0.0 instead of 84.2.1, then sing-box 1.13.16 instead of 1.14.3. An isolated Python environment and a process-local PATH select the pinned versions. Package reproducibility, offline installation and rollback passed; the full check remains required.
- Paired native source `764d7519483e5879d3ae58c1b532723df16dbfbd` passed eight hopping cases across IPv4/IPv6, plain/Salamander and fixed/random intervals, plus ordinary TCP/UDP, auth rejection and TLS rejection. Each hopping case preserved one authenticated session across three local/remote port changes and verified 20 TCP replies of 8208 bytes and 60 distinct UDP replies of 2736 bytes. Cleanup passed in every case. The test peer is Hysteria 2.13.0, which matches the public server example; no live server version is inferred.
- Local peer tests consumed actual Kotlin serializer outputs. The client lane also passed 3911 targeted Kotlin tests and 295 affected native tests. Linux GRO, final hosted checks and the Android artifact remain separate client gates in `po4yka/RIPDPI#661`.
- Source review identified paired client qualification as a release precondition. Draft PR checks can run in parallel, but this producer must not merge or release until the qualified client reaches main. No hosted, device or fleet completion is claimed here.
