## Context

Image CI already enumerates pinned Molecule and observer images. Trivy is
SHA-pinned. The explicit host audit already retains private command reports.
See proposal.md for the scope and the notification channel selected by the owner.

## Goals / Non-Goals

- Goal: detect advisories each day and notify on changed results or scan failure.
- Goal: add a read-only systemd isolation report to the explicit audit.
- Non-goal: deploy, send a test issue, change credentials, Cloudflare or SSH.

## Decisions

- Reuse Trivy for repository filesystem scanning, with only its vulnerability
  scanner and development dependencies enabled. Include all severities and
  unfixed dependency findings. Keep the existing image policy unchanged.
- Reuse image-scan.yml and expose its exact matrix. An opt-in report-artifact
  input retains each matrix report independently for the daily caller.
- Aggregate expected SARIF reports and upstream job results. Fingerprint sorted
  finding identities, not timestamps or run URLs. Missing or invalid reports
  remain failures. Serialize daily runs to avoid duplicate issue creation.
- Use an owner-assigned bot issue and comments for new or changed problems,
  with closure after complete recovery. GitHub account settings control email.
  Only summary counts and run links enter issue content; no SMTP secret is needed.
  Only default-branch runs may update the shared issue; manual feature-branch
  runs retain reports without replacing the accepted branch's notification state.
- Bind artifacts to the GitHub run attempt. Partial retries cannot reuse old
  clean reports; a full retry creates a fresh artifact set without overwriting
  prior evidence. Compare the run SHA with the current default-branch SHA before
  any issue write, so historical reruns cannot clear a newer warning.
- Add systemd-analyze collection to the existing audit task file. Retain its
  diagnostics at 0640 and skip both execution and report publication in check
  mode. An exposure score is configuration evidence, not a vulnerability verdict.

## Contracts and ownership

- Own .github/workflows/daily-security.yml, image-scan.yml,
  scripts/notify-security-scan.cjs, their tests, audit-role tasks and notes,
  .github/SECURITY.md and docs/reference/testing.md.
- Terraform, vpnd, secrets, public listeners and deployment contracts are unchanged.
- The implementation stays in its dedicated worktree; shared files have one writer.

## Risks / Trade-offs

- Registry, advisory or artifact failure can prevent a scan: notify and retain a
  failed run rather than accepting incomplete clean output.
- Email depends on owner account settings: document GitHub notification setup.
- Broad dependency scanning can find existing advisories: report them without
  suppressing findings or expanding this change into dependency updates.
- Host reports contain unit names: keep the existing private report boundary.

## Migration Plan

After integration, the workflow runs at 06:17 UTC each day and supports manual
dispatch. Existing image CI callers retain their current behavior. The new host
report appears on the next explicitly authorized security audit. Reverting this
source change removes both additions without changing host service configuration.
Validate focused workflow/notification and Ansible tests, static workflow checks,
the complete local `make check` gate and an independent source review. Record
hosted execution and actual notification delivery as unverified, not as local proof.
