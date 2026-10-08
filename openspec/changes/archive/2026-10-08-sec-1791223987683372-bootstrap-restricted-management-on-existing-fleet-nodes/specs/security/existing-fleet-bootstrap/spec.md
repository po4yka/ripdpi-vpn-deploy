## Purpose

Enroll existing repository-managed fleet nodes through real restricted public
and Tailnet management paths while preserving their runtime policy and the
operator's bounded authority, rollback and cleanup guarantees.

## ADDED Requirements

### Requirement: REQ-SEC-1791223987683372-001 — Explicit lifecycle classification

Bootstrap SHALL bind an exact Terraform workspace and its canonical build
environment to the selected inventory node. Permanent named workspaces SHALL
be supported. Disposable workspaces SHALL retain exact cleanup-manifest,
identity, deadline and state checks. Missing or contradictory classification
SHALL refuse before guest writes; deprecated requests SHALL not receive a shim.

#### Scenario: Named permanent workspace

- **GIVEN** an exact inventory node emitted from a named workspace with build environment `prod`
- **WHEN** the operator supplies the matching source-bound bootstrap request
- **THEN** lifecycle classification accepts the permanent node without relabeling inventory or state.

#### Scenario: Disposable node disguised as permanent

- **WHEN** workspace, build environment or cleanup authority is contradictory
- **THEN** bootstrap refuses before installation, enrollment or firewall changes.

### Requirement: REQ-SEC-1791223987683372-002 — Bounded console ingress capability

The canonical Make surface SHALL render an exact-node console ingress lease
bound to source revision/digest, independently verified host identity, current
operator sources and an absolute deadline. Execution SHALL preserve shared
systemd runtime directories at their normal traversable permissions, retain
private application files at mode 0600, and change only RAM state and exact-source
SSH ingress. It SHALL preserve existing rules, keys, passwords and configuration.

#### Scenario: Healthy systemd startup

- **WHEN** the rendered artifact is executed in an authorized read-only-root recovery shell
- **THEN** shared systemd directories remain traversable by network services and the guest can return to ordinary init.

#### Scenario: Expiry or identity mismatch

- **WHEN** the capability is expired, targets another host, or encounters unsafe owned paths
- **THEN** it creates no ingress allowance; an armed lease expires independently of its controller.

### Requirement: REQ-SEC-1791223987683372-003 — Reviewed managed-policy conversion

Bootstrap SHALL accept an explicitly reviewed repository-managed firewall
without the current Tailnet fragment only through a source-bound policy
snapshot. It SHALL validate root ownership, safe paths, the file/kernel graph,
complete owned tables/chains and the declared ingress lease. The durable
transaction SHALL convert it to one canonical layout while preserving existing
VPN listeners and unrelated policy. Foreign or unexplained drift SHALL refuse.

#### Scenario: Existing managed policy

- **GIVEN** a reviewed managed firewall and real pinned public SSH/SFTP
- **WHEN** enrollment is armed and applied
- **THEN** exact Tailnet SSH sets and interface-scoped rules are added without removing existing VPN listeners.

#### Scenario: Unowned or changed policy

- **WHEN** policy differs from the reviewed snapshot or contains foreign ownership
- **THEN** bootstrap refuses without flushing or adopting unrelated runtime state.

### Requirement: REQ-SEC-1791223987683372-004 — Autonomous original-policy recovery

Controller loss, timeout, reboot, lost replies or failed proof SHALL restore the
original files, effective firewall and service state and remove only newly
enrolled identity. Recovery SHALL not extend a console lease, assume an SSH
runtime directory, or discard foreign changes. Confirmation SHALL require real
fresh public/Tailnet SSH and SFTP with the original host key and unchanged SSH,
resolver and route policy.

#### Scenario: Controller disappears during conversion

- **WHEN** the controller disappears before confirmation
- **THEN** the guest autonomously restores the reviewed original policy and the public management path.

#### Scenario: Successful existing-node enrollment

- **WHEN** both transports authenticate and all preserved-policy postconditions pass
- **THEN** a durable source-bound handoff permits canonical inventory rendering and ordinary deployment.

### Requirement: REQ-SEC-1791223987683372-005 — Positive capability and separate evidence

The task SHALL remain open until positive enrollment, rollback and cleanup are
proved on protected source with relevant local/native, hosted CI, guarded
staging and existing-node evidence. Refusals, fixtures, console availability,
partial SSH restoration or an installed foundation SHALL not count as full
VPN deployment or acceptance. Paid resources SHALL require concrete authorization.

#### Scenario: A safe refusal is the only observed outcome

- **WHEN** the implementation refuses safely but cannot enroll the supported managed node
- **THEN** the feature remains unfinished and its parent live acceptance remains blocked.
