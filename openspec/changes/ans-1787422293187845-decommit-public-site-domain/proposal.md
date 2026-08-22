# Change: Decommit the production decoy domain from group_vars

Task ID: `ANS-1787422293187845`

## Why

`ansible/group_vars/vpn-p1-web.yml` and `ansible/group_vars/vpn-p2-udp.yml`
hard-code the production decoy identity
(`public_site_canonical_url: "https://<registered-domain>"`). Git history
therefore permanently links this repository — cloneable by anyone with access
— to a specific registered domain, its certificate timeline, and the REALITY
promotion gates described in committed research notes. The repository's own
contract test (`tests/unit/test_public_site_contract.py`) asserts that this
domain must never appear in rendered artifacts, and the audit flagged the
contradiction. Rotating the decoy identity currently requires editing
committed files, so every rotation burns another commit into history.

## What Changes

- Both cohort profiles carry the neutral placeholder
  (`https://vpn.example.com`, matching `group_vars/all.yml`) instead of a
  registered domain.
- The operator supplies the real decoy origin at deploy time through the
  existing `ANSIBLE_EXTRA_VARS_FILE` mechanism; the extra-vars validator
  allowlists `public_site_canonical_url` with strict https-origin validation.
- The converge-time assert in `nginx-xhttp` (canonical URL must equal
  `https://<nginx_xhttp.server_name>`) remains the fail-closed backstop: a
  deploy that forgets the override fails before any listener changes.
- A contract test pins that committed group_vars profiles only ever carry the
  neutral placeholder.
- No rendered artifact, template, role default, or secrets schema key
  changes.

## Capabilities

### New Capabilities

- `ansible/deploy-profile-overrides`: Contract for which variables may be
  overridden at deploy time outside git, and how the decoy site identity is
  supplied without entering version control.

### Modified Capabilities

- None

## Impact

- `ansible/group_vars/vpn-p1-web.yml`, `ansible/group_vars/vpn-p2-udp.yml`
  (runtime defaults for deployed nodes).
- `scripts/validate-ansible-extra-vars.py` (operator override surface).
- `docs/DEPLOY-PROFILES.md` (operator instructions).
- Operator workflow: production deploys on the p1-web / p2-udp profiles now
  require an `ANSIBLE_EXTRA_VARS_FILE` carrying the real decoy origin; lab
  deploys keep converging unchanged because the placeholder matches the
  hysteria masquerade default.
