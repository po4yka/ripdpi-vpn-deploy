## Context

The owner revised acceptance on 2026-10-15: all implementation and validation
must run without external infrastructure. Local Docker supplies Linux root,
systemd, TUN and network namespaces on the workstation. Upstream source/package
retrieval is allowed; no external runtime or application endpoint is involved.

## Goals / Non-Goals

- Goal: build and exercise the real upgraded sources against the exact retained
  source pair, including warm daemon adoption and failure compensation locally.
- Non-goals: change production defaults, claim stable upstream eligibility,
  physical Android compatibility, provider acceptance or a 48-hour staging soak.
  These are excluded from this task rather than relabelled as local successes.

## Decisions

- The versioned candidate contract binds both exact tags and commits, the exact
  Go toolchain and both supported Linux archive checksums. A moved tag or dirty
  module graph fails the build. `GOTOOLCHAIN=local`, readonly modules and two-job
  limits prevent hidden toolchain upgrades and unbounded compilation.
- Fetch public source Git objects on the workstation through standard GitHub
  SSH port 22, verify the exact tag commit, and cache immutable Git bundles under
  `.cache/awg-source-candidate/`. Only these public objects enter the build;
  neither the SSH agent nor credentials are mounted or copied into Docker.
  The build verifies each checked-out commit again before compiling.
- Go v3.1.20260828 resolves to b5928efb6ca19f0153958460c3d141f04abc5c2e.
  Its release API returned 404 at review; publication/channel eligibility is
  unknown. Tools v3.1.20260812 resolves to
  ee0f0a9aa34ff0a0da4b3433b9512781cfe02843 and its non-draft, non-prerelease
  release was published on 2026-08-12. The contract explicitly denies production
  eligibility; deployment examples remain on the reviewed baseline.
- The runner admits only a local Unix-socket Docker context and its engine
  BuildKit driver, binds subsequent calls to that context/builder, builds a bounded
  explicit context containing public source files, and starts a uniquely allocated
  container without network access, host workspace mounts or published ports.
  The systemd cgroup mount belongs to the local Linux VM. Only the owned
  container identity is removed, including its preallocated unique name when
  startup fails before returning an ID.
- A checksum-pinned Ubuntu image supplies package dependencies. Build both real
  source pairs with repository-pinned Go 1.27.1. The contract explicitly selects
  the reachable module cache; original `go.sum`, readonly modules and the standard
  signed checksum database remain enabled. This changes artifact delivery, not
  the reviewed dependency versions or their byte authentication.
- Test candidate/server versus baseline/client, baseline/server versus
  candidate/client, and candidate/candidate with two existing scalar-header wire
  shapes. Each proves authenticated bidirectional sustained TCP/UDP and DNS,
  three reconnects, and captured handshake/transport header bytes and offsets.
- Use the existing durable source publisher to atomically publish the complete
  Go/tools/quick pair in the lab. Real systemd daemons adopt pin-only changes;
  unit-only changes adopt the sandbox. Build failure retains the receipt and
  ready traffic. Readiness rejection restores the complete baseline pair and
  both owned daemons. Unchanged publication preserves PIDs and an independent
  third tunnel retains its process and traffic throughout.
- This proves a local candidate upgrade procedure. It does not claim that the
  production role has acquired a new automatic data-plane readiness transaction.
- S3/S4 remain zero; RandomTrailers, DisableCookies and new modes stay absent.
  The physical safe-floor policy and cross-repository fingerprints are unchanged.

## Contracts and ownership

- `contract/awg-source-candidate.json`: source and toolchain selection.
- `scripts/test-awg-source-candidate.py`: local-only orchestration and cleanup.
- `tests/integration/awg_source_candidate/`: real builds and isolated traffic.
- `Makefile`, script/test guidance, test docs and this change's task metadata.
- One serialized writer; no parallel ownership lanes are needed.
- The already integrated source publisher is a dependency. Device binding and
  four-protocol acceptance remain related work, not prerequisites for this
  independent local two-version lab. Their task states are not modified.

## Risks / Trade-offs

- Privileged containers are required for TUN, namespaces and service sandboxing;
  the local Docker VM is the isolation boundary, not a production host.
- Distribution package versions follow the pinned image's signed repositories;
  AWG source/module inputs and the compiler are pinned independently.
- Local Linux arm64 cannot establish Android's embedded-core or physical path
  behavior. Existing physical S3/S4 guards remain fail-closed.
- Unknown upstream release eligibility and advisory reachability cannot be
  converted into a production approval by this lab.

## Migration Plan

Run `build-gate -- make test-awg-source-candidate` locally. No private migration
or deployment is needed. Remove only the owned lab container on every outcome;
its image remains reusable in the Docker build cache. Review candidate source
changes through this PR. Promoting production pins is separate work requiring
resolved upstream eligibility and its own explicit scope.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_awg_source_candidate.py tests/unit/test_amneziawg_source_pins.py tests/unit/test_amneziawg_version_floor.py`
- `build-gate -- make test-awg-source-candidate`
- `make snapshot-check`
- `build-gate -- make check`
