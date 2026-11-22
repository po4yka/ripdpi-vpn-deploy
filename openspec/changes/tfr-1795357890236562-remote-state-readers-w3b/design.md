## Context

W3 put every workspace behind a partial `backend "s3" {}` with enforced state and plan encryption (`terraform/providers/*/state.tf`). Its implementation findings list the scripts that still read local state paths as follow-up work. A survey found more consumers than that list: every script that accepts a state file path from the operator or from a manifest (staging cleanup guards, unbound retirement, tailnet bootstrap, tailnet promotion, CI seed cleanup). With enforced encryption, all of them fail even against a local backend, because the file is ciphertext.

## Goals / Non-Goals

**Goals:** one way to read state (pull, in memory, bounded, fail closed); bind digests of the pulled bytes; a working disposable CI deploy without new bucket identities.

**Non-Goals:** CI identities in the bucket (W4); changes to the Terraform roots, the wrapper or the backup and restore scripts; live proof (the next authorized staging run).

## Decisions

- **`scripts/tofu_state.py` is the single reader.** It runs the wrapper in a new session, reads at most 16 MiB, kills the process group on timeout or overflow, discards stderr and returns `None` only for an existing empty workspace. Callers keep the bytes in memory. Rejected: pulling to a private temporary file for the path-based scripts, because it puts plaintext state on disk.
- **Bindings keep the digest and drop the path.** A pulled state is a serialization of the stored state; the same stored state pulls to the same bytes, so the SHA-256 binding still detects a change by another writer. The provider and environment that select the state come from the manifest or request that the binding already carries. File-identity checks (inode, mode, link count) on state are removed; the digest check replaces them.
- **No compatibility for old manifests and configs.** Manifests and controller configs that carry a state path are refused. They are short-lived staging artifacts, and accepting them would keep a second code path.
- **Tailnet promotion pulls through its own trusted binary.** The promotion snapshot already freezes the workspace data directory (backend settings and selected workspace) and runs a digest-pinned OpenTofu. It pulls state with that binary and passes exactly `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `TF_VAR_state_passphrase`; `-state=` is removed because it does not apply to the S3 backend.
- **Disposable CI uses a local backend override.** `ci-real-deploy.py` writes the gitignored `terraform/providers/upcloud/ci_backend_override.tf` (`backend "local" {}`), a backend file `<work>/backend/upcloud.s3.tfbackend` that sets `workspace_dir` inside the private work directory, and a random per-run passphrase. The wrapper and `make init` stay unchanged. Rejected: a CI state identity in the operator bucket, because it needs live IAM and bucket policy changes and overlaps W4, and disposable workspaces would accumulate object versions under Object Lock retention.

## Risks / Trade-offs

- The backend file has the S3 name but local settings. The name is the wrapper's contract; the CI code comments it.
- A pull needs the state identity and passphrase in each script's environment. Scripts with allowlisted environments (recovery runtime, observability cleanup, tailnet promotion) now forward them; others inherit the operator environment.
- Plaintext state passes through process memory and pipes only. The recovery runtime journals command output, so it reads state through the helper, not through its journaled command runner.
