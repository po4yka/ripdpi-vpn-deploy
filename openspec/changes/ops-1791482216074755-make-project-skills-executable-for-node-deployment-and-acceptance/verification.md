---
task_id: OPS-1791482216074755
change: ops-1791482216074755-make-project-skills-executable-for-node-deployment-and-acceptance
commit_sha: 265301c1b0371443176c0b36f676cf73ba15b92e
local: passed
local_evidence: Targeted preparer, instruction and promotion tests passed (97 tests); build-gate make check exited 0 with 5250 Python tests, 22 subtests, 55 Bats tests and 205 Rust release tests passed, plus release clippy, Terraform, lint, schema and snapshots.
remote_ci: passed
remote_ci_evidence: PR 280 source SHA 265301c1b0371443176c0b36f676cf73ba15b92e had 81 terminal latest checks (80 success, Trivy neutral), with no failed or pending checks; CI run 37835940541 and associated checks completed.
dry_run: not_applicable
dry_run_evidence: Local preparation and skill guidance only; no runtime or external capability changed.
staging: not_applicable
staging_evidence: Local preparation and skill guidance only; no runtime or external capability changed.
live: not_applicable
live_evidence: Local preparation and skill guidance only; no runtime or external capability changed.
client: not_applicable
client_evidence: Local preparation and skill guidance only; no runtime or external capability changed.
artifact: passed
artifact_evidence: Five portable skills, conditional OpenSpec references, nine offline scenarios and real local intent/mapping publication validated; no live proof claimed.
---

# Verification

This change adds local preparation and agent guidance, not runtime deployment. Provider dry-run, staging, live and client categories are not required; offline scenario evaluation is not their substitute.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SKILL-LIFECYCLE | OPS-1791482490840434 | Five new skills validated; independent lifecycle decision cases | passed |
| REQ-SKILL-OUTCOMES | OPS-1791482490840434 | Failed XHTTP and interrupted/bound-unbound cleanup decisions | passed |
| REQ-SKILL-HANDOFF | OPS-1791482490840434 | Missing-artifact authorized continuation and read-only role assessment | passed |
| REQ-SKILL-EVALUATION | OPS-1791482498372510 | Nine retained offline scenarios; initial two partial responses refined and cold-retested | passed |
| REQ-INTENT-LOCAL | OPS-1791482495146337 | 30 preparer tests, real Make positive publication and existing validator | passed |
| REQ-INTENT-PRIVATE | OPS-1791482495146337 | Private modes, nonempty refusal, substitution, retained-partial and five configuration/input-alias tests; security review approved | passed |
| REQ-INTENT-MAKE-BOUNDARY | OPS-1791482495146337 | Real Make environment/assignment expression and mixed-goal refusal tests | passed |

## Independent review and limits

Standards/spec review approved the skills, routing, packaging and hash registration.
Security review first found a mkdir/open directory substitution race and a misplaced
test assertion. Publication now opens an existing empty private directory without
creating/chmod-ing it, and checks its binding around each exclusive file write;
both findings were repaired and the repeated review approved the result.
The preparer also refuses a configuration path equal to any credential or
manifest input before opening the configuration. Five regression cases prove
that ordering; the final security review approved this hardening.

The full local gate used an isolated Docker test profile with two CPUs and 2 GiB
memory and retained the Cargo release limit of two jobs. Its owned profile,
Lima instance, disk and Docker context were removed after the successful run;
the original Docker context remained unchanged. The 18 native-runtime tests
excluded by the canonical Python selector are not live acceptance evidence.

Initial offline decision evaluation covered nine requests, with two responses
incomplete in their bootstrap handoff/role integration detail. Instructions and
the explicit data-plane preparation scenario were clarified; a separate cold
evaluation then covered both. These observations validate proposed decisions,
not actual live execution, automatic-selection rates or future model reliability.
Generic skill validation passes the five new entrypoints. Its older frontmatter
validator rejects the existing OpenSpec compatibility field; repository portable
frontmatter checks remain authoritative and the metadata is retained.
