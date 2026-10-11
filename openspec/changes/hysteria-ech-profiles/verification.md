---
task_id: "ANS-1791618083683925"
change: "hysteria-ech-profiles"
commit_sha: null
local: "required"
local_evidence: "complete affected suites and exact native positive/failure cases after implementation"
remote_ci: "required"
remote_ci_evidence: "terminal exact-SHA protected-source checks for this new capability"
dry_run: "not_applicable"
dry_run_evidence: "source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization"
staging: "required"
staging_evidence: "separately authorized bounded 48-hour candidate soak and exact rollback before promotion"
live: "not_applicable"
live_evidence: "no production rollout belongs to this source or disabled-default candidate task"
client: "required"
client_evidence: "actual supported recipient parser and real authenticated protocol behavior"
artifact: "required"
artifact_evidence: "private rendered outputs and redacted exact-source requirement-specific evidence after implementation"
---

# Verification

## Requirement evidence

All rows name planned acceptance, not observed implementation evidence. Planning validation is recorded separately in the final handoff. Populate exact source SHA and real test/CI/client artifacts only after execution.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-ECH-CONTRACT | ANS-1791618091815754 | Exact native server and recipient parser/connection matrix, schema boundaries and qualified RIPDPI integration if included; placeholders and refusal-only tests are insufficient. | required |
| REQ-PROTO-ECH-CONTRACT | ANS-1791618093172970 | Exact native server and recipient parser/connection matrix, schema boundaries and qualified RIPDPI integration if included; placeholders and refusal-only tests are insufficient. | required |
| REQ-PROTO-ECH-CONTRACT | ANS-1791618095149688 | Exact native server and recipient parser/connection matrix, schema boundaries and qualified RIPDPI integration if included; placeholders and refusal-only tests are insufficient. | required |
| REQ-PROTO-ECH-PRIVATE | ANS-1791618093172970 | Packet capture and exact client telemetry establish negotiated ECH; real wrong-SAN/untrusted certificate cases and verbose synthetic-key leak regressions enforce privacy. | required |
| REQ-PROTO-ECH-PRIVATE | ANS-1791618094259404 | Packet capture and exact client telemetry establish negotiated ECH; real wrong-SAN/untrusted certificate cases and verbose synthetic-key leak regressions enforce privacy. | required |
| REQ-PROTO-ECH-PRIVATE | ANS-1791618095149688 | Packet capture and exact client telemetry establish negotiated ECH; real wrong-SAN/untrusted certificate cases and verbose synthetic-key leak regressions enforce privacy. | required |
| REQ-PROTO-ECH-ACTIVATE | ANS-1791618094259404 | Real private-file and systemd compensation/intent tests with exact Hysteria connections; wrong-key, unsafe-path and interrupted-publication cases preserve prior generation. | required |
| REQ-PROTO-ECH-ACTIVATE | ANS-1791618095149688 | Real private-file and systemd compensation/intent tests with exact Hysteria connections; wrong-key, unsafe-path and interrupted-publication cases preserve prior generation. | required |
| REQ-PROTO-ECH-ACCEPT | ANS-1791618095149688 | NEW exact ECH native target plus separately authorized supported-recipient staging procedure, negotiated packet observations and guarded cleanup evidence. | required |
