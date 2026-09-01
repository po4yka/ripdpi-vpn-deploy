# Restricted Tailnet management

This opt-in role adds a second path to the existing OpenSSH listener. It does
not enable Tailscale SSH, replace host keys, change the SSH port, take over DNS
or routes, advertise routes or an exit node, or manage the Tailnet ACL policy.
Public emergency SSH remains a separate required path.

## Configure source policy

Enable the role and list exact approved Tailnet device addresses in the
reviewed host or cohort variables:

```yaml
vpn:
  enable_tailnet_management: true
tailnet_management:
  approved_sources:
    - 100.64.10.20
    - fd7a:115c:a1e0::1234
```

Entries are individual canonical addresses, not CIDRs. IPv4 must belong to
`100.64.0.0/10`; IPv6 must belong to `fd7a:115c:a1e0::/48`. The guest firewall
opens only those sources on `tailscale0` and the effective existing sshd port.
An empty, duplicate, noncanonical or out-of-range list refuses locally before
the first host write.

Review the complete Tailnet ACL or grants document separately. An additive
narrow rule does not neutralize an existing broad grant. Applying that policy
is an external authorization change and requires its own fresh diff and
action-time approval.

## Enroll one node

Create a short-lived one-node auth key in the Tailnet administration UI. Do not
put it in Git, SOPS, inventory, a Make argument or shell history. Read it into
the environment, select exactly one canonical inventory alias, and keep the
SSH recovery and promotion inputs required by the normal deploy runbook:

```bash
IFS= read -r -s TAILSCALE_AUTH_KEY </dev/tty
export TAILSCALE_AUTH_KEY

make deploy ANSIBLE_LIMIT=<exact-inventory-alias> \
  DEPLOY_SSH_CONTEXTS_FILE="$HOME/.config/vpn-provision/ssh-contexts.json" \
  DEPLOY_PROMOTION_CONFIG_FILE="$HOME/.config/vpn-provision/promotion-configs.json"

unset TAILSCALE_AUTH_KEY
```

The Make boundary rejects command-line credentials. The deploy controller
validates the auth-key shape and one-node selection, then forwards it only to
the `site.yml` Ansible process. The role sends it on controller stdin. The host
controller writes a random mode-`0600` file under the owner-controlled
`/run/vpn-tailnet-management` runtime directory, uses
Tailscale's `--auth-key=file:` form, and removes and fsyncs that file before
returning. Logs and task results remain redacted.

Before `tailscale login`, the controller verifies that the persistent recovery
timer is enabled and active, executes the sandboxed recovery worker successfully,
then fsyncs a private mode-`0600` transaction under
`/var/lib/vpn-tailnet-management`. The record contains a fresh nonce, the exact
recovery generation, the original backend state, and bounded resolver,
default-route and `sshd -T` snapshots with resolver ownership and mode. The
controller and periodic worker serialize on the same root-only lock. The worker
is also a required boot dependency before `ssh.service` or `ssh.socket`; it starts
after `tailscaled`, reconciles an armed record, and only then permits the ordinary
SSH listener to start. Controller loss or reboot while the record is armed makes
the worker log out the new node, verify the original snapshots and remove the
record. Corrupt state or unrelated drift is retained and refused for manual
recovery instead of being overwritten.

After all local postconditions pass, the controller durably marks the record
confirmed before removing it. A crash after that commit can only finish receipt
cleanup; it cannot log out the confirmed node. This local transaction protects
enrollment itself. It does not replace the later provider rollback and fresh
public-plus-Tailnet SSH proof required by the serial promotion workflow.

`make dry-run` never forwards or consumes the capability. It uses the installed
controller's read-only `check` action when available; on a fresh node it reports
the pending enrollment without creating the controller or joining the Tailnet.

## Fail-closed postconditions

Fresh enrollment must leave all of these true:

- backend state is `Running` with DNS, route, exit-node, route advertisement,
  shields-up, Tailscale SSH and automatic netfilter management disabled;
- both canonical Tailnet address families are present;
- `/etc/resolv.conf`, the canonical default-route JSON and full `sshd -T`
  policy are byte-identical to their pre-enrollment snapshots;
- the nftables ruleset has no Tailscale-owned `ts-*` chain or jump.

A failed postcondition logs out a newly enrolled node and verifies the same
snapshots and absence of Tailscale-owned netfilter state. An already-running
node with different managed preferences is refused without mutation.

## What still requires live proof

Molecule exercises configuration, credential cleanup, exact flags and
idempotence with a synthetic CLI and nftables fixture. It does not prove the
Tailnet control plane, ACL enforcement, a fresh pinned SSH connection, stable
host identity, direct emergency access, resolver/routing behavior on a VPS, or
unchanged VPN paths. Those require the authorized isolated staging sequence and
then a separately approved serial fleet window. Do not remove public recovery
access on the strength of source or container tests.

The package defaults pin Tailscale stable `1.102.3` and the official repository
key digest. Updating either pin requires reviewing the official stable package
repository, focused controller tests, the role's Molecule scenario, full CI and
fresh staging proof before production use.
