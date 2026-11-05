---
task_id: SEC-1793774981005821
change: sec-1793774981005821-medium-security-remediation
commit_sha: 46bceb948c024118b0ebcf5156a09eca5326a3ba
local: passed
local_evidence: "Backup grant tests 11 passed; the public-site version test fails without the fix and passes with it; Terraform management tests passed in hetzner (25), scaleway (17), upcloud (27) and vultr (17); collector render, generation and operator tests 160 passed; make snapshot-check matched 174 templates. A local vmagent v1.155.0 and Prometheus 3.15.1 reproduction showed the duplicated node label before the relay fix and node=vpn-p0 after it, for a sample with forged node and ingress_node labels."
remote_ci: passed
remote_ci_evidence: "CI run 41817647971 completed successfully for 46bceb948c024118b0ebcf5156a09eca5326a3ba, including the Molecule observability_control_plane forged-label probe and the real agent remote-write check."
dry_run: passed
dry_run_evidence: "Dry-runs of 46bceb94 passed with failed=0 and unreachable=0: node-a ok=632 changed=17, node-b ok=636 changed=3, node-c ok=630 changed=2. Each preview was reviewed before deploy. Monitoring observability-validate and observability-check passed for the three agents and the node-b control plane."
staging: not_applicable
staging_evidence: The change was rolled out to the existing production nodes through the ordinary reviewed deploy transaction.
live: passed
live_evidence: "Core deploy of 46bceb94 to node-a (cohort p0-self-steal), node-b and node-c passed deploy, verify, source-drift, security-verify, smoke-test and protocol-liveness (healthy). The nodes now run 64a05385 = 46bceb94 plus the kernel-surface commits in #497, and the operator receipts show protocol verification ok on all three nodes. The monitoring agents and the node-b control plane with the relay were then deployed and bound to that core: manifest identity is match on every node, no alert is firing, and the Kuma monitors node-a, node-b, node-c and pipeline are UP. External probes: P0 without SNI presents the owned self-steal certificate, and HTTP/80 by name and by address returns Server: nginx with no version. B2: the hidden-version lifecycle is 30 days; every node backs up with an append-only key (no deleteFiles, own prefix), and the 2026-11-05 remote copy succeeded on all three nodes; the previous keys that had deleteFiles were deleted."
client: passed
client_evidence: "Protocol liveness after the P0 SNI change: the regenerated external probe probe-c-to-a completed an authenticated REALITY handshake with DNS through the tunnel against node-a."
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-OSH-BACKUP-APPEND-ONLY | SEC-1793776165979531 | Unit refusals; a live check accepts the reissued node keys and refuses the previous keys with `append-only-grant-required`; the remote copy succeeded on the new keys; the previous keys are deleted | passed |
| REQ-SEC-OSH-INGEST-NODE-LABEL | SEC-1793776927682536 | Molecule forged-label probe in CI; a live probe from node-a with `node="forged-node"` was stored under node-a's certificate identity | passed |
| REQ-SEC-OSH-SSH-PREFIX-FLOOR | SEC-1793777693877736 | Terraform tests in all four provider roots reject /23 and /47 and accept /32 | passed |
| REQ-SEC-OSH-HTTP-VERSION-HIDDEN | SEC-1793778451096956 | Render test; an external HTTP/80 probe by name and by address shows no version | passed |
| REQ-SEC-OSH-REALITY-SAME-HOST | SEC-1793778849874329 | P0 without SNI presents the owned self-steal certificate; the authenticated REALITY probe is healthy | passed |

## Residual items

- The self-steal certificate expires on 2027-02-02 and is not renewed automatically. It must be reissued off-node before then.
- PR #497 (kernel surface upstreaming) and PR #499 (image refresh for CVE-2026-109518) are separate follow-ups.
