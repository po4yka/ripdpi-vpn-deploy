# Automatic vpnd releases

The `release-please` workflow runs on `main` by default. It maintains the
release PR from conventional commits. Merging that PR creates the `vpnd-vX.Y.Z`
tag and GitHub Release. Release PR approval and merge remain operator decisions.

The repository must allow GitHub Actions to create pull requests under
**Settings → Actions → General → Workflow permissions**. Missing permissions
or release-please errors fail the workflow; they are not informational success.
The default token remains read-only, with write permissions scoped to each job.

## Binary handoff

When the root package reports `release_created=true`, a separate job verifies
that `tag_name` resolves to release-please's full commit `sha`, then explicitly
runs `release-vpnd.yml` with that tag as both the dispatch ref and input.
`GITHUB_TOKEN` does not trigger tag-push workflows; `workflow_dispatch` is the
explicit handoff. No personal token or GitHub App is required.

The downstream workflow validates the tag against its own `GITHUB_SHA`, builds
four target binaries, attests them, and attaches the binaries, `SHA256SUMS`, and
the locked Cargo SBOM. Running on the tag keeps checkout, builds, attestations,
and SBOM on the same revision even if `main` has advanced.

Creating or updating a release PR does not dispatch binary publication.
Dispatch errors fail the parent workflow. A successful dispatch means the
build was requested; publication is complete only when `release-vpnd` succeeds.

## Verification and recovery

1. After a conventional commit reaches `main`, check that `release-please`
   succeeds and creates or updates the release PR. Review its version and files.
2. After that PR is merged, check `dispatch vpnd binaries` and find the
   `release-vpnd` run on the created tag and SHA.
3. Check all build, attestation, SBOM and asset-upload jobs before consuming
   the release. The release metadata can exist before binaries are attached.

If the dispatch failed after release creation, recover explicitly with the
existing tag; rerunning release-please might not report it as newly created:

```bash
tag=vpnd-vX.Y.Z
gh workflow run release-vpnd.yml --ref "$tag" -f "tag=$tag"
```

Inspect any existing downstream run before retrying. Never dispatch on `main`
with an older tag input: the downstream revision check rejects that mismatch.
This handoff does not add a CI promotion gate or change asset overwrite policy.

## Pause

Set the repository variable `RELEASE_PLEASE_ENABLED=false` to pause new
release-please runs. Delete the variable or set it to `true` to resume.
Deleting the variable now enables automation. This switch does not cancel
already dispatched builds or disable manual `release-vpnd` recovery.
