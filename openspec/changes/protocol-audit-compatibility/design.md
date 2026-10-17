## Context

The audit found mismatched wire protocols and admission gaps at existing owner
boundaries. The default P0 Vision path remains classical. Optional roles remain
disabled by default and research restrictions stay enforced.

## Goals / Non-Goals

- Goal: reject incompatible artifacts, validate canonical identities, and prove
  supported paths with real pinned engines and synthetic local credentials.
- Goal: preserve PQE HOLD and repair its release history.
- Non-goal: deploy, rotate credentials, add listeners, enable PQE, H3 or MASQUE.

## Decisions

- Refuse sing-mux delivery to Xray rather than substitute another incompatible
  multiplexing protocol. Retain Xray Mux.Cool smoke and supported Vision/XUDP.
- Use the shared runtime-release archive transaction for mtg; validate FakeTLS
  structure in controller admission and native parsing before publication. Use
  the local release identity `<upstream-version>+archive.1` so an existing
  same-version raw-binary receipt stays immutable and recoverable. Native version
  checks and archive member names retain the upstream version. Exercise migration
  from a genuine legacy receipt, failed admission, publication and idempotence.
- Normalize REALITY shortIds as decoded zero-padded eight-byte values for duplicate
  comparison. Require nonempty even-length hex and retain per-device UUID ownership.
- Exclude request-bearing Naive error namespaces and verify failed CONNECT logs.
- Keep VLESS decryption none. Correct documentation rather than weaken PQE guards.
- Represent Finalmask through the pinned typed stream contract or refuse an
  unsupported form; no setting may silently disappear.
- Use the existing required native CI lane for real binary checks. Tests must fail
  when required engines are unavailable; fixtures may test orchestration separately.
- Review same-family Naive and Snell stable pins with exact checksums and native
  validation. Do not promote an optional role or change its TCP-only contract.

## Contracts and ownership

- Client lane owns client_payload.py, liveness_profiles.py, Xray template and
  related export, P0 and native compatibility tests.
- Identity/mtg lane owns secrets schema, validate-secrets.py, transport_semantics.py,
  probe-matrix-target, FakeTLS helpers, related tests and PQE policy documents.
- Alternative lane owns Naive/Snell roles, exact native build inputs, their tests,
  CLIENT-NOTES and refinement documentation.
- Integration owns Makefile, CI, task lifecycle, snapshots, shared folder notes,
  verification and PR metadata. Shared files are edited only in this lane.
- Terraform, cloud-init, provider configuration and private inputs are unchanged.

## Risks / Trade-offs

- Invalid historical inputs now fail earlier. Diagnostics must identify fields
  without showing credentials. No automatic secret rewrite is allowed.
- Refusing P0 mux output removes a broken delivery shape. Valid Vision artifacts
  remain supported and must retain positive native compatibility checks.
- Native tests require verified downloads and local resources. CI provides the
  isolated Linux authority; host test results remain distinct from production.

## Migration Plan

Land source fixes and required checks together. Existing nodes change only on a
separately authorized deployment. Operators must replace invalid input and use a
supported P0 client before that operation. A source revert restores the prior
contract; no live state is mutated by this task. Validate focused regressions,
review rendered snapshots, run make check, complete independent structured and
security reviews, then require exact-head CI before merge.

## Required test dependency

CI exposed an existing Debian test-image security failure on the unchanged main
source. Dependency task CIC-1792268380780556 advances all active consumers to the
already published digest that passes the existing scan. This refresh changes no
runtime image, deployment or scan policy. Native migration failures must expose
only static task labels and categorical refusals; captured tool output remains
private. Exact-head CI remains required before merge.

## Authenticated Finalmask acceptance

The runtime-release probe must copy typed streamSettings.finalmask from the
accepted inbound into its generated Xray client. Copy it independently so probe
generation cannot change the source candidate. Real Vision and Mux.Cool cases
must pass traffic with this generated client and refuse a valid identity when
the required mask is absent. The legacy sockopt location is not a fallback.
