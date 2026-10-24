---
task_id: OPS-1792820562787120
change: ripdpi-hysteria-port-hopping
commit_sha: 756f5a64cdea531b017fc78d0a01b57236aa27cb
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
client: passed
client_evidence: Recipient PR 661 merged as e22c8d66d8fa0c9245eb5bf8ef802e24028d0f48 and its exact-main CI passed. Linux acceptance passed all eight real-peer hopping cases and the GRO regression with no skips. Recipient closure PR 663 reached fbd57b32b0eb24a915ef3d96c57b0686d8444d97; all four main workflows passed. No physical-device result is claimed.
artifact: passed
artifact_evidence: The hopping bundle passed semantic validation and matches the fixture on recipient main byte for byte. The verified Android artifact contains the qualified native engine; package and native hashes passed the canonical checks. Details and retained artifact digests are below.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-HY-COMPATIBILITY | OPS-1792820856126759 | Targeted recipient payload tests and full local gate | required |
| REQ-AUDIT-HY-COMPATIBILITY | OPS-1792820857234441 | Paired client real-server hopping, IPv6, Salamander, import tests, Linux GRO and exact-main CI | passed |
| REQ-DR-HOPPING-ADMISSION | OPS-1792820856126759 | Positive policy parity and atomic failure tests | required |
| REQ-DR-HOPPING-ADMISSION | OPS-1792820858662402 | Exact producer and client PR and main terminal hosted checks | required |

## Current source evidence

- Targeted recipient hopping, payload boundary, bundle schema, transport semantics, host selection and Hysteria audit tests: 307 passed.
- Full bundle consistency regressions reproduced 17 invalid-policy admissions before the fix. After the fix, 164 bundle and recipient tests plus 202 transport, recipient boundary, emitter roundtrip and Hysteria audit tests passed. Standalone extensions, either policy form alone and equivalent normalized policies remain valid.
- Follow-up source review reported one Unicode exception concern. A direct CLI reproduction rejected the surrogate with exit 1 and no traceback: `UnicodeEncodeError` inherits `ValueError`, which the boundary already catches. The finding was rejected; no actionable follow-up finding remains.
- Documentation checks: 10 passed. The generated hopping bundle passed semantic validation.
- Task contracts and strict OpenSpec validation passed. Independent source review found no code defect.
- The full local check exposed two local tool mismatches: setuptools 84.0.0 instead of 84.2.1, then sing-box 1.13.16 instead of 1.14.3. An isolated Python environment and a process-local PATH select the pinned versions. Package reproducibility, offline installation and rollback passed; the full check remains required.
- Paired native source `764d7519483e5879d3ae58c1b532723df16dbfbd` passed eight hopping cases across IPv4/IPv6, plain/Salamander and fixed/random intervals, plus ordinary TCP/UDP, auth rejection and TLS rejection. Each hopping case preserved one authenticated session across three local/remote port changes and verified 20 TCP replies of 8208 bytes and 60 distinct UDP replies of 2736 bytes. Cleanup passed in every case. The test peer is Hysteria 2.13.0, which matches the public server example; no live server version is inferred.
- Local peer tests consumed actual Kotlin serializer outputs. The client lane also passed 3911 targeted Kotlin tests and 295 affected native tests. Final client qualification is recorded below.
- Source review identified paired client qualification as a release precondition. That precondition now passes. The producer's full local gate and protected PR/main checks remain required. No device or fleet completion is claimed here.

## Qualified recipient and artifact

Recipient PR `po4yka/RIPDPI#661` passed its final checks at
`b8b2eca0294973df68f52ecddcafcef6ccc62c8a` and merged as
`e22c8d66d8fa0c9245eb5bf8ef802e24028d0f48`.
Exact-main CI run `40085973754` completed with 48 successful jobs and 16
jobs excluded by path rules. Its native and Android
checks passed. Closure PR `po4yka/RIPDPI#663` then preserved the review,
terminal and purge history at `fbd57b32b0eb24a915ef3d96c57b0686d8444d97`.
CI `40089743265`, fleet fixtures `40089743241`, Secret Scan `40089743239`
and CodeQL `40089743267` all passed on that exact main commit.

Linux acceptance run `40082693795`, job `120839369907`, passed the GRO
regression and all eight actual Hysteria peer cases without skips. Its source
was the tested merge `e87c9428636e72d641d6940afd3269efa759b27a`. Artifact
`12555917006` has ZIP SHA-256
`0dec7e9ecc99ef95c3b02873ff041c89f81aa6d98e7fbc16aa4722474baef63c`.
The report SHA-256 is
`12cca6ce8c5cebfbb99e0547d230193916fe87b8eea7de3f64deda4cd369e507`.
Each case proves traffic through three scheduled destination-port changes,
with IPv4/IPv6, plain/Salamander and fixed/random intervals covered. Cleanup
passed. These are owned test peers, not a deployed fleet.

Android artifact `12556472475` from run `40082693780` has ZIP SHA-256
`4d3b54c898c32c68d66c0c660f62148b905297a0d8d5aef152444e86628f19c6`.
Its PR head is `b8b2eca0294973df68f52ecddcafcef6ccc62c8a`; its tested source
is `e87c9428636e72d641d6940afd3269efa759b27a`.
Canonical verification passed all six APK hashes and package identities.
The Full and Simple APKs each contain 38 DEX files and 16 64-bit x86_64
ELF files. All their PT_LOAD segments meet the 16 KiB alignment requirement.
Their shared relay library SHA-256 is
`254fdbe9b1bc485d69f62a5263a8d16690c2edd71096b2613d149677160e3dc5`.
All four native ABI lanes passed. No physical-device test is inferred.

The producer fixture `contract/ripdpi-bundle.hysteria-port-hopping.json`
passes `scripts/validate-bundle.py` and matches the fixture on recipient main
byte for byte. The final producer gate must still pass after the independent
terminal-review cleanup fix is integrated.
