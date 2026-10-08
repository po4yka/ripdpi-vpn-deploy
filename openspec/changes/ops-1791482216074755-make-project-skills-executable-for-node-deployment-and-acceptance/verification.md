---
task_id: OPS-1791482216074755
change: ops-1791482216074755-make-project-skills-executable-for-node-deployment-and-acceptance
commit_sha: null
local: required
local_evidence: Targeted preparer, instruction and promotion tests passed (92 tests); full build-gate make check pending.
remote_ci: required
remote_ci_evidence: null
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
| REQ-INTENT-LOCAL | OPS-1791482495146337 | 25 preparer tests, real Make positive publication and existing validator | passed |
| REQ-INTENT-PRIVATE | OPS-1791482495146337 | Private modes, nonempty refusal, substitution and retained-partial tests; security review approved | passed |
| REQ-INTENT-MAKE-BOUNDARY | OPS-1791482495146337 | Real Make environment/assignment expression and mixed-goal refusal tests | passed |

## Independent review and limits

Standards/spec review approved the skills, routing, packaging and hash registration.
Security review first found a mkdir/open directory substitution race and a misplaced
test assertion. Publication now opens an existing empty private directory without
creating/chmod-ing it, and checks its binding around each exclusive file write;
both findings were repaired and the repeated review approved the result.

Initial offline decision evaluation covered nine requests, with two responses
incomplete in their bootstrap handoff/role integration detail. Instructions and
the explicit data-plane preparation scenario were clarified; a separate cold
evaluation then covered both. These observations validate proposed decisions,
not actual live execution, automatic-selection rates or future model reliability.
Generic skill validation passes the five new entrypoints. Its older frontmatter
validator rejects the existing OpenSpec compatibility field; repository portable
frontmatter checks remain authoritative and the metadata is retained.
