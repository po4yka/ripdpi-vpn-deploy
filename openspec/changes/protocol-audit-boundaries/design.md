## Context

The audit observed eight defects in otherwise guarded protocol paths. The
repair changes admission and serialization, not protocol engines or runtime
pins. The source baseline is c00be573277bcb7de29dd365eb7bce9b7f344843.

## Goals / Non-Goals

- Goal: implement REQ-PAB-LOG, URL, UUID, AWG, JSON, HOP, SAN and EXTRAS with
  regression evidence at their real producer or consumer boundary.
- Non-goal: change AWG backend selection, PQE HOLD, arm64 support, Realm peers,
  multiplex support, live hosts or credentials.

## Decisions

- Set categorical access logging and URI-free error handling at subscription
  server scope. Keep matching-location rate limits and diagnostics intact.
- Use the existing bare subscription path for generated remote import and QR
  URLs. Do not add another public alias or change token lifetime or authority.
- Compare VLESS authentication identities using pinned Xray normalization,
  including parsed UUID bytes and its reserved byte treatment. Refuse aliases;
  never rewrite operator credentials.
- Reserve every AWG server host address against every peer prefix. Preserve
  valid routed prefixes and nonconflicting overlapping pools.
- Serialize credential strings with the existing JSON filter. Compare parsed
  server, smoke and emitted-client values, not only successful JSON parsing.
- Refuse RIPDPI Hysteria hopping before publication. Keep official sing-box
  support and exact profile semantics; do not silently downgrade the route.
- Match certificate names with the native certificate matcher and require DNS
  SAN authority. Preserve expiry, self-signing and public-key checks.
- Populate Hysteria extensions independently for each emitted tag.

## Contracts and ownership

- No Terraform, cloud-init, secrets schema or runtime version changes.
- Proxy worker: VLESS identity validation, Snell/Trojan templates, related tests
  and role notes. It edits the cohort section of transport_semantics.py first.
- UDP worker: AWG validation and binding tests. It edits the AWG section of
  transport_semantics.py only after the proxy worker releases the file.
- Delivery worker: subscription template, vpnd share URLs, client_payload.py,
  delivery regressions and its role/vpnd notes.
- Primary: certificate preflight/tests, shared scripts/tests/Ansible notes,
  OpenSpec/task lifecycle, integration, review, commits, PR and main acceptance.
- Shared task files, generated board and lifecycle commands have one writer:
  the primary. Workers do not commit or change shared planning artifacts.

## Risks / Trade-offs

- Existing ambiguous credentials or addresses now refuse. Report categories;
  preserve operator inputs and require an explicit later correction.
- Previously generated broken import links need regenerated recipient pages.
  The existing canonical subscription URL remains compatible.
- A format refusal can remove an accidental partial-delivery path. This is
  intentional: a successful artifact must not conceal an unsupported node.
- Synthetic tests do not prove current host log state or physical-client
  connectivity. Native hosted checks and source acceptance stay distinct.

## Migration Plan

Run the focused regressions, render/snapshot checks, task validation and full
make check. Review the complete diff with security-review and autoreview.
Open one scoped PR, require its complete CI, merge through protected main,
then verify every required context on the exact resulting main SHA.
No deployment is included. A source revert restores prior behavior but must
not be used to re-admit unsafe credentials or suppress a failed safety gate.
