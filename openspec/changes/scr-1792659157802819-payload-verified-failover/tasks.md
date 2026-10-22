# SCR-1792659157802819

## Objective

Ship exact useful-data probes, coordinated recipient selection and opt-in alternate listeners.

## Ownership

- Probe worker owns `scripts/probe-payload-throttle.sh`,
  `scripts/payload_probe_content.py`, `scripts/serve-payload-probe.py`,
  `tests/unit/test_probe_payload_throttle.py`, and `docs/how-to/payload-throttle.md`.
  Its delegated listener lane also owns provider listener defaults/examples/tests
  and provider notes, synthetic listener/inventory fixtures, render defaults and
  snapshots, listener parity tests, Xray role notes and `docs/reference/client-notes.md`.
- Parent owns `scripts/client_payload.py`, the canonical bundle schema and its
  validation tests, Ansible listener defaults, disposable CI listener inputs,
  canonical Make argument handling and shared recipient regression fixtures.
- Client worker owns the coordinated RIPDPI consumer in its isolated checkout;
  its own repository lifecycle records exact paths and verification.
- Parent serializes all shared `CLAUDE.md`, Makefile, task/spec/board edits,
  contract synchronization, commits and deployment PR operations. Workers must
  preserve unrelated edits and request ownership before editing other paths.

## Execution

- [x] SCR-1792659429313208 Verify bounded download and upload payloads through explicit transports #feature !high @item:SCR-1792659157802819
- [ ] SCR-1792659429925062 Deliver typed payload failover policy to the coordinated client #feature !high @item:SCR-1792659157802819
- [x] SCR-1792659430538417 Make alternate REALITY listeners explicit across runtime and provider contracts #feature !high @item:SCR-1792659157802819

## Verification

Run real local HTTP/SOCKS transfer regressions, typed policy/recipient tests,
listener/profile tests, reviewed snapshots, Terraform mock tests, `make check`,
client runtime/controller tests, security review and protected PR checks.
Provider, production and physical-network acceptance are not part of this source change.
