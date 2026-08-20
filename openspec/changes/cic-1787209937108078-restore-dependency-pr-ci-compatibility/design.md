## Context

The current peer portfolio deliberately removed its task configuration, while
this repository's workflow still checks it out unconditionally. The Debian 13
Molecule image is third-party and immutable, but its OS packages are older
than currently available security fixes; a vulnerability allow-list would
hide those fixes instead of applying them.

## Goals / Non-Goals

- Goal: make required pull-request gates evaluate current, owned inputs and
  fail closed for an unsafe Molecule image.
- Goal: retain immutable image identity for every Molecule scenario.
- Non-goal: alter Terraform, Ansible role runtime behavior, live nodes, or
  waive a vulnerability finding.
- Non-goal: restore configuration that the peer repository intentionally
  retired.

## Decisions

- Remove the peer checkout and federation invocation from this repository's
  task-contract job. The job keeps local base-history validation; the peer is
  no longer a compatible participant, so retaining it would be a false gate.
- Replace the third-party Debian 13 Molecule image with a repository-owned
  image built from a pinned upstream base and updated at build time. CI scans
  the result before publishing or using it, and scenarios reference only its
  published digest.
- Do not use `.trivyignore` for fixed vulnerabilities. A scan failure blocks
  the image refresh until the image recipe installs the available fixes.

## Contracts and ownership

- `.github/workflows/ci.yml` owns local task-contract validation.
- A new image recipe and image publish workflow own the test-container supply
  chain. `ansible/**/molecule.yml` owns references to the published digest.
- `tests/unit/test_molecule_image_pins.py` asserts the approved immutable
  image identifiers.
- Terraform, cloud-init, runtime Ansible roles, SOPS configuration, and vpnd
  have no changed contracts.

## Risks / Trade-offs

- Publishing a repository-owned image adds a CI supply-chain asset; pinning
  the base and scanning the built digest controls that risk.
- A peer may adopt a future compatible federation protocol. Reintroducing it
  requires a separate contract change and both projects' validation.
- Docker is unavailable locally in this checkout; hosted image build and
  scan are required evidence before changing Molecule image references.

## Migration Plan

1. Remove the obsolete federation peer path and validate local task history.
2. Add the pinned image recipe and CI publish/scan path; publish a clean
   Debian 13 image digest.
3. Replace all Debian 13 Molecule references and their pin test with that
   digest, then run required CI.
4. Merge the CI repair, rerun both Dependabot PRs, and merge them only after
   required checks succeed.

Rollback: restore the previous Molecule digest only if its scan is clean at
rollback time; otherwise retain the last known clean owned digest. Reverting
the retired federation check requires a compatible peer contract first.
