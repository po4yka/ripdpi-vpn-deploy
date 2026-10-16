# ANS-1791618048083304: Deliver interface-correct dual-stack AmneziaWG forwarding and configurable MTU

## Objective

Deliver interface-correct dual-stack AmneziaWG forwarding and configurable MTU. Implementation is authorized in the dedicated worktree. Checkboxes require their named observed evidence; source, native, emulator, Android native-core and fleet results remain distinct.

## Ownership

- ansible/roles/firewall/templates/nftables.conf.j2
- ansible/roles/firewall/CLAUDE.md
- ansible/roles/amneziawg/templates/awg0.conf.j2
- ansible/roles/amneziawg/defaults/main.yml
- ansible/roles/amneziawg/tasks/instances.yml
- ansible/roles/amneziawg/CLAUDE.md
- secrets/schema.json
- scripts/validate-secrets.py
- scripts/new-client.sh
- scripts/rotate-secrets.sh
- scripts/emit-awg.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- contract/ripdpi-bundle.schema.json
- docs/RIPDPI-BUNDLE.md
- docs/AWG-COHORTS.md
- tests/unit/test_firewall_egress_policy.py
- tests/unit/test_real_vps_awg_nat_lane.py
- tests/unit/test_bundle_schema.py
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] ANS-1791618053112824 Extend canonical device identity and published consumers to typed dual-stack addresses and shared MTU #feature !high @item:ANS-1791618048083304
- [x] ANS-1791618053810186 Converge interface-correct isolated forwarding and NAT with complete failure compensation #feature !high @item:ANS-1791618048083304
- [ ] ANS-1791618054450509 Deliver exact client and liveness parity and qualified cross-repository contract integration #feature !high @item:ANS-1791618048083304
- [ ] ANS-1791618055065632 Prove bidirectional constrained-path traffic no-leak failure and revocation then complete source gates #feature !high @item:ANS-1791618048083304

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_firewall_egress_policy.py tests/unit/test_bundle_schema.py tests/unit/test_real_vps_awg_nat_lane.py`
- `make snapshot-check`
- `make test-native-runtime`
- `build-gate -- make check`
- `Existing when the qualified peer checkout is available: make task-federation PEER_ROOT=<RIPDPI-checkout>`
- `NEW make test-awg-dualstack-runtime; implementation must add authenticated dual-family TUN forwarding MTU and no-leak cases to the canonical native lane`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

### Android emulator gate

Android acceptance for this change uses the exact supported arm64 core with S3=S4=0 on an authorized emulator. Record exact client/core/ABI/OS and invocation-bound APK/library evidence; exercise authenticated IPv4/IPv6 TCP, UDP and DNS at MTU 1280 and 1420 through three reconnect cycles each. Physical-device and Android VpnService/TUN acceptance are outside this change, as explicitly requested by the owner. Linux native tests retain forwarding, revocation, tunnel-death lockdown and complete activation compensation requirements. Fixtures or hand-written success records cannot satisfy runtime acceptance.

Native `make test-native-runtime` and the dependency-provided native acceptance targets run only on the explicitly isolated Linux root/systemd/TUN host. macOS or missing privileges are prerequisite failures, never silent skips or mocked substitutes.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
