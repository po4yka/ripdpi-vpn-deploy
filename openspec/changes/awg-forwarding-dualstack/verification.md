---
task_id: "ANS-1791618048083304"
change: "awg-forwarding-dualstack"
commit_sha: null
local: "required"
local_evidence: "complete affected suites and exact native positive/failure cases after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal exact-SHA protected-source checks for this new capability"
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "not_applicable"
staging_evidence: "source contract uses isolated native acceptance; actual fleet rehearsal is separately authorized"
live: "not_applicable"
live_evidence: "no production rollout belongs to this source or disabled-default candidate task"
client: "required"
client_evidence: "actual supported recipient parser and real authenticated protocol behavior; physical Android arm64 must establish the exact currently supported baseline core, three reconnects, DNS and sustained bidirectional transfer; S3/S4 floor remains unchanged"
artifact: "required"
artifact_evidence: "private rendered outputs and redacted exact-source requirement-specific evidence after implementation"
---

# Verification

## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-FORWARD | ANS-1791618053810186 | Extend firewall render tests and add real nftables namespace enforcement with exact AWG clients, observing per-instance counters and return traffic. | required |
| REQ-PROTO-AWG-FORWARD | ANS-1791618055065632 | Extend firewall render tests and add real nftables namespace enforcement with exact AWG clients, observing per-instance counters and return traffic. | required |
| REQ-PROTO-AWG-DUAL | ANS-1791618053112824 | Exact server/client namespace tests plus qualified recipient parser round trips, separate IPv4 IPv6-only and DNS observations, and one-device revocation in each family. | required |
| REQ-PROTO-AWG-DUAL | ANS-1791618054450509 | Exact server/client namespace tests plus qualified recipient parser round trips, separate IPv4 IPv6-only and DNS observations, and one-device revocation in each family. | required |
| REQ-PROTO-AWG-DUAL | ANS-1791618055065632 | Exact server/client namespace tests plus qualified recipient parser round trips, separate IPv4 IPv6-only and DNS observations, and one-device revocation in each family. | required |
| REQ-PROTO-AWG-MTU | ANS-1791618053112824 | Shared resolution boundary tests, exact client parser tests and controlled link-MTU namespace transfers; record throughput and loss instead of claiming an arbitrary preset optimal. | required |
| REQ-PROTO-AWG-MTU | ANS-1791618054450509 | Shared resolution boundary tests, exact client parser tests and controlled link-MTU namespace transfers; record throughput and loss instead of claiming an arbitrary preset optimal. | required |
| REQ-PROTO-AWG-MTU | ANS-1791618055065632 | Shared resolution boundary tests, exact client parser tests and controlled link-MTU namespace transfers; record throughput and loss instead of claiming an arbitrary preset optimal. | required |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618053810186 | Linux routing/nft packet capture plus supported physical recipient tests, failed activation compensation and prior-address/profile preservation assertions. | required |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618054450509 | Linux routing/nft packet capture plus supported physical recipient tests, failed activation compensation and prior-address/profile preservation assertions. | required |
| REQ-PROTO-AWG-NOLEAK | ANS-1791618055065632 | Linux routing/nft packet capture plus supported physical recipient tests, failed activation compensation and prior-address/profile preservation assertions. | required |
