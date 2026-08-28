## Purpose

The deploy path from inventory rendering through converge, verification, rotation, and rollback behaves identically regardless of invocation shape: safety pre_tasks always run, first-boot completion precedes convergence, renderer inputs are validated fail-closed, restore points stay current with rotated state, transient probe resources are reclaimed on failure, and maintenance gates depend only on repo-managed facts.

## ADDED Requirements

### Requirement: REQ-TAGGED-GUARDS — Safety pre_tasks MUST execute under any tag scope

Secrets-presence assertion, tier guards, listener-contract, and collision pre_tasks in site.yml MUST carry the always tag so `--tags` runs cannot skip them.

#### Scenario: tag-scoped converge

- **WHEN** an operator runs site.yml with a single role tag
- **THEN** the secrets assert and both tier guards execute before any role

### Requirement: REQ-BOOTSTRAP-GATED-DEPLOY — Convergence MUST NOT start before bootstrap completes

Deploy and dry-run entry points MUST wait for successful cloud-init completion and the bootstrap marker on every selected canonical inventory host before running Ansible. Selection MUST use one private immutable inventory snapshot: empty means all vpn hosts; exact aliases, canonical cohort groups and comma unions are supported. Unknown or ambiguous names, empty results and complex Ansible patterns MUST fail before SSH. HOSTS and Terraform outputs MUST NOT widen or redirect this selection.

Every local input, key, known-host file and selected transport MUST be validated before the first SSH operation. Approved host/port overrides MUST apply before readiness. The unchanged strict SSH builder's host identity and frozen transport records MUST govern readiness, convergence and the subsequent source-drift check. A changed or dirty source after waiting MUST prevent mutating convergence. Existing prechecks, check/diff behavior, tag guards and best-effort audit ordering MUST remain effective.

Canonical variable loading MUST preserve per-host cohort membership, runtime metadata and Ansible types/templating/precedence before secrets and approved overrides. Ambient Ansible configuration, host/group variable files, plugins, callbacks, collection paths or Git routing MUST NOT alter the selected authority. Protected transport variables MUST NOT redirect controller-local delegated tasks.

Unsupported plugin discovery directories at playbook/role bases, symlinked role paths and playbook-relative shadow roles MUST be rejected before SSH, including during a dirty-source dry-run. Canonical roles and the explicitly configured trusted collection installation remain available.

#### Scenario: apply followed immediately by deploy

- **WHEN** `make apply && make deploy` runs against fresh nodes
- **THEN** converge begins only after each node publishes its bootstrap marker

#### Scenario: bounded cohort deployment with an approved transport override

- **WHEN** a cohort limit and approved address/port override select a subset of a multi-host inventory
- **THEN** readiness and Ansible use the same selected host identities and effective transports, preserve each host's canonical cohort variables, and never contact unselected hosts

#### Scenario: inventory or source changes during readiness

- **WHEN** the original inventory changes after selection or source becomes dirty during a bootstrap wait
- **THEN** the inventory change cannot affect convergence or source-drift targets, and dirty source prevents mutating convergence

#### Scenario: ambient Ansible authority or a local-input failure

- **WHEN** an ambient host_vars/plugin/environment override is present or any selected key/input is invalid
- **THEN** ambient authority is excluded, invalid inputs fail before the first SSH operation, and controller-local delegated guards remain local

### Requirement: REQ-BOUNDED-WAIT — The bootstrap wait MUST be bounded and diagnose error state

The remote cloud-init wait MUST terminate within a fixed bound and MUST distinguish a cloud-init error outcome from a missing marker in its failure output.

#### Scenario: stalled first boot

- **WHEN** cloud-init hangs past the bound
- **THEN** the wait fails with a message identifying the observed cloud-init state instead of hanging

### Requirement: REQ-COHORT-SLUG-VALIDATION — Cohort slugs MUST validate against known profiles at render time

Inventory rendering MUST reject cohort slugs with no matching group_vars profile.

#### Scenario: typo in HOSTS pair

- **WHEN** a HOSTS pair names a cohort that has no group_vars file
- **THEN** rendering fails naming the unknown slug instead of emitting an empty group

### Requirement: REQ-SSH-ALLOWLIST-FAILFAST — An empty SSH allowlist MUST fail before apply

Both Terraform variable validation and the site.yml pre-converge asserts MUST reject an SSH allowlist containing no CIDRs.

#### Scenario: allowlist stripped in tfvars

- **WHEN** plan or converge runs with an empty allowed_ssh_cidrs
- **THEN** the gate fails before any node loses its management-path accept rule

### Requirement: REQ-UNIQUE-HOST-ALIASES — Inventory host aliases MUST be unique across provider pairs

Inventory rendering MUST fail when two HOSTS pairs produce the same alias rather than merging their vars silently.

#### Scenario: shared server_name across roots

- **WHEN** two provider pairs resolve to the same hostname alias
- **THEN** rendering aborts listing the conflicting pairs

### Requirement: REQ-ROTATION-PREV-CONTRACT — Rotation MUST preserve the rollback restore point

Credential rotation MUST snapshot the outgoing xray configuration to the same .prev artifact the rollback playbook consumes before writing the new one.

#### Scenario: rotation followed by config rollback

- **WHEN** rotate-credentials runs and is followed by rollback-config
- **THEN** the restored file is the immediately preceding credential set, not an older generation

### Requirement: REQ-ROLLBACK-VALIDATE-FIRST — Binary rollback MUST validate before repointing runtime

Rollback MUST validate the target release binary against the current configuration before changing the runtime symlink, and MUST refuse a no-op rollback to the pinned version.

#### Scenario: incompatible historical binary

- **WHEN** rollback targets a release whose binary rejects the live config
- **THEN** the play fails before the symlink changes and the running service stays untouched

### Requirement: REQ-SMOKE-CLEANUP — Failed probes MUST reclaim transient resources

Smoke-test protocol blocks MUST stop transient services and remove their workdir on every exit path including failures.

#### Scenario: wait_for timeout mid-smoke

- **WHEN** a smoke-test stage times out
- **THEN** no transient proxy unit remains running and the credential-bearing workdir is removed

### Requirement: REQ-MAINTENANCE-SERVICE-GATE — Maintenance verification MUST depend only on repo-managed services

Post-maintenance service checks MUST NOT hard-fail on units no Ansible role installs or manages.

#### Scenario: fleet host without external management plane

- **WHEN** rolling maintenance reaches a host lacking an externally installed unit
- **THEN** maintenance continues; absence is reported without failing the serial batch

### Requirement: REQ-TOGGLE-DEFAULT-PARITY — Playbook inline toggle defaults MUST match the declared surface

Every inline enable_* default in playbooks MUST equal the corresponding default in group_vars/all.yml, enforced by test.

#### Scenario: new profile omitting a key

- **WHEN** a cohort profile omits an enable key
- **THEN** deploy, verify, smoke, maintenance, and rotation agree on the effective default

### Requirement: REQ-LOCALE-INDEPENDENT-GATE — Output-parsing gates MUST pin locale

Package-backlog assertions MUST parse simulation output generated under a pinned locale.

#### Scenario: non-English host locale

- **WHEN** residual-package simulation runs on a localized host
- **THEN** the gate evaluates package counts, not translated phrases

### Requirement: REQ-DECLARED-TOGGLE-SURFACE — Every consumable feature toggle MUST appear in the declared toggle surface

All vpn.enable_* keys consumed by playbooks or roles MUST have documented defaults in group_vars/all.yml.

#### Scenario: operator enables governance-gated topology

- **WHEN** an operator reads the declared toggle surface to enable cascade legs
- **THEN** the cascade toggles are present with defaults and a governance pointer
