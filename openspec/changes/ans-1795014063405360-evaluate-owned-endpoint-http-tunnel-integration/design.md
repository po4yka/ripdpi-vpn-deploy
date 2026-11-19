## Context

TrustTunnel defines authenticated HTTP CONNECT streams over HTTP/2 or HTTP/3 with TCP, UDP and DNS forwarding. This is an owned-endpoint alternative, unlike a third-party-account relay. The existing baseline already supplies four transports; another runtime is justified only by reproducible incremental benefit. P1 (nginx + XHTTP direct) is already HTTP-based, so the benefit must be measured against P1 first.

## Goals / Non-Goals

- Goal: implement a local qualification harness and evidence report sufficient for a go/no-go integration decision.
- Non-goal: deploy an endpoint, change live profiles, import credentials, add client protocol support or promise filtering evasion.

## Decisions

Use an isolated external runtime fixture rather than immediately adding an Ansible role. Pin released revisions and checksums after review; unknown transitive license obligations block execution. Exercise an actual paired client/endpoint, not only configuration parsing. Report exact builds, local fixture topology, timeouts, payload sizes and observed resource use without identifying network labels. A separate follow-up specification is required for production integration after admission.

## Contracts and ownership

The future harness owns `tests/integration/owned_http_tunnel/`; the qualification report belongs under `docs/research/` and must follow docs indexing conventions. Existing Terraform roots, cloud-init, Ansible roles, SOPS schema, vpnd and RIPDPI bundle remain unchanged. A native client compatibility finding must be coordinated with the peer repository, not represented as a supported bundle field prematurely.

## Risks / Trade-offs

HTTP resemblance is not proof against active fingerprinting. Endpoint reachability is a prerequisite, not an allowlist bypass. Extra runtime and certificate surface add maintenance cost; compare measured benefit to baseline before admission. Fixture credentials must be synthetic and logs redacted. Refuse arbitrary destinations and allow only isolated fixture peers; limit CPU, bytes and runtime.

## Migration Plan

No production migration in this research task. Remove disposable fixtures on failure and restore no global state because none is modified. Admission requires passed local protocol/failure tests, documented client compatibility and reviewed artifact; rejection records the reason and preserves baseline. A later authorized staging task owns any path-specific or live evidence. Planning validation: taskctl validate, OpenSpec strict validation and make docs-check. Harness implementation adds focused regression tests and selected CI without claiming live acceptance.
