# SEC-1787810718115433: Refresh Debian Molecule image security

## Objective

Publish a security-gated Debian 13 Molecule image and move every scenario to its new immutable digest without weakening the vulnerability policy.

## Ownership

Own `images/molecule-debian13/`, `.github/workflows/publish-molecule-debian13.yml`, and Debian 13 image references in `ansible/**/molecule.yml`. This is one serialized image-reference lane because every scenario shares the same digest.

## Execution

- [x] SEC-1787810718115434 Enable cache-free repository-owned Debian 13 image refreshes, record the successfully scanned GHCR digest, and preserve the existing HIGH/CRITICAL Trivy policy. #feature !high @item:SEC-1787810718115433
- [x] SEC-1787810718115435 Repin every Debian 13 Molecule scenario to the successfully scanned immutable digest and verify the obsolete digest has no remaining references. #feature !high @item:SEC-1787810718115433
- [x] SEC-1787810718115436 Validate the image refresh through static workflow checks, the published-image Trivy scan, and hosted Molecule matrix before merging the blocked dependency PRs. #feature !high @item:SEC-1787810718115433

## Verification

Run `make actionlint-check zizmor-check`; verify the publisher reports an immutable digest and a successful Trivy scan; run hosted `image-scan` and affected Molecule checks; confirm `rg` finds no old Debian image digest; and observe the dependency PR gates green without an administrator bypass.
