# Central observability operator surface

This runbook covers the exact-host commands for the centralized observability
agent, control plane, and independent dead-man. It does not authorize a
provider change, production deployment, credential creation, fault injection,
or paging cutover. The control plane and dead-man must already exist in the
generated inventory.

Every command requires an exact inventory alias, an explicit environment and
one component: `agent`, `control-plane`, or `deadman`. Wildcards, groups and
`all` are rejected before SSH or Ansible. The controller uses the inventory's
pinned SSH identity and the supplied `known_hosts`; it never calls
`ansible/playbooks/site.yml`.

## Inputs

Set the non-secret scope once:

```sh
export OBSERVABILITY_INVENTORY="$PWD/ansible/inventory/generated.ini"
export OBSERVABILITY_HOST="control-observer"
export OBSERVABILITY_ENVIRONMENT="staging"
export OBSERVABILITY_COMPONENT="control-plane"
export OBSERVABILITY_KNOWN_HOSTS="$HOME/.ssh/known_hosts"
```

`render`, `validate`, `rotate`, and `rollback` additionally require the
materialized SOPS document and a role-variable file. Both must be same-owner,
non-symlink regular files with mode `0600` in an owner-controlled path:

```sh
export OBSERVABILITY_SECRETS_FILE="/owner/private/path/staging.secrets.yml"
export OBSERVABILITY_VARS="/owner/private/path/control-plane-vars.yml"
```

The vars document must contain the selected role's exact mapping with
`enabled: true`; a disabled or different component is rejected before Ansible.
Use the dedicated `remove` command for disable convergence.

The controller rejects enabled `ANSIBLE_DEBUG` or `ANSIBLE_DIFF_ALWAYS` and
sets both false for child processes. It never prints a secrets path, decrypted
value, command output from a journal, process environment, endpoint, or
generation derived from agent credentials.

## Command effects

| Command | Reads | Mutates | Notifies or injects failure |
|---|---|---|---|
| `make observability-render` | private vars/secrets, exact inventory, selected host facts | Ansible check mode only | no |
| `make observability-validate` | private vars/secrets and role syntax | no host contact | no |
| `make observability-status` | fixed systemd properties and loopback readiness on one host | no | no |
| `make observability-drill` | local Alertmanager API on the staging control plane | submits one synthetic firing/resolved pair | **yes: private staging Telegram route** |
| `make observability-rotate` | replacement private vars/secrets | converges only the selected role and host | may restart that role's units |
| `make observability-rollback` | private last-known-good vars/secrets | reconverges only the selected role and host to that complete prior generation | may restart that role's units; no notification is claimed |
| `make observability-remove` | canonical role defaults | converges `enabled: false` for only the selected role and host | no; control-plane TSDB retention remains intact |

The status output is a bounded JSON object containing only the requested alias,
component, categorical unit states and aggregate readiness. It is passive and
secretless. `healthy` is local component readiness, not fresh fleet telemetry,
outside-in VPN availability, Telegram receipt, or dead-man independence.

## Workflow

Validate syntax, then run the remote check-mode render:

```sh
make observability-validate
make observability-render
```

Inspect one component without materializing secrets:

```sh
make observability-status
```

Rotate credentials only after preparing a complete replacement SOPS document
and matching role vars. The role validates and publishes a content-addressed
generation before activation:

```sh
make observability-rotate
```

The controller's confirmation is deliberate but is not production authority.
Production execution still requires an explicitly approved change window and
the repository's deployment evidence gates.

For rollback, point `OBSERVABILITY_SECRETS_FILE` and `OBSERVABILITY_VARS` at the
retained last-known-good material for the selected component. Ansible owns the
runtime state: it validates and reconverges the complete prior agent,
control-plane, or dead-man generation, including owned credentials and ingress,
instead of editing remote links from an operator shell:

```sh
make observability-rollback
```

Removal is component-scoped and convergent:

```sh
make observability-remove
```

## Staging delivery drill

`make observability-drill` is accepted only for `staging` plus the
`control-plane` component. It sends a clearly labelled synthetic warning with
one stable fingerprint and then its resolved form to the loopback Alertmanager
API. It performs no deploy, provider call, service restart, public request, or
production fault injection.

Command success proves only that the local Alertmanager API accepted the pair.
Record the separately observed Telegram firing and resolved messages; API
acceptance is not human receipt. A dead-man loss/recovery drill, service or node
failure injection, credential rotation proof, two-vantage VPN proof and live
rollback remain separate approved staging steps.

## Failure handling

The controller emits only categorical failures. On an Ansible or SSH error,
inspect locally retained operator logs through the normal protected workflow;
do not retry with debug/diff, paste decrypted variables into argv, or replace
the exact role command with `site.yml`. Rollback refuses missing, mutable,
foreign-owned, group-writable or path-shape-invalid generations. Treat that as
an unresolved rollback blocker rather than repairing symlinks by hand.
