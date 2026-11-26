# operations/concurrent-node-previews Specification

## Purpose
Let previews of different nodes run at the same time from one worktree, allow one controller operation per node on the operator machine, and keep deploys one at a time.

## Requirements

### Requirement: REQ-CNP-LOCK — One operation per node on the operator machine

The deploy controller MUST take an exclusive non-blocking lock for each selected inventory alias in the operator state directory before its first readiness probe in `dry-run` and `deploy`, and MUST hold it until the run exits. A run that cannot take the lock MUST refuse with `node-operation-in-progress` before any SSH operation or decrypted-secrets copy.

#### Scenario: Preview during a deploy of the same node

- **WHEN** a `deploy` of alias A runs and an operator starts `make dry-run ANSIBLE_LIMIT='A'` from any checkout
- **THEN** the preview refuses with `node-operation-in-progress` and contacts no host.

#### Scenario: Lock release after failure

- **WHEN** a preview of alias A fails, is cancelled or loses its management route
- **THEN** a new preview of alias A can take the lock.

### Requirement: REQ-CNP-SERIAL — Deploys stay one at a time

`deploy` MUST also take one exclusive non-blocking fleet deploy lock and MUST refuse with `deploy-in-progress` when another deploy holds it. `dry-run` MUST NOT take the fleet deploy lock. `site.yml` MUST keep `serial: 1`, and the node's `transaction.lock` MUST stay unchanged.

#### Scenario: Two deploys of different nodes

- **WHEN** a deploy of alias A runs and a deploy of alias B starts
- **THEN** the deploy of B refuses with `deploy-in-progress`.

#### Scenario: Preview beside a deploy

- **WHEN** a deploy of alias A runs and a preview of alias B starts
- **THEN** the preview of B runs.

### Requirement: REQ-CNP-ISOLATION — Concurrent previews share no written local state

Concurrent previews from one checkout MUST each use their own decrypted secrets path and an explicit inventory path that no preview writes. The controller's run directory, SSH control socket directory and Ansible home MUST stay private to each run.

#### Scenario: Two previews from one worktree

- **WHEN** previews of aliases A and B run at the same time from one clean worktree with distinct `SECRETS_FILE` paths and explicit `ANSIBLE_INVENTORY` paths
- **THEN** each preview reads only its own inputs, and the `make clean` of one leaves the other's secrets path in place.
