# ASN Exposure Denylist Gate

This note defines a safe design boundary for a future server-side denylist gate based on external ASN and service-network feeds. It is intentionally non-deployable: it contains no ranges, no generated rule payloads, no firewall commands, and no provider-specific policy.

## Objective

Reduce direct exposure between stack nodes and high-risk service-network ecosystems that may participate in telemetry, probing, or reputation workflows. The gate is a hardening layer, not a transport feature and not a substitute for role separation, public-surface minimization, probe rate limits, credential hygiene, monitoring, and disposable-node rebuilds.

## Source Inputs

Allowed provenance inputs for the first design pass:

- `https://github.com/C24Be/AS_Network_List`
- `https://docs.google.com/spreadsheets/d/1YWS5aMEykkM9koxcZW1q_bZBi2j1UGmTbhFhOfnrd4k/edit?gid=2065371898#gid=2065371898`

These sources may be referenced by URL and evaluated for update cadence, license, trust, and coverage gaps. Do not copy source rows, ranges, generated rule files, firewall snippets, or route payloads into this repo.

## Adoption Model

The first implementation must be a review gate, not enforcement:

- schema for feed metadata and policy intent;
- parser validation that classifies input shape without preserving inventory rows in docs;
- diff summary for added/removed source groups;
- dry-run output that reports counts, source provenance, and affected policy direction only;
- log-only/canary mode before any blocking behavior;
- explicit rollback criteria and disabled-by-default toggles.

Ingress and egress policy are separate decisions. Ingress filtering answers "who can directly reach this node"; egress filtering answers "what service-network ecosystems this node or forwarded traffic may contact." Treat them as separate review surfaces with separate false-positive analysis.

## Required Artifacts

Any implementation proposal must produce these documents or files before enforcement is considered:

- `docs/ASN-EXPOSURE-DENYLIST.md` as the design boundary and safety contract.
- A schema document or checked schema file for feed metadata, source trust, update cadence, license, policy direction, and rollout mode.
- Placeholder-only fixtures that exercise the schema without real ranges, ASNs, generated rules, provider names, operators, carriers, or geography-specific cohorts.
- A redacted dry-run report format that shows source URLs, validation status, added/removed counts, policy direction, and risk notes, but never prints inventories.
- An operator runbook section that defines review, log-only/canary rollout, false-positive monitoring, rollback criteria, and ownership.
- Tests proving that disabled-by-default behavior leaves the rendered firewall unchanged.

## Integration Points

The first safe integration surface is documentation and validation. Runtime enforcement, if ever approved, belongs behind explicit toggles in Ansible group variables and must render through the existing firewall role without bypassing its validate-before-reload path. The `vpnd` CLI may expose a review or dry-run helper only after the schema and redaction rules are stable; it must not become a hidden updater that fetches feeds and applies policy.

## Non-Goals

- No bundled ASN or IP inventory in the repo.
- No ready-to-load nftables, ipset, route, or provider firewall rules in docs.
- No geography-, carrier-, ISP-, or operator-named variables, files, cohorts, or comments.
- No default-on blocking behavior.
- No dependency on external knowledge stores or page slugs.

## Verification Requirements

Before any enforcement code lands, a task must define:

- schema fixtures that contain placeholder data only;
- unit tests for source metadata parsing and validation;
- snapshot tests for redacted dry-run summaries;
- a molecule or integration test that proves disabled-by-default behavior leaves the rendered firewall unchanged;
- an operator runbook section documenting review, canary, false-positive monitoring, and rollback without deployable rule payloads.

## Open Questions

- Which source-trust states are needed: primary maintained repository, supplemental sheet, local operator override, and rejected source may be enough for the first schema.
- Whether egress exposure policy should apply to host-originated traffic only, forwarded VPN client traffic only, or both must be an explicit operator choice.
- Whether feed refresh belongs outside Ansible as a human-reviewed artifact update, or inside automation as a dry-run-only fetcher, remains unresolved.
