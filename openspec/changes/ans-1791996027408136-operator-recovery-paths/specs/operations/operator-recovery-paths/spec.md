## Purpose

Guarantee that operator incident paths cannot wedge or widen: an interrupted protected ingress deploy is compensated by the next deploy through the existing single compensation owner, the credential rotation and rollback verbs act on exactly one named inventory node, and operator runtime rollback states and proves what it moves.

## ADDED Requirements

### Requirement: REQ-OPS-ORP-INGRESS-ADOPT — Adopt an interrupted protected ingress transaction

A deploy that finds an open protected ingress site journal on the target node MUST, before capturing a new transaction, adopt that journal as the protected block's compensation owner, run the existing compensation sequence (quiesce candidate transports, restore the accepted ingress, roll back the egress generation when its outer route is open), and then fail with a categorical, non-secret message instructing the operator to repeat dry-run and deploy. Check mode MUST refuse with the same category and MUST NOT mutate node state. A malformed journal MUST fail closed with the journal retained.

#### Scenario: Deploy after an interrupted protected ingress transaction

- **WHEN** a previous deploy was killed after protected ingress capture and before commit, leaving the site journal on the node
- **THEN** the next deploy restores the accepted ingress files, receipts and nginx service state, rolls back the open egress route, removes the site journal and ends non-zero with the interrupted-transaction category

#### Scenario: Dry-run sees an interrupted transaction

- **WHEN** check mode runs against a node with an open site journal
- **THEN** it refuses with the interrupted-transaction category, does not claim compensation was attempted, and leaves every journal, file and service unchanged

#### Scenario: No interrupted transaction

- **WHEN** no site journal exists on the node
- **THEN** detection creates no state, reports nothing changed, and capture proceeds exactly as before

#### Scenario: Malformed journal

- **WHEN** the site journal exists but fails validation
- **THEN** the deploy fails closed before capture and the journal is retained for manual recovery

### Requirement: REQ-OPS-ORP-PENDING-RECOVER — Recover a pending-only publication journal at capture

When a non-check site capture finds an ordinary publication journal for the shared nginx unit without a site journal, it MUST recover that journal under the unit lock with the same recovery the ordinary publisher uses, before receipt admission, and then capture. Unknown, foreign or unsafe journals MUST still refuse. Check-mode admission MUST continue to refuse on either journal.

#### Scenario: Interrupted ordinary publication before the protected block

- **WHEN** an ordinary nginx publication was interrupted and only its pending journal remains
- **THEN** the next site capture restores the prior files and receipt, removes the pending journal and captures normally

#### Scenario: Foreign pending journal

- **WHEN** the pending journal is not a recognized publication journal for the unit
- **THEN** capture refuses and the journal is retained

### Requirement: REQ-OPS-ORP-EXACT-NODE — Bind operator incident verbs to one inventory alias

`make rotate-credentials`, `make rollback-xray` and `make rollback-config` MUST refuse unless `ANSIBLE_LIMIT` names exactly one inventory alias, and MUST pass it to Ansible as the host limit. Their plays MUST assert, before any task that reads private inputs or mutates the host, that exactly one host is selected and that it equals the limit, and MUST run with `serial: 1` and `any_errors_fatal: true`. Groups, patterns, lists and an absent limit MUST refuse without mutation.

#### Scenario: Missing limit

- **WHEN** an operator runs one of the three verbs without `ANSIBLE_LIMIT` or with a whitespace-only value
- **THEN** Make refuses before Ansible starts

#### Scenario: Group or multi-host limit

- **WHEN** the limit selects a group, a pattern or more than one host
- **THEN** the play refuses with a categorical message and no host is changed

#### Scenario: Exact alias

- **WHEN** the limit names exactly one inventory alias
- **THEN** only that host is targeted

### Requirement: REQ-OPS-ORP-ROTATE-ENV — Rotate credentials only within the selected environment

`make rotate-credentials` MUST require clean source, the deploy pre-checks and the existing inventory before running, and the play MUST refuse when the target host's rendered inventory `env` differs from the operator's `ENV`. The audit record MUST name the rotated node. Operator documentation MUST state that revocation is incomplete until every node of the environment has been rotated.

#### Scenario: Environment mismatch

- **WHEN** the target host's inventory `env` is `staging` and `ENV` is `prod`
- **THEN** rotation refuses before secrets are applied

#### Scenario: Revocation across the environment

- **WHEN** an operator revokes a leaked device credential
- **THEN** the runbook directs one rotation and one verification per node of the environment and states that revocation is incomplete until all are done

### Requirement: REQ-OPS-ORP-RUNTIME-ROLLBACK-SCOPE — Operator runtime rollback moves and proves the frontend runtime

Operator runtime rollback MUST retarget both the `XRAY_RUNTIME_BINARY` environment and `ExecStart` of `xray.service` to the verified previous release, MUST publish only nodes owned by the runtime publisher, and MUST NOT add egress-owned gateway units to its candidate set. Operator documentation MUST state that it moves `xray.service` only and that private gateways keep the pinned release until the pin is changed and deployed.

#### Scenario: Frontend rollback candidate set

- **WHEN** a runtime rollback to a verified retained release is planned
- **THEN** the `xray.service` candidate names the release binary in both fields and the candidate set contains no `ripdpi-transport-*.service` path

#### Scenario: Native rollback adoption

- **WHEN** the native lane rolls back to the previous release
- **THEN** the running `xray.service` main process executes the previous release binary and a following ordinary converge with the newer pin succeeds
