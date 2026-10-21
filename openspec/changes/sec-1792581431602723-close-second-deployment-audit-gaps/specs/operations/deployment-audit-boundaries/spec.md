## Purpose

Keep decrypted secrets off disk after an operator interrupt, keep provider OS
changes from rebuilding a live node, keep verification plays inside the
selected environment, and let several environments share one operator key.

## ADDED Requirements

### Requirement: REQ-DAB-SIGNAL — Clean plaintext after an interrupt

`vpnd deploy` and `vpnd reconverge` MUST run `make clean` after SIGINT,
SIGQUIT, SIGTERM or SIGHUP arrives at any time from the decrypt step until
cleanup ends. They MUST NOT start another pipeline step after the signal, and
they MUST exit with 128 plus the signal number.

#### Scenario: A stop request arrives during a step

- **WHEN** vpnd receives SIGTERM while `make plan` runs
- **THEN** no later step starts
- **AND** `make clean` runs and the decrypted secrets file is absent
- **AND** vpnd exits with 143

#### Scenario: A terminal interrupt reaches the process group

- **WHEN** the terminal sends SIGINT to vpnd and its running Make step
- **THEN** `make clean` runs and vpnd exits with 130

### Requirement: REQ-DAB-OSIMAGE — Refuse an in-place OS change

The Vultr root MUST refuse a plan whose `os_id` differs from the `os_id` of
the existing node, and MUST NOT plan an in-place update of `os_id`.

#### Scenario: The operator edits os_id for an existing node

- **WHEN** a node exists with `os_id` 2625 and the tfvars set 2284
- **THEN** `make plan` fails before any change to the node

### Requirement: REQ-DAB-PLAYENV — Bind verification plays to ENV

`smoke-test.yml`, `verify.yml` and `security-verify.yml` MUST refuse, before
any other task, a selected host whose inventory `env` is not `ENV`, and MUST
refuse an empty `ENV`. Tag selection MUST NOT skip this check.

#### Scenario: The inventory holds two environments

- **WHEN** the operator runs `make smoke-test ENV=staging` and the inventory
  also holds a `prod` host
- **THEN** the play fails for the `prod` host before it writes any client
  credential

### Requirement: REQ-DAB-SHAREDKEY — Reuse one operator key per project

The Hetzner root MUST accept the name of an existing project SSH key and MUST
NOT create a key when that name is set. It MUST refuse a named key whose public
key differs from `admin_ssh_public_key`. A change of the admin public key MUST
still require a node replacement.

#### Scenario: A green environment reuses the blue key

- **WHEN** `admin_ssh_key_name` names the key that the blue environment created
- **THEN** the green plan creates no `hcloud_ssh_key`
- **AND** the green server uses the named key

#### Scenario: Existing state keeps its key

- **WHEN** an existing environment plans without `admin_ssh_key_name`
- **THEN** the key moves to its indexed address with no change
