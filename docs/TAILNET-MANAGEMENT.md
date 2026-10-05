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

The current production inventory profiles `vpn-p0-self-steal`, `vpn-p1-web`
and `vpn-p2-udp` explicitly enable this role. Their one reviewed controller
address per family is shared from `group_vars/all.yml`; the global VPN toggle
remains false, so every other cohort stays inert unless it opts in separately.
Changing the controller device or Tailnet addresses requires updating the
saved Tailnet ACL and these exact sources together, then repeating staging and
serial live acceptance.

Review the complete Tailnet ACL or grants document separately. An additive
narrow rule does not neutralize an existing broad grant. Applying that policy
is an external authorization change and requires its own fresh diff and
action-time approval.

## Bootstrap one node

The required `build_environment` is distinct from the exact Terraform workspace.
Inventory emits it as `vpn_build_environment` from `var.build_env`; the read-only
guest probe checks the root-owned `/etc/vpn-build-id` before access writes.
Named permanent workspaces retain their names. Every disposable workspace still
requires its exact cleanup manifest, regardless of the build label.

First enrollment uses `make bootstrap-tailnet`, not ordinary deploy. Before
any guest writes on disposable staging, create the exact-state cleanup
manifest described in [CI-REAL-DEPLOY.md](CI-REAL-DEPLOY.md#uuid-bound-operator-staging-cleanup).
Wait for cloud-init, acquire and verify the public host-key pin, and install
the exact SSH recovery foundation through `make install-ssh-recovery` in the
approved exclusive window. Bootstrap refuses a dirty or mismatched source.

Create an operator-owned mode-`0600` JSON config in a private directory. Its
exact fields are:

| Field | Required value |
|---|---|
| `schema_version` | Integer `2` |
| `environment`, `provider` | Exact routed Terraform workspace, including named permanent workspaces; `upcloud`, `scaleway` or `vultr`. Disposable `ci-staging-*` workspaces always require their manifest; disposable Scaleway is unsupported. |
| `build_environment` | Canonical `vpn_build_environment` emitted by inventory and matching `/etc/vpn-build-id`; named permanent workspaces require `prod` |
| `inventory_alias`, `public_address`, `ssh_port` | One exact canonical inventory node and its current public SSH endpoint |
| `host_key_sha256` | Lowercase hex SHA256 of the decoded pinned Ed25519 public-key blob |
| `public_sources` | Exact observed controller public source IPs, not CIDRs |
| `approved_sources` | Exact reviewed Tailnet controller IPs, matching the later cohort policy |
| `source_revision`, `deployable_digest` | Clean source revision and deployable digest from `scripts/deploy-source-identity.sh --identity` |
| `known_hosts` | Absolute path to the verified known-hosts file, keyed by the inventory host-key alias |
| `cleanup_manifest` | Absolute current exact-state staging manifest path; JSON `null` for production |
| `policy_approval` | JSON `null` for the canonical/empty layout; otherwise the reviewed legacy plan approval object below |
| `output` | New absolute handoff path under an operator-owned mode-`0700` directory |

Unknown fields, ambiguous nodes, unsafe files and missing pins refuse before
remote writes. Do not invent a management address or reuse a stale cleanup
manifest. Create a short-lived one-node enrollment key separately; do not put
it in Git, SOPS, inventory, a Make argument or shell history:

```bash
IFS= read -r -s TAILSCALE_AUTH_KEY </dev/tty
export TAILSCALE_AUTH_KEY
make bootstrap-tailnet ANSIBLE_LIMIT=<exact-inventory-alias> \
  TAILNET_BOOTSTRAP_CONFIG="$HOME/.config/vpn-provision/bootstrap-tailnet.json"
unset TAILSCALE_AUTH_KEY
```

The controller validates inputs and public-path readiness, installs pinned
inert components through the dedicated bootstrap playbook, then sends the key
only on strict SSH stdin. Ansible never receives the key. The guest creates a
random mode-`0600` auth file under `/run/vpn-tailnet-management`, uses
`--auth-key=file:`, and removes and fsyncs it after login. Bootstrap never
changes provider firewall policy or Tailnet ACLs.

Before changing access, the guest verifies both the enabled early boot
firewall recovery unit and the late recovery worker, then arms one durable
generation-, target-, nonce- and snapshot-bound transaction. Its 300-second
lease uses monotonic
time and boot identity; reboot cannot extend it. The minimal guest firewall
preserves exact approved public SSH sources, allows exact `tailscale0` sources
on the same port and opens no VPN listeners. Foreign firewall ownership or
pending network transactions refuse without flushing unrelated policy. The
exact four empty daemon tables (`ip/ip6 filter/nat`) may remain as inert
baseline objects; any chains, rules, sets, maps or extra attributes disqualify
that exception. Their original state is included in apply and rollback.

After login, fresh public and Tailnet SSH and SFTP connections must verify the
same original host key and real socket addresses. Local status alone cannot
confirm. A durable confirmation prevents later recovery from logging out the
node and records the confirmed Tailnet node ID and addresses. The private
handoff contains the observed socket contexts and binding, not the auth key
or a VPN acceptance result. If output publication fails after
confirmation, inspect status and rerun with the same binding and a new output
path, without an enrollment key; do not log out a committed identity.

## Recovery and ordinary deployment

A persistent worker rolls back an expired unconfirmed transaction. At boot,
the early worker restores firewall files and effective policy before nftables,
networking and `ssh.socket`, without calling tailscaled. The late worker runs
after tailscaled and gates only `ssh.service`, completing owned-identity logout
and firewall service reconciliation. A socket may listen after early recovery,
but sshd cannot serve/authenticate connections until late recovery succeeds.
This separation avoids the socket/basic-target/daemon dependency cycle.

Both workers share the same private lock and durable rollback decision.
Interrupted restoration is replayable; confirmation refuses once rollback
begins. Corrupt or foreign state remains for diagnosis. Pinned inert packages
may remain after rollback, but the access-changing runtime policy is restored.

### Disposable staging recovery exercises

Do not approximate controller loss by interrupting `make bootstrap-tailnet`:
its normal cancellation path requests an explicit rollback. After the cleanup
manifest and SSH recovery foundation exist, exercise the two autonomous paths
through their fixed staging-only verbs. Each run consumes a different one-use
enrollment key and MUST complete before positive bootstrap:

```bash
IFS= read -r -s TAILSCALE_AUTH_KEY </dev/tty
export TAILSCALE_AUTH_KEY
make staging-tailnet-controller-loss-test ANSIBLE_LIMIT=<exact-inventory-alias> \
  TAILNET_RECOVERY_CONFIG="$HOME/.config/vpn-provision/controller-loss.json"
unset TAILSCALE_AUTH_KEY

IFS= read -r -s TAILSCALE_AUTH_KEY </dev/tty
export TAILSCALE_AUTH_KEY
make staging-tailnet-reboot-recovery-test ANSIBLE_LIMIT=<exact-inventory-alias> \
  TAILNET_RECOVERY_CONFIG="$HOME/.config/vpn-provision/reboot-recovery.json"
unset TAILSCALE_AUTH_KEY
```

Each owner-controlled mode-`0600` config has exactly `schema_version: 2`, an
absolute `bootstrap_config` path, and new absolute `evidence` and `diagnostic`
paths beneath owner-controlled mode-`0700` directories. The referenced
bootstrap config uses the same contract as positive bootstrap, but its handoff
output must still be absent and must differ from both recovery outputs; the two
recovery outputs must also differ from each other. Recovery exercises accept
only `ci-staging-*` with current cleanup ownership; production is categorically
refused.

Schema 2 replaces schema 1: add a fresh, absent `diagnostic` path before the
next recovery run. Schema-1 files are rejected before SSH or guest changes;
there is no compatibility fallback because an unrecorded reboot failure is the
defect this contract closes.

The controller-loss verb obtains a durable pending enrollment in a dedicated
worker, kills that worker with `SIGKILL`, waits through the guest lease and
requires a fresh successful recovery invocation. A private ownership pipe also
terminates the paused worker if its parent controller disappears. The reboot
verb kills the worker, initiates a real reboot over pinned public SSH, requires
a changed boot identity and current-boot success from both recovery units. Both
require final idle state plus fresh public SSH and SFTP and the strict preinstall
probe. They never call confirmation or explicit rollback. Success evidence is
atomically published mode `0600` and contains only hashes and categorical
verdicts; it excludes addresses, raw nonces/capabilities, keys, provider state
and remote output. A categorical best-effort audit record follows successful
publication. A reboot failure after public SSH is observed down may publish the
separate `diagnostic` artifact with `status: incomplete` and only categorical
reboot-request, SSH down/up, recovery-status and unit-proof stages. It contains
no addresses, exception text or remote output, is not success evidence, and
does not emit the passed audit record. Any ambiguous result retains private and
guest evidence for diagnosis and publishes no success artifact.

After bootstrap, render the exact node with
`TAILNET_HANDOFFS=<private-bootstrap-handoff-path> make inventory`. For
multiple hosts, supply one absolute handoff path or `-` per `HOSTS` entry. The
renderer reads each mode-0600 handoff without following the final path,
validates its confirmation digest and public/Tailnet socket contexts, binds it
to the exact Terraform alias, public address and SSH port, and derives the
management address whose IPv4 or IPv6 path was actually confirmed. It keeps
Terraform's public service address
separate. The handoff itself is not the deploy input schema. Keep the separate
`DEPLOY_PROMOTION_CONFIG_FILE` and fresh private
`DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE` required by
[RUNBOOK-deploy.md](RUNBOOK-deploy.md); bootstrap does not satisfy protocol proof.
Both `make dry-run` and `make deploy` reject enrollment keys and require the
existing dual paths. The ordinary Tailnet role verifies installed state only;
it never installs or enrolls implicitly. Before convergence, it requires a
confirmed guest receipt matching the inventory alias, public address, SSH port,
approved controller sources and current Tailnet node identity. A missing or
mismatched receipt refuses without host writes. Previously enrolled nodes
without this receipt require a separately approved bootstrap decision.

## Fail-closed postconditions

Fresh enrollment must leave all of these true:

- backend state is `Running` with DNS, route, exit-node, route advertisement,
  shields-up, Tailscale SSH and automatic netfilter management disabled;
- both canonical Tailnet address families are present;
- `/etc/resolv.conf`, the canonical default-route JSON and full `sshd -G`
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

An offline boot inspection on the pre-rollout P0 node found no Tailscale
binary, service, recovery unit or state. That is a clean missing-foundation
boundary, not a daemon boot failure: rebooting alone cannot create this
management path. Installation and enrollment must use the canonical one-node
bootstrap flow above; do not install ad hoc through the provider console.

The package defaults pin Tailscale stable `1.102.3` and the official repository
key digest. Updating either pin requires reviewing the official stable package
repository, focused controller tests, the role's Molecule scenario, full CI and
fresh staging proof before production use.


## Existing managed firewall bootstrap

The credential-free `make render-console-bootstrap` renders a private command;
it never executes it or changes provider policy. Its mode-0600 request contains
`schema_version: 1`, absolute `bootstrap_config`, exact `hostname`, verified
`root_filesystem_uuid`, absolute UNIX `expires_at` no more than 900 seconds
away, and a new absolute `output` under a mode-0700 directory. Console/GRUB
execution requires separate emergency authorization. Shared systemd directories
remain 0755; application state stays private in RAM. Ordinary reboot removes
that state. Expiry validates all nonce rules before one atomic deletion and
shares the RAM coordination lock with policy replacement.

Use `make inspect-tailnet-bootstrap ANSIBLE_LIMIT=<exact-alias>
TAILNET_BOOTSTRAP_CONFIG=<private-config>` to inspect the exact managed legacy
policy through pinned public SSH. The config's new `output` receives the private
plan instead of a handoff. Review the main-file hash, original rules, candidate
rules and preserved VPN listeners. Set `policy_approval` in a fresh bootstrap
config to `{"schema_version":1,"decision":"approve-managed-legacy-v1",
"plan_sha256":"<reviewed-plan-digest>"}` and select a distinct handoff output.
Only the pre-Tailnet managed layout is supported. Foreign objects, includes,
arbitrary runtime drift and changed approval digests refuse.

The existing durable enrollment transaction adopts that candidate; this is
not a second firewall transaction. Recovery generation v4 and firewall snapshot
schema 2 distinguish observed console ingress from the original durable policy.
Rollback always retires console ingress and restores the original files, rules
and service state. It does not replay an emergency rule even before expiry.
Enrollment still requires real public and Tailnet SSH/SFTP proof. A console
lease must retain the complete 300-second transaction budget plus 60 seconds;
installation is separately bounded by the remaining lease. Provider firewall
retirement stays in the invoking operator's Terraform lifecycle.

The approval digest uses `review_digest()` projection version 1, not a raw
JSON file hash: it binds every effective policy object, file hash and service
state, while ignoring only the complete object-free daemon quartet and replacing
replay text with its validated semantic policy digest. Package startup may add
that quartet; a partial quartet or any object in it still refuses.

Generation-v3 or unknown installed Tailnet bundles refuse before replacement.
This bootstrap establishes first enrollment on nodes without a prior Tailnet
identity; it does not overwrite a pending or confirmed older transaction. The
existing SSH recovery foundation has an independent source digest.
