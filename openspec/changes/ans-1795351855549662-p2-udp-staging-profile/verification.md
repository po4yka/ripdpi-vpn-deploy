---
task_id: ANS-1795351855549662
change: ans-1795351855549662-p2-udp-staging-profile
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Pending a make dry-run of a disposable staging node with COHORTS=p2-udp-staging, recorded under ANS-1795259263103243.
staging: not_applicable
staging_evidence: The profile only enables a staging dry-run; staging convergence of the p2-udp transports is evidence for ANS-1795259263103243.
live: not_applicable
live_evidence: The profile is scoped to disposable staging; production p2-udp nodes keep vpn-p2-udp.
client: not_applicable
client_evidence: No client contract changes.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-P2S-PROFILE | ANS-1795351937363114 | `tests/unit/test_deploy_profile_guard.py::test_live_explicit_profile_surfaces_are_locked`; `tests/unit/test_listener_contract.py::test_p2_udp_listener_surface_serves_its_masquerade_site_over_tcp[vpn-p2-udp-staging.yml]` | Pending |
| REQ-P2S-SECRETS | ANS-1795351937363114 | `tests/unit/test_ci_real_deploy.py::test_disposable_staging_profiles_serve_the_generated_masquerade_origin` for the new profile; `tests/unit/test_public_site_contract.py::test_committed_profiles_carry_only_the_neutral_placeholder_origin` | Pending |
| REQ-P2S-ADMISSION | ANS-1795351937363114 | `python3 scripts/check-deploy-profile.py`; `tests/unit/test_deploy_profile_guard.py` family list | Pending |
| REQ-P2S-SECRETS | ANS-1795351982817826 | `make docs-check` on the profile reference | Pending |
