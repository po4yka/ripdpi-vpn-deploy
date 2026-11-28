---
task_id: ANS-1795328948145006
change: ans-1795328948145006-egress-proxy-node-w5
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
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-EGRESS-CONNECT-ONLY | ANS-1795329034006860 | Molecule denial tests including IPv4/IPv6 literals with allowlisted PTR names | planned |
| REQ-EGRESS-TAILNET-ONLY | ANS-1795329045195870 | public scan negative and tag:ci-deploy negative receipts | planned |
| REQ-EGRESS-SECRETLESS | ANS-1795329034006860 | Molecule file audit; `security-review` checklist | planned |
| REQ-EGRESS-HARDENED | ANS-1795329034006860 | Molecule `systemd-analyze security` score | planned |
| REQ-EGRESS-FIXED-ADDRESS | ANS-1795329022845451 | `tofu test` replacement case; recreation drill | planned |
| REQ-EGRESS-PROVIDER-PROOF | ANS-1795329056411801 | proxy log per provider in the ops repository receipt (`receipts/egress-proxy-w5-20261128/provider-proof.json`): five plans through the proxy, CONNECT to every provider host and the state host | passed 2026-11-28 |
| REQ-EGRESS-ALLOWLISTS | ANS-1795329068636739 | Vultr direct-call negative receipt (same file): access list holds only the egress `/32`; direct call 401, proxied call 200 | passed 2026-11-28 |
| REQ-EGRESS-BREAK-GLASS | ANS-1795329082564404 | Stopped-service SSH repair and lost-server direct bootstrap with retained address and backend lock: ops receipt `receipts/egress-proxy-w5-20261128/break-glass.json` (stopped-service drill; lost-server path run as a real recovery; temporary Vultr entry documented, not exercised) | passed 2026-11-28 |
