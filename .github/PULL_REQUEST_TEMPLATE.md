## Task contract

- Task ID: <!-- AREA-16-digit-ID -->
- Task record: <!-- docs/tasks/issues/<slug>.md -->
- OpenSpec change: <!-- change name, or N/A -->
- Spec-not-required reason: <!-- allowed reason, or N/A -->
- Cross-repository references: <!-- qualified project#TASK-ID values, or N/A -->

## Summary

<!-- What observable outcome does this PR deliver and why? -->

## Scope

- [ ] Terraform
- [ ] Ansible
- [ ] `vpnd` or scripts
- [ ] Documentation
- [ ] CI / GitHub automation
- [ ] Other: <!-- describe -->

## Evidence

<!-- Exact commands and the observed local, remote CI, dry-run, staging, live, client, and artifact evidence that apply. -->

## Checklist

- [ ] `make task-check` passes
- [ ] `make check` passes, or unavailable gates and their reason are recorded above
- [ ] No task or execution step is marked complete without observed evidence
- [ ] No secret, decrypted value, address feed, state, credential, or host inventory is exposed
- [ ] Changes to runtime policy remain disabled by default unless separately approved
- [ ] mdtask PolyForm Shield internal-tool use is owner/legal-approved if `tools/tasking` changes
