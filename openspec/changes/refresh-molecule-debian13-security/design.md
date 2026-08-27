## Context

The pinned Debian 13 Molecule digest is a previously published result of the owned Dockerfile. The Dockerfile already upgrades Debian packages during each build, but the current immutable result has aged into a fixable severe Trivy finding. `image-scan` blocks pull requests that reference it.

## Goals / Non-Goals

- Goal: publish a freshly upgraded, Trivy-clean Debian 13 Molecule image and repin all consumers to its immutable digest.
- Goal: retain the current severity threshold, `ignore-unfixed` behavior, and digest-only consumption model.
- Non-goal: alter production VM images, Ansible role behavior, Terraform, secrets, or the dependency PR contents.

## Decisions

- Configure the existing `publish-molecule-debian13` workflow to build without cache so every security refresh executes the Dockerfile's package upgrade before its digest is adopted.
- Record the returned digest in all Molecule scenario YAML files in one mechanical update. A mutable tag is rejected because it would make tests non-reproducible.
- Do not add a `.trivyignore` exception or soften the severity threshold; the finding is fixable through a rebuild.

## Contracts and ownership

- Owned paths: `images/molecule-debian13/Dockerfile`, `.github/workflows/publish-molecule-debian13.yml`, and Debian 13 `molecule.yml` image references.
- External effect: publishing a new package digest to GHCR.
- No Terraform roots, Ansible runtime roles, `vpnd` interface, or secrets schema are changed. Molecule test environment selection changes only to the new immutable image.

## Risks / Trade-offs

- A current upstream image can introduce a new severe finding. Mitigation: the publisher's Trivy gate must pass before its digest is adopted.
- A missed scenario reference leaves the old vulnerable image in CI. Mitigation: repository-wide digest search and image scan verify that no previous digest remains.
- The new image can alter test behavior. Mitigation: run the affected Molecule matrix in hosted CI before merging.

## Migration Plan

1. Enable cache-free builds in the existing publisher to trigger a fresh security refresh.
2. Observe successful GHCR publication and Trivy scan; obtain its immutable digest.
3. Repin all Debian 13 Molecule references to that digest in a follow-up commit on the same PR.
4. Run local static validation and hosted required checks, including image scan and Molecule jobs.
5. If the new digest fails tests or scanning, retain the previous source references, diagnose the image, and publish a corrected image; do not use an allow-list exception as rollback.
