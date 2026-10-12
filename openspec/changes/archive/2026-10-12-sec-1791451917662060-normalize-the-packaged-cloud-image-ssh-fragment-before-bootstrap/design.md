## Context

The observed fresh Ubuntu image has a root-owned mode-0644 image fragment with
exact bytes `PasswordAuthentication no\n`. Existing bootstrap rejects membership
before writes, leaving cloud-init incomplete and effective root SSH enabled.

## Goals / Non-Goals

- Goal: complete canonical first-boot SSH ownership on this supported image.
- Non-goal: admit arbitrary vendor directives or change runtime ownership.

## Decisions

- Add one bounded input owner, validate exact bytes/mode before any writes, then
  remove its redundant directive in the existing rollback transaction.
- Include its temporary restore names in the existing bounded residue grammar.
  A crash after removal can repeat from the canonical layout.
- Keep effective-policy validation, root ownership, symlink and hardlink refusal,
  file/output bounds, fsync and directory-descriptor operations unchanged.

## Contracts and ownership

- Cloud-init helper, its unit tests and nearest folder notes are owned here.
- Every Terraform root embeds the same helper. No provider resources, Ansible
  roles, CLI flags or secret schemas change.
- One serialized writer; no delegated or concurrent edits.

## Risks / Trade-offs

- Deleting an unrecognized owner would hide policy: exact name, bytes and mode
  are required before any mutation.
- Failure after deletion could lose the input: the existing snapshot/rollback
  path restores it, including metadata; interruption is tested separately.

## Migration Plan

Run focused unit coverage and the full required local gate, commit and obtain
hosted validation before live use. Create a clean replacement from this validated
source and observe its actual first boot; do not regenerate host keys or
synthesize the completion marker.
The attempted final-stage retry on the failed candidate was not acceptance:
this image retained the per-instance scripts-user semaphore and skipped the
script. Retire that failed candidate after the clean replacement is ready.
Observe strict SSH policy, marker and readiness before continuing deployment.
Ordinary helper failures restore original files. The original working fleet
remains available.
