---
name: ansible-role
description: Implement or change VPN Ansible roles with repository toggle, profile, secrets, template and Molecule contracts. Use for role code and tests; running a live deployment uses vpn-deploy, read-only role audits stay read-only.
---

# Implement an Ansible role

Deliver the requested runtime behavior with its integration and local evidence. An inspection or planning request permits analysis; an implementation request permits the scoped code and local validation, while live hosts, provider access and credential changes retain their own authority boundary.

## Establish the contract

1. Run root workspace discovery, inspect relevant existing changes, and read [Ansible design and the new-role recipe](../../../ansible/CLAUDE.md), the target role's `CLAUDE.md` when present, defaults/tasks/handlers, its `site.yml` callers and tests. Preserve the role's ownership boundaries and nearby patterns.
2. Resolve the portfolio task and validated OpenSpec through `repo-task-board`, `sdd` and the appropriate proposal/apply workflow. Runtime features, infrastructure, schema or security/network behavior require OpenSpec. Existing implementation authority carries through missing planning preparation into apply once validated; a planning-only request stops before source changes.
3. Define observable behavior, check-mode behavior, idempotency and relevant failure boundaries. Update every affected caller/contract rather than adding compatibility paths. Terraform owns provider state; cloud-init owns first-boot basics; Ansible owns runtime; SOPS owns secrets.

## Implement the role and integration

- For a new role, follow the canonical recipe in `ansible/CLAUDE.md`: role defaults/tasks/meta/needed handlers, explicit enable toggle, tier and toggle map, ordered guarded site integration, justified test coverage, role notes and instruction alias, plus operator docs and governed counts as needed. Use the existing task's ownership lanes for shared files.
- Use `ansible_facts[...]`, explicit role ordering and real idempotency. Keep prerequisite guards under `always` tags. Listener changes must agree with the shared listener manifest and Terraform's provider contract; SSH/firewall changes retain recovery and promotion gates.
- For runtime downloads/activation or source builds, read [shared runtime release](../../../ansible/roles/runtime-release/CLAUDE.md) and reuse its pinned release/receipt transaction. Consumers own trusted build descriptors, not duplicate activation/recovery machinery. Fresh check mode predicts changes without asserting downloaded-byte proof.
- When secret structure or usage changes, update `secrets/schema.json`, its validation/coverage and non-secret example plus all consumers. Preserve `no_log` where secret-bearing values flow, explicit private file modes and per-device identities. Credential issuance/decryption is not needed to validate a source change locally.
- For systemd templates/install/restart tasks, use `systemd`; for shell templates, use `bash-scripting`; for a security-relevant diff, use `security-review`. Update the target role's `CLAUDE.md` with behavioral decisions and pitfalls in the same change.
- For monitoring roles, read [the current contract](../../../docs/OBSERVABILITY-OPERATIONS.md#current-contract-and-task-history) before older role/task material. Maintain co-hosted resource admission, private component boundaries and independent Kuma; honor current environment limits and rollout hold.

## Validate and hand off

1. Run focused tests for the changed failure/boundary behavior, then `make molecule-test ROLE=<name>` where the role has a scenario. Require its convergence, idempotency and verification outcomes; a documented unsupported environment is a gap, not a passing run. Use the pinned `mise` environment and machine-wide build gate where root instructions require it.
2. For changed templates, review the rendered output before `make snapshot-update`, then run `make snapshot-check`. Refresh only intended snapshots. Run relevant secrets/profile/listener checks when those contracts changed and use [the test map](../../../docs/TESTING.md) to select remaining coverage.
3. Run required `make check` for changes crossing layers, schemas, secret handling or shared scripts. Review the final diff for complete call sites and unintended changes, then follow the task's verification/commit workflow with exact owned paths. Live deployment and acceptance remain separate when not requested.

Report implemented behavior, affected roles/contracts, exact local commands/results and any unverified runtime or environment claim. Successful Molecule, snapshots or check mode do not prove live host identity, external client traffic or production readiness.

For a planning-only assessment, report the proposed toggle/site integration, secret/listener impact (or why unaffected), check-mode/idempotency choices and exact local validation plan, without writing implementation files.
