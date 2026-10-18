# XRY-1792265213021342: Repair protocol compatibility and audit validation defects

## Objective

Repair the audited protocol contracts while preserving PQE HOLD and prove the
supported paths with real pinned engines.

## Ownership

- Client lane: scripts/client_payload.py, scripts/liveness_profiles.py,
  ansible/roles/xray/templates/config.json.j2, ansible/roles/xray/CLAUDE.md,
  related P0/export tests and a dedicated native compatibility test;
  watchdog REALITY probe template, smoke-reality.yml and watchdog role notes;
  runtime-release authenticated probe generation, its role notes and regressions.
- Identity/mtg lane: secrets/schema.json, scripts/validate-secrets.py,
  scripts/transport_semantics.py, new FakeTLS validator, probe-matrix-target role,
  related identity/mtg tests, docs/PQ-REALITY-ADOPTION.md and docs/XRAY-RELEASE-LINE.md.
- Alternative lane: ansible/roles/naive/, ansible/roles/snell/,
  scripts/build-native-naive-test.sh, related Naive/Snell tests,
  docs/CLIENT-NOTES.md and docs/SNELL-REFINEMENT.md.
- Integration lane: vpnd/tests/test_update_cache.py, vpnd/CLAUDE.md,
  scripts/render-inventory.sh, its metadata regressions,
  contract/ripdpi-bundle.example.json, contract/ripdpi-bundle.golden-full.json,
  CONTRIBUTING.md, Makefile, .github/workflows/, snapshots, tests/CLAUDE.md,
  scripts/CLAUDE.md, ansible/CLAUDE.md, docs/TESTING.md, task and OpenSpec files,
  PR metadata and all commits. Shared files are serialized through this lane.


## Execution

- [x] XRY-1792265286038091 Reject incompatible mux delivery and prove supported P0 and Finalmask engines #bug !high @item:XRY-1792265213021342
- [x] XRY-1792265286826282 Repair mtg archives and identity admission while preserving PQE HOLD #bug !high @item:XRY-1792265213021342
- [x] XRY-1792265287536541 Protect Naive logs and prove current optional transport runtime compatibility #bug !high @item:XRY-1792265213021342
- [ ] XRY-1792265288315040 Integrate native CI and complete local validation and independent review #bug !high @item:XRY-1792265213021342
- [x] XRY-1792265289044732 Pass exact-head CI and merge the reviewed pull request #bug !high @item:XRY-1792265213021342

## Verification

Run focused portable and real-engine regressions, reviewed snapshots, make check,
security and structured review, then exact-head protected CI. No live deployment.
