## Context

The audit found the production decoy domain committed in two cohort profiles,
contradicting the repo's own leak-prevention stance and its public-site
contract test. The domain is already burned by prior exposure; the goal is
that the *next* identity never enters git and rotation becomes a
secrets-plus-local-file operation.

## Goals / Non-Goals

- Goals: neutral placeholder in committed profiles; validated operator
  override path; fail-closed behavior preserved; rotation without git edits.
- Non-Goals: history scrubbing (the old association is already burned;
  rewriting protected main history is out of scope); moving
  `nginx_xhttp.server_name` or cert material (already SOPS-resident);
  changing any rendered artifact.

## Decisions

### D1 — Reuse ANSIBLE_EXTRA_VARS_FILE instead of new plumbing (chosen)

The Makefile already carries a hardened override channel: regular file,
same-owner, mode 0600, non-symlink, key-allowlisted via
`validate-ansible-extra-vars.py`. Adding `public_site_canonical_url` to that
allowlist with https-origin validation is a three-line change versus inventing
a second mechanism.

Rejected: deriving the URL from `nginx_xhttp.server_name` at group_vars scope.
The p2-udp profile enables hysteria without nginx-xhttp, so `nginx_xhttp` is
not defined there; a derivation covering both profiles needs profile-specific
logic for one value — more complexity than the override it replaces.

### D2 — Placeholder equals the all.yml default (chosen)

`https://vpn.example.com` already appears in `group_vars/all.yml` and in the
hysteria masquerade default, so lab profiles keep converging unchanged and
there is exactly one placeholder string to pin in tests.

### D3 — Fail-closed stays in the roles (chosen)

The nginx-xhttp assert (`canonical == https://<server_name>`) and the hysteria
assert (`masquerade_url == canonical`) remain the enforcement point. The unit
contract test pins committed defaults; the role asserts pin live convergence.

## Risks / Trade-offs

- An operator upgrading from the old profiles must start passing the extra-vars
  file on prod deploys or convergence fails with a clear assert message —
  intentional fail-closed friction, documented in DEPLOY-PROFILES.md.
- The validator cannot cross-check the override against secrets'
  `nginx_xhttp.server_name`; the converge-time assert covers that gap.

## Migration Plan

Single commit sequence: validator allowlist entry, group_vars placeholders,
contract test, docs note. Operators rotate by editing their local 0600
extra-vars file and secrets — no repo changes.

## Open Questions

- None.
