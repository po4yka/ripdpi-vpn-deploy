## Context

The XHTTP backend treats an IP address as a trusted forwarded-header name, nginx and Xray disagree on schema-valid trailing-slash paths, and the public canonical origin excludes nginx's nondefault served port. These contracts cross server, proxy, validation, recipient output, liveness and Hysteria masquerade. Existing transactional nginx and fallback-log repairs are already implemented and must remain preserved.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: align xhttp endpoint paths forwarded attribution and served origins with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Choose a canonical slashless nonroot path with a leading slash and constrained segments; reject trailing slash, root, query, fragment, whitespace and directive control characters before mutation. Update every producer and consumer rather than preserving a second path grammar.
- The trusted direct proxy overwrites the backend source header with its actual peer address; incoming client forwarding headers never grant source authority. Use the exact pinned Xray header-name semantics and prove attribution through the runtime.
- Canonical HTTPS origin equals the actual primary served origin including a nondefault port; ordinary port 443 omits its default port. Explicitly review alternate-host canonical identity rather than treating canonical metadata as a socket test.
- Update nginx preflight and extra-vars validation together with Hysteria masquerade validation; never silently rewrite private operator inputs.
- Preserve complete nginx candidate transaction, bearer-log privacy, TLS floor and ordinary site behavior from integrated review changes.
- Official sing-box still receives only supported transports; RIPDPI/Xray-specific XHTTP output is validated using its exact supported engine, not the official sing-box parser.

## Contracts and ownership

- secrets/schema.json
- scripts/validate-secrets.py
- scripts/validate-ansible-extra-vars.py
- scripts/emit-singbox.sh
- scripts/liveness_profiles.py
- ansible/roles/xray/templates/config.json.j2
- ansible/roles/xray/CLAUDE.md
- ansible/roles/nginx-xhttp/tasks/enable.yml
- ansible/roles/nginx-xhttp/templates/site.conf.j2
- ansible/roles/nginx-xhttp/templates/public-site/
- ansible/roles/nginx-xhttp/CLAUDE.md
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/templates/config.yaml.j2
- ansible/roles/hysteria/CLAUDE.md
- tests/unit/test_secrets_schema.py
- tests/unit/test_validate_ansible_extra_vars.py
- tests/unit/test_relay_fallback.py
- tests/unit/test_public_site_contract.py
- tests/unit/test_liveness_profiles.py
- NEW: tests/unit/test_xhttp_endpoint_contract.py
- Dependencies: schema. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- Path grammar tightening intentionally rejects previously schema-valid inputs; redistribution and server convergence must be coordinated.
- A port-aware canonical origin affects Atom sitemap structured metadata and the Hysteria masquerade target; split-host deployments need explicit origin ownership.
- Fixing attribution can change policy detector interpretation and log source keys; forged forwarding headers must not become trusted during migration.
- Shared schema renderer and snapshot files require a serialized integration lane across protocol changes.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

Planning only; future implementation requires separate approval. Change the endpoint contract and every call site together without compatibility shims. At rollout review, identify private configurations violating the path/origin contract through categorical validation without printing their values, regenerate supported recipient and liveness artifacts, converge server and proxy together and prove exact authenticated traffic. Preserve fallback logging and nginx transaction guarantees. Existing review tasks and evidence are related references, not reopened work. Fallback export and advanced tuning belong to the dependent feature change.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-XEC-PATH`: NEW test_xhttp_endpoint_contract.py plus existing schema relay and liveness profile tests; include native request completion and parameterized rejected path shapes.
- `REQ-PROTO-XEC-ATTRIBUTION`: NEW native nginx-to-pinned-Xray attribution tests for primary alternate no-header and conflicting-header cases; assert privacy-safe technical source observations.
- `REQ-PROTO-XEC-ORIGIN`: Extend test_validate_ansible_extra_vars.py and test_public_site_contract.py with port-aware native HTTPS discovery and masquerade checks.
- `REQ-PROTO-XEC-PRESERVATION`: Reuse existing nginx transaction and private output regressions; extend endpoint native tests and supported versus official client parser boundaries.

## Validation commands

- `mise exec -- python3 -m pytest tests/unit/test_secrets_schema.py tests/unit/test_validate_ansible_extra_vars.py tests/unit/test_relay_fallback.py tests/unit/test_public_site_contract.py tests/unit/test_liveness_profiles.py`
- `make liveness-profile-check`
- `make snapshot-check`
- `build-gate -- make check`
- `NEW make test-xhttp-endpoint-contract — Run pinned actual nginx/Xray endpoint path origin and attribution integration without real inventory.`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- `SCT-1791617687019287` — `transport-input-semantics`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
