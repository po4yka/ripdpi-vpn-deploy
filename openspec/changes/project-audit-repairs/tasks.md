# SEC-1791735853691219: Repair project audit defects

## Objective

Repair all sixteen REQ-AUDIT cases and publish source and validation evidence in one PR.

## Ownership

- Runtime worker: ansible runtime-release, monitoring, honeypot, firewall, watchdog, AWG verification, direct tests and snapshots, applicable role notes.
- Operator worker: issue-sub-token, rotate-secrets, promote-spare, warm-spare-watcher, Makefile admission and helper, direct tests, scripts/CLAUDE.md.
- Infrastructure worker: release configuration/workflows, install-vpnd.sh, shared cloud-init and helpers, direct release/bootstrap tests, synthetic Git/group fixtures in scripts/tests and tests/unit, applicable subtree notes.
- Primary: vpnd source/templates/tests, diagnostic script address support if required, task/spec artifacts, root tests/CLAUDE.md and integration.
- Shared lane: scripts/CLAUDE.md additions from other workers go to primary after operator completes. Only primary updates task state and commits. Coordinate any additional overlapping path first.

- CI repair ownership: runtime worker owns the retirement consumer mappings and logrotate renderer; operator worker owns the unique vpnd test-module name; infrastructure worker owns the runtime defaults contract assertion and installer-test import; primary owns shared notes, validation evidence and publication.

## Execution

- [x] SEC-1791735997436813 Repair runtime recovery retirement IPv6 AWG and retention with regression tests #bug !high @item:SEC-1791735853691219
- [x] SEC-1791735998160729 Repair subscription binding writer locks promotion and verification admission with regression tests #bug !high @item:SEC-1791735853691219
- [x] SEC-1791735998967800 Repair release publication provenance SSH activation and isolated fixtures with regression tests #bug !high @item:SEC-1791735853691219
- [x] SEC-1791735999672160 Repair diagnostic host scope and recipient origin and QR artifacts with regression tests #bug !high @item:SEC-1791735853691219
- [x] SEC-1791736000413192 Run integrated checks independent review and prepare the exact-source PR #bug !high @item:SEC-1791735853691219

## Verification

Run focused behavior tests for each lane, snapshot-check, make check, independent source review and exact-source PR CI. Native Linux and provider/client evidence remain separate; this source PR does not authorize deployment.
- [ ] SEC-1791740843514856 Repair hosted CI and scanner findings and verify the updated PR head #bug !high @item:SEC-1791735853691219
