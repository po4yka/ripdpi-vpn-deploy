# Change: Close second deployment audit secrets and lifecycle gaps

Task ID: `SEC-1792581431602723`

## Why

A second pre-deployment audit of `main` at `03033beb` found four defects that
the first audit (`ANS-1792499727513191`, `OPS-1792512787218003`) left open:

- `vpnd deploy` and `vpnd reconverge` reset SIGINT and SIGTERM to the default
  action and do not handle SIGHUP or SIGQUIT. Only the review prompt maps these
  signals to a failure. A Ctrl-C, a lost session or a stop request during
  `init`, `plan`, `apply`, `deploy` or `verify` ends vpnd at once, so
  `make clean` does not run and the decrypted secrets file stays on disk.
- `vultr_instance.vpn` passes `os_id` to the provider, and a changed `os_id`
  is an in-place update that reinstalls the instance. `prevent_destroy` does
  not stop an update. The first audit made the image allowlist refuse Debian 12,
  and its message tells the operator to set a new `os_id`; on an existing node
  that edit wipes the server.
- `smoke-test.yml`, `verify.yml` and `security-verify.yml` select every `vpn`
  host and load one decrypted secrets file, but they do not compare the host
  inventory `env` with `ENV`. `smoke-test.yml` writes client credentials from
  that file onto each selected host, so an inventory with several environments
  copies one environment's credentials onto another environment's hosts.
  `make smoke-test` also skips the inventory check.
- Each Hetzner environment creates its own `hcloud_ssh_key` from
  `admin_ssh_public_key`. Hetzner keeps one key per fingerprint in a project, so
  a blue-green or warm-spare environment with the same operator key cannot
  provision.

## What Changes

- `vpnd deploy` and `vpnd reconverge` record SIGINT, SIGQUIT, SIGTERM and
  SIGHUP from the first plaintext step until cleanup ends. A recorded signal
  stops the pipeline at the next step boundary, `make clean` runs, and vpnd
  exits with 128 plus the signal number. The running step is not killed by
  vpnd; terminal signals reach it directly.
- The Vultr root ignores provider drift in `os_id` and adds a postcondition
  that refuses a plan when the requested `os_id` differs from the node's
  `os_id`. An OS change goes through a replacement node.
- `smoke-test.yml`, `verify.yml` and `security-verify.yml` import one shared,
  `always`-tagged pre-task that refuses a host whose inventory `env` is not
  `ENV`. Their Make recipes pass `ENV` explicitly; `make smoke-test` requires
  the inventory.
- The Hetzner root accepts an optional `admin_ssh_key_name`. When it is set,
  the root reads that project key, requires that its public key equals
  `admin_ssh_public_key`, and does not create a key. Existing state moves to
  the indexed key address without change.

## Capabilities

### New Capabilities

- `operations/deployment-audit-boundaries`: plaintext cleanup after operator
  interrupts, OS-image change refusal, environment binding of verification
  plays and shared provider SSH keys.

### Modified Capabilities

- None. The deployment readiness requirements remain in force.

## Impact

- vpnd: `commands/__init__.py`, `commands/deploy.py`, `commands/reconverge.py`.
- Ansible: `playbooks/smoke-test.yml`, `verify.yml`, `security-verify.yml`,
  a new `playbooks/tasks/selected-env.yml`.
- Makefile: `verify`, `security-verify` and `smoke-test` recipes.
- Terraform: Vultr and Hetzner provider roots, variables, examples and tests.
- Docs: folder notes, blue-green guidance for Hetzner.
- A Vultr tfvars `os_id` that differs from an existing node now refuses at
  plan. A verify or smoke-test run with a host from another environment now
  refuses before any host task. This change authorizes no deployment.
