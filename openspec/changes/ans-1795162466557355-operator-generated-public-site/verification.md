---
task_id: ANS-1795162466557355
change: ans-1795162466557355-operator-generated-public-site
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: not_applicable
client_evidence: "No client, bundle or transport contract changes."
artifact: not_applicable
artifact_evidence: "No release artifact."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SITE-IDENTITY | ANS-1795162712291937 | `test_new_writes_one_identity_and_never_replaces_it`, `test_new_refuses_an_unsafe_origin_without_writing`, `test_an_unset_directory_is_refused_instead_of_the_working_directory` | passed locally |
| REQ-SITE-BUILD | ANS-1795162712291937 | `test_build_is_reproducible`, `test_build_refuses_a_link_in_its_inputs_and_writes_nothing`, `test_build_refuses_a_canonical_url_on_another_host`, `test_build_refuses_an_unsafe_identity_and_writes_nothing`, `test_archive_holds_each_generation_as_a_delta_dated_by_the_schedule` | passed locally |
| REQ-SITE-SCHEDULE | ANS-1795162712291937 | `test_schedule_starts_on_the_start_date_and_keeps_every_interval_near_the_cadence` (pinned times), `test_each_generation_adds_one_article_with_a_later_date` | passed locally |
| REQ-SITE-UNIQUE | ANS-1795162712291937 | `test_independent_content_is_admitted` (measured share 0.0), `test_bundled_pages_under_another_origin_are_refused`, `test_bundled_pages_with_one_paragraph_replaced_are_still_refused` (measured share above 0.7), `test_check_names_each_refused_file`, `test_a_peer_bundle_with_the_same_content_is_refused`, `test_check_refuses_to_run_without_its_reference_or_origin`; `test_production_preflight_refuses_a_bundle_that_copies_the_bundled_site` (deploy and dry run), `test_preflight_leaves_a_non_production_host_and_a_static_bundle_alone`; `test_check_refuses_the_bundled_live_sources_and_markup_and_a_peer_with_the_same_markup` | controller check, production preflight and the live source clause passed locally |
| REQ-SITE-PUBLISH | ANS-1795162729645051 | `tests/unit/test_public_site_publisher.py`: scheduled generation and advance, file times from the schedule, recreated node, repeated run, refused schedule, interrupted-run leftovers; Molecule `public-site` in CI; `test_every_server_of_a_published_bundle_reads_its_served_generation` | publisher and vhost root passed locally; Molecule not run locally (amd64-only image on an arm64 host); the 404 for an unpublished path against a real nginx pending in CI Molecule and staging |
| REQ-SITE-ISOLATION | ANS-1795162729645051 | `test_publisher_unit_has_no_network_or_privilege_and_writes_only_its_state`, `test_an_unexpected_archive_member_refuses_that_bundle_and_the_next_one_is_still_published`, `test_an_archive_that_does_not_match_its_directory_name_is_refused` | passed locally; `systemd-analyze` and the sandboxed run pending in CI Molecule and staging |
| REQ-SITE-ROLLBACK | ANS-1795162729645051 | role keeps every digest and exports `_public_site_remove_after_commit`; Molecule verify runs `retire.yml` and `absent.yml` as a caller does; `test_site_closes_complete_protected_block_before_unrelated_roles` pins removal after the commit; the transaction harness runs the real block with the role | playbook order passed locally; forced activation failure on staging pending |
| REQ-SITE-LIVE | ANS-1795162761685232 | `test_a_site_document_supplies_its_own_page_sources_and_markup`, `test_a_site_document_the_build_would_refuse_keeps_the_previous_page`, `test_build_carries_the_live_page_declaration_with_its_own_sources_and_markup`, `test_build_refuses_an_unsafe_live_page_declaration`, `test_a_declared_live_page_is_served_from_its_own_directory_with_the_generation_as_fallback`, `test_live_refresh_unit_has_the_network_but_cannot_write_the_publisher_state`; Molecule `public-site` in CI | passed locally; unit instances, permissions and the nginx location against a real host pending in CI Molecule and staging |
| REQ-SITE-RUNWAY | ANS-1795162712291937 | `test_status_counts_unpublished_generations_and_days_left`, `test_make_targets_build_and_admit_a_bundle_and_the_render_target_is_gone`; `test_preflight_admits_independent_content_and_warns_about_a_short_runway` (dry run names bundle and origin) | passed locally |
| REQ-SITE-LAYOUT | ANS-1795162748588038 | old-layout refusal case in `tests/unit/test_public_site_contract.py`; absent Make target; `test_a_tree_without_the_bundle_layout_refuses`, `test_a_self_steal_tree_without_the_bundle_layout_refuses`, `test_rejects_unsafe_public_site_tree`, `test_make_targets_build_and_admit_a_bundle_and_the_render_target_is_gone` | passed locally |
