# SEC-1792306834441683: Repair confirmed transport audit boundaries

## Objective

Repair each confirmed audit failure and merge the reviewed source with regression evidence.

## Ownership

- Root: firewall role, split-hop-ingress role, site preflight integration, tests/native/transport_acceptance/test_hopping.py, split-hop native/unit tests, shared folder notes, planning, snapshots, gates and Git/PR lifecycle.
- Hysteria worker: scripts/client_payload.py, scripts/liveness_profiles.py, Hysteria role notes, docs/CLIENT-NOTES.md, export/liveness tests. Root serializes its small bandwidth helper addition in scripts/transport_semantics.py with the AWG worker.
- AWG/WARP worker also owns the native hopping and split-hop tests plus tests/unit/test_transport_audit_network.py. Its original lane: scripts/transport_semantics.py AWG admission, AWG and WARP role notes, WARP prepare tasks, docs/AWG-COHORTS.md, docs/RIPDPI-BUNDLE.md, tests/unit/test_transport_audit_awg_warp.py.
- DNS worker: DNS-Morph role, runtime-release YAML validator and notes, secrets schema/example, docs/PROVIDER-NOTES.md DNS section, DNS admission/lifecycle tests.
- Shared lanes: root alone edits site.yml, ansible/CLAUDE.md, scripts/CLAUDE.md, tests/CLAUDE.md, task records and generated snapshots. No worker commits or runs task lifecycle commands. No worker edits another lane without coordination.

## Execution

- [ ] SEC-1792306951999782 Repair hopping strict egress and split-hop failure boundaries with regressions #bug !high @item:SEC-1792306834441683
- [x] SEC-1792306952664722 Repair Hysteria client metadata bandwidth hints and qualified documentation #bug !high @item:SEC-1792306834441683
- [x] SEC-1792306953297349 Repair AWG wire admission and WARP key format with operator notes #bug !high @item:SEC-1792306834441683
- [x] SEC-1792306953944270 Validate DNS-Morph before mutation and require explicit echo mode #bug !high @item:SEC-1792306834441683
- [ ] SEC-1792306954609366 Run source native security and review gates then merge the protected PR #bug !high @item:SEC-1792306834441683

## Verification

Focused regressions precede make check, applicable native Linux and Molecule checks, template snapshot validation, security review and structured review. Exact-head protected CI must pass before merge. Real deployment, provider, registered vendor, physical-client and filtered-path acceptance are outside this source repair.
