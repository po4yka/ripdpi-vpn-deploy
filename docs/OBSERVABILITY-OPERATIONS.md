# Central observability operator surface

This runbook covers the exact-host commands for the centralized observability
agent, control plane, and independent dead-man. It does not authorize a
provider change, production deployment, credential creation, fault injection,
or paging cutover. The control plane and dead-man must already exist in the
generated inventory.

Every command requires an exact inventory alias, an explicit environment and
one component: `agent`, `control-plane`, or `deadman`. Wildcards, groups and
`all` are rejected before SSH or Ansible. The controller uses the inventory's
pinned SSH identity and the supplied `known_hosts`; it snapshots the selected
alias into a private one-host inventory, disables ambient Ansible vars plugins,
and supplies strict SSH options without a local config, proxy or multiplexing.
It never calls `ansible/playbooks/site.yml`. `OBSERVABILITY_ENVIRONMENT` has no
fallback to `ENV`: every Make invocation must supply it explicitly.

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
Use the dedicated `remove` command for disable convergence. `remove` also
requires that same private deployment-vars snapshot, so it disables the actual
configured roots instead of guessing defaults.

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
| `make observability-drill` | authenticated local gateway on the staging control plane | submits one synthetic firing/resolved pair | **yes: private staging Telegram route** |
| `make observability-silence-create` | private bounded request and named owner credential | finite scoped notification suppression | no synthetic incident |
| `make observability-silence-delete` | silence UUID and named owner credential | removes that owner's silence | existing incident delivery may resume |
| `make observability-rotate` | replacement private vars/secrets | converges only the selected role and host | may restart that role's units |
| `make observability-rollback` | private last-known-good vars/secrets plus a digest-bound rollback manifest | reconverges only the control-plane role and host to its remotely retained previous generation | may restart that role's units; no notification is claimed |
| `make observability-remove` | private deployment vars snapshot | converges `enabled: false` for only the selected role and host | no; control-plane TSDB retention remains intact |

The status output is a bounded JSON object containing only the requested alias,
component, categorical unit states and aggregate readiness. It is passive and needs no locally decrypted secrets. Control-plane readiness
uses the existing remote sender credential without exposing it. `healthy` is local component readiness, not fresh fleet telemetry,
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
retained control-plane material and provide a private `0600` JSON manifest whose
host, component, previous generation and SHA-256 values bind both files. The
controller reads the actual remote `previous.yml` link through the same strict
transport and refuses a missing, divergent, or arbitrary generation. Agent and
dead-man rollback remain unavailable through this operator surface until they
retain an equivalent durable previous-generation link.

```sh
export OBSERVABILITY_ROLLBACK_MANIFEST="/owner/private/path/control-plane-rollback.json"
make observability-rollback
```

Removal is component-scoped and convergent:

```sh
make observability-remove
```

## Staging delivery drill

`make observability-drill` is accepted only for `staging` plus the
`control-plane` component and requires `OBSERVABILITY_SILENCE_OWNER` to name a
configured operator. The token remains in its fixed remote root-owned credential
file; do not provide a token in argv or environment. It sends a clearly labelled synthetic warning with
one stable fingerprint and keeps it firing for more than the fixed 30-second
Alertmanager group wait. Before resolving it, the controller requires a bounded
authenticated loopback gateway observation of that active fingerprint routed to the
exact `telegram-primary` receiver. It performs no
deploy, provider call, service restart, public request, or production fault
injection.

Command success proves only that the local Alertmanager API accepted the pair.
Record the separately observed Telegram firing and resolved messages; API
acceptance is not human receipt. A dead-man loss/recovery drill, service or node
failure injection, credential rotation proof, two-vantage VPN proof and live
rollback remain separate approved staging steps.

## Finite maintenance silences

Alerting requires `observability_control_plane.alerting.silence_gateway.enabled`
and dedicated gateway authorities in `observability_secrets.silence_gateway`.
Bind the existing private role-vars mapping to the SOPS fields instead of
copying credential values. For example, the `alerting.silence_gateway` value in
the complete control-plane vars document can be:

```yaml
silence_gateway: >-
  {{ observability_secrets.silence_gateway | combine({
      'enabled': true, 'listen': '127.0.0.1:19094',
      'environment': 'staging', 'max_ttl_seconds': 14400}) }}
```

The role uses a fixed private configuration root and loopback-only gateway;
Alertmanager's underlying API requires a separate client certificate held only
by the gateway. Sender credentials cannot create or delete silences. A named
operator may delete only silences it created. The default maximum TTL is four
hours, bounded by the configured policy.

Create a mode-0600 JSON request in an owner-controlled directory. Its exact
fields are `schema_version: 1`, a technical-slug `reason`, UTC `starts_at` and
`ends_at`, and `matchers`. Matchers require the configured `environment` and
at least one exact `node` or `policy`; optional allowed stable labels further
narrow the scope. Do not use `node_id`, regex matchers, an owner field, tokens,
free-text diagnostics or an indefinite end time in this file.

```sh
export OBSERVABILITY_SILENCE_OWNER="operator"
export OBSERVABILITY_SILENCE_REQUEST="/owner/private/path/maintenance.json"
make observability-silence-create

# Use the UUID returned by the successful create operation.
export OBSERVABILITY_SILENCE_ID="<returned-uuid>"
make observability-silence-delete
```

These explicit mutation commands use the already-selected exact inventory
host and environment. They do not deploy, alter metrics, reset incident times,
or claim recovery. Alertmanager expires a silence at its finite end even if
the gateway is temporarily down. The private bounded audit retains categorical
creation, expiry and deletion records without bearer tokens. A successful API
response is not the required real alert delivery/expiry staging evidence.

## Failure handling

The controller emits only categorical failures. On an Ansible or SSH error,
inspect locally retained operator logs through the normal protected workflow;
do not retry with debug/diff, paste decrypted variables into argv, or replace
the exact role command with `site.yml`. Rollback refuses missing, mutable,
foreign-owned, group-writable or path-shape-invalid generations. Treat that as
an unresolved rollback blocker rather than repairing symlinks by hand.

### Alerting authority recovery boundary

An ordinary activation failure restores the captured credential/configuration
files and previous service states. Failed restoration retains a private snapshot
under `/etc/observability-control-plane/.authority-rollback` and blocks further
publication and disable. Do not delete that snapshot or blindly restart services;
restore the exact recorded authority under an exclusive maintenance window first.
Runtime binary installation and abrupt process/host loss are outside this
configuration rollback guarantee. Check mode inspects and predicts changes without
creating a snapshot, starting services, or performing readiness requests.
