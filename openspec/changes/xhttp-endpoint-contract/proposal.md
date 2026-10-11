# Change: Align XHTTP endpoint paths forwarded attribution and served origins

Task ID: `XRY-1791617955392712`

## Why

The XHTTP backend treats an IP address as a trusted forwarded-header name, nginx and Xray disagree on schema-valid trailing-slash paths, and the public canonical origin excludes nginx's nondefault served port. These contracts cross server, proxy, validation, recipient output, liveness and Hysteria masquerade. Existing transactional nginx and fallback-log repairs are already implemented and must remain preserved.

Audit coverage: A11, A13, A15; planning baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` on 2026-10-10.

## What Changes

- Define one strict XHTTP path grammar and apply it to schema validators, nginx, server, recipient export and liveness rendering.
- Define the exact pinned-runtime forwarded source header contract and sanitize client-supplied authority at nginx before backend attribution.
- Represent canonical HTTPS origin with effective host and optional nondefault served port across discovery metadata, extra-vars and Hysteria masquerade.
- Add positive exact server/client requests and path origin header rejection tests without expanding the default CDN or public management surface.

## Capabilities

### New Capabilities

- `transports/xhttp-endpoint-contract`: align xhttp endpoint paths forwarded attribution and served origins.

### Modified Capabilities

- None.

## Impact

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
- Planning only: no implementation, private-input mutation, provider action or deployment is authorized by these artifacts.
- Dependency and prerequisite ownership is recorded in the portfolio and design; source-fixed predecessor evidence stays intact.
