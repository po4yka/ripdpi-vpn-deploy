## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.

# Change: Deliver isolated native acceptance for every baseline transport

Task ID: `TST-1791618356595983`

## Why

Existing synthetic role fixtures and external sentinel capabilities cover different boundaries. Six original findings now have integrated source fixes, but warm daemon adoption, real hopping, default XHTTP completion and exact source regression still need a runnable isolated native acceptance contract.

Audit coverage: A03, A07, A08, A09, A12, A14, A22; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Deliver one isolated Linux runner that executes exact pinned client/server sockets and AWG TUN while preserving existing quick fixture tests.
- Exercise positive traffic, secure rejection, warm upgrades, retirement, authority compensation and repeated convergence.
- Retain distinct source/native, optional staging, physical-client and live evidence; do not revive cancelled acceptance work.

## Capabilities

### New Capabilities

- `transport/native-acceptance`: deliver isolated native acceptance for every baseline transport.

### Modified Capabilities

- None.

## Impact

- tests/unit/test_protocol_liveness.py
- tests/unit/test_liveness_profiles.py
- tests/unit/test_amneziawg_native_lifecycle.py
- tests/unit/test_nginx_transaction_native.py
- tests/unit/test_monitoring_logrotate.py
- ansible/molecule/full-stack/
- docs/TESTING.md
- Makefile
- Canonical Make runner composing the existing native fixtures and complete named suites
- Existing isolated native CI lane extended through its current selector
- Implementation and local acceptance are authorized; provider, private operator input and deployment actions remain outside scope.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
