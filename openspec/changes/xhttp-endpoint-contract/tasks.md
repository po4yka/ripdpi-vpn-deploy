# XRY-1791617955392712: Align XHTTP endpoint paths forwarded attribution and served origins

## Objective

Align XHTTP endpoint paths forwarded attribution and served origins. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

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
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] XRY-1791617961367849 Define strict path and port-aware origin inputs and update all validators renderers and profile exporters with boundary tests #bug !high @item:XRY-1791617955392712
- [ ] XRY-1791617962188506 Correct direct frontend source attribution and prove actual peer identity under supplied header conflicts #bug !high @item:XRY-1791617955392712
- [ ] XRY-1791617963780756 Exercise exact supported client requests discovery masquerade and failed endpoint rollback across served ports #bug !high @item:XRY-1791617955392712
- [ ] XRY-1791617971846326 Review serialized snapshots run contract and full gates and document the breaking input redistribution boundary #bug !high @item:XRY-1791617955392712

## Verification

- `mise exec -- python3 -m pytest tests/unit/test_secrets_schema.py tests/unit/test_validate_ansible_extra_vars.py tests/unit/test_relay_fallback.py tests/unit/test_public_site_contract.py tests/unit/test_liveness_profiles.py`
- `make liveness-profile-check`
- `make snapshot-check`
- `build-gate -- make check`
- `NEW make test-xhttp-endpoint-contract — Run pinned actual nginx/Xray endpoint path origin and attribution integration without real inventory.`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
