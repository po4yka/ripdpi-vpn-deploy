# EPC-1792155716043904: Deliver the local four-protocol reliability roadmap

## Objective

Deliver the complete local four-protocol behavior and all retained positive domain
requirements. Supersede the former external scope without claiming staging,
recipient-device or production results. Open steps require observed acceptance.

## Ownership

- `scripts/client_payload.py`, `scripts/transport_semantics.py`, `scripts/liveness_profiles.py`, `scripts/protocol-liveness.py` and REALITY validator/monitor/scanner entry points.
- `ansible/roles/watchdog/templates/`, `ansible/playbooks/smoke-test.yml`, secrets schema/examples and existing guarded runtime, Hysteria, AWG, firewall interfaces.
- Native fixtures and regression suites under `tests/`, including complete four-protocol traffic, ownership, rollback, source-candidate and parser checks.
- `Makefile`, existing CI selector, reviewed snapshots and relevant operator documentation.
- This linked change, supersession of the former roadmap scopes and taskctl-only portfolio lifecycle; preserve historical observations and unchanged completed predecessor records.
- One primary writer serializes all shared source, schema, snapshot and portfolio edits in the dedicated worktree. Preserve unrelated work and private operator inputs.

## Execution

- [ ] EPC-1792156116769877 Deliver isolated baseline transport and canonical per-device payload identity #feature !high @item:EPC-1792155716043904
- [ ] EPC-1792156184465728 Deliver real dual-stack AWG forwarding MTU revocation and source-candidate adoption #feature !high @item:EPC-1792155716043904
- [ ] EPC-1792156185783587 Deliver stable Hysteria resources trusted ECH and verified local parser upgrades #feature !high @item:EPC-1792155716043904
- [ ] EPC-1792156186791455 Deliver selectable XHTTP endpoints typed tuning and measured degraded-path delivery #feature !high @item:EPC-1792155716043904
- [ ] EPC-1792156187806825 Deliver finite REALITY target identity hygiene and bounded monitor ownership #feature !high @item:EPC-1792155716043904
- [ ] EPC-1792156189132400 Deliver topology-aware secure probes and retained runtime recovery authority #feature !high @item:EPC-1792155716043904
- [ ] EPC-1792156196617565 Complete real no-skip protocol lifecycle compensation and exact-source acceptance #feature !high @item:EPC-1792155716043904

## Verification

- `make liveness-profile-check`, focused identity/validator/watchdog/endpoint suites and reviewed snapshots.
- `build-gate -- mise exec -- make check` on the exact committed source and complete credential-free federation validation.
- `make transport-native-acceptance` (with the workstation build gate held once by its outer runner) inside owned isolated Linux/systemd/TUN with real pinned runtimes and zero selected skips.
- Complete `make test-transport-runtime-acceptance` in a separate fresh owned Linux root; no existing consumer authority may be adopted as a fixture.
- AWG source-candidate evidence retains its exact source/pair/build identity; no physical or external acceptance is inferred.
- Requirement mappings and local/client/artifact evidence remain required in verification.md until observed. Automatic PR checks are supplementary; external soak, recipient devices, deployment and promotion are excluded.
