# Real-VPS AWG/NAT evidence sentinel

The recurring lane uses three independent machines: an owner-controlled TCP
and UDP echo host, a VPS with a dedicated `awg-evidence0` interface, and a
physical Linux sentinel. It validates direct controls, initial AWG traffic,
service restart, peer reload, rejection of the old key, recovery with the new
key, interface counters, and the named NAT counter.

This is an explicit standalone research-role exception to the repository's
normal `group_vars/all.yml` toggle plus `site.yml` wiring. The role itself must
not run as part of the ordinary family site. Its echo and server surfaces may
use two different existing family VPS nodes, while the physical sentinel stays
on a third machine. Their credentials, interfaces, services, and firewall
tables remain separate trust boundaries.

## Private input contract

Keep the following variables in a root-readable SOPS file or a temporary
mode-`0600` Ansible vars file. No private value belongs in inventory, Git,
command-line arguments, logs, or evidence artifacts.

- `real_vps_awg_nat_secrets.server_private_key`
- `real_vps_awg_nat_secrets.current_client_public_key`
- `real_vps_awg_nat_secrets.current_preshared_key`
- `real_vps_awg_nat_secrets.sentinel_ssh_public_key`
- `real_vps_awg_nat_secrets.sentinel_ssh_private_key`
- `real_vps_awg_nat_secrets.current_client_config`
- `real_vps_awg_nat_secrets.rotated_client_config`
- `real_vps_awg_nat_expected_placement`

Bind credentials to the current fleet placement in the same protected vars
file. These values are non-secret but security-sensitive:

```yaml
real_vps_awg_nat_expected_placement:
  echo:
    inventory_hostname: vpn-p1-scaleway-pl-waw-1
    ansible_host: REPLACE_WITH_CURRENT_SCALEWAY_PROVIDER_IPV4
    provider: scaleway
    cohort_group: vpn-p1-web
  server:
    inventory_hostname: vpn-p2-vultr-ams
    ansible_host: REPLACE_WITH_CURRENT_VULTR_PROVIDER_IPV4
    provider: vultr
    cohort_group: vpn-p2-udp
```

Before creating a directory, user, service, or firewall table, the role checks
the exact `inventory_hostname`, numeric provider-state `ansible_host`, provider
host var, and cohort membership. A swapped standalone group, redirected alias,
or incomplete generated inventory therefore fails before either host receives
credentials.

The two client configs must have different private keys and preshared keys.
The server public key, endpoint, obfuscation parameters, routes, and address are
ordinary AWG fields inside each private client config. Generate every value
once on an operator-owned machine; never reuse a production peer.

The supported local topology maps the echo to Linux/systemd/nft host
`vpn-p1-scaleway-pl-waw-1` in `vpn-p1-web`, the dedicated AWG interface to
`vpn-p2-vultr-ams` in `vpn-p2-udp`, and the sentinel to the Raspberry Pi. The
inventory hostnames come from provider state; cohort groups come from the
matching `COHORTS` entries during inventory rendering. A macOS machine is not
a supported echo host.
The non-secret inventory has exactly one host in each group:
`awg_evidence_echo`, `awg_evidence_server`, and `awg_evidence_sentinel`. Set the
echo global address, sentinel global source address, P2 egress address, P2 SSH
host/key pin, runner ID, exact source SHA, and source-bundle path in protected
vars. The echo policy admits only the sentinel's direct address and the P2
egress address seen after AWG NAT. The dedicated UDP listener (default `51920`)
must first be present in the canonical provider `public_listeners` and deployed
`public_listener_contract`. Add the exact `awg-evidence0` to uplink tuple to
`firewall_forward_interface_contract`, then converge the ordinary site/firewall
play before running this provisioning play. The evidence role verifies both
live canonical rules and refuses to start the interface when either is absent;
it never rerenders the production firewall from its narrow private vars.

The echo host has the same canonical-firewall prerequisite: add
`awg-evidence-echo-tcp` TCP/10001 and `awg-evidence-echo-udp` UDP/10002 (or the
configured echo ports) to its provider `public_listeners`. Add
`awg-evidence` UDP/51920 to the P2 provider contract. The ordinary runtime
listener manifest exposes these entries only when
`real_vps_awg_nat_mode=echo` or `server`, so the provider/runtime exact-match
guard remains fail-closed. Render each matching mode as a host var beside its
exact provider contract, then converge the ordinary site/firewall before
evidence provisioning:

```bash
HOSTS="scaleway:prod,vultr:prod" \
COHORTS="p3-ts,p2-udp" \
AWG_EVIDENCE_MODES="echo,server" \
ANSIBLE_SSH_PRIVATE_KEY_FILE=/secure/operator-key \
scripts/render-inventory.sh

cd ansible
ansible-playbook playbooks/site.yml --limit vpn-p3-ts
ansible-playbook playbooks/site.yml --limit vpn-p2-udp \
  --extra-vars @/secure/real-vps-awg-nat-forward.yml
```

Apply each provider change locally, then rerender the inventory before these
ordinary site converges; `terraform_public_listeners_b64` must contain the
applied provider contract. The P2 private forward vars must contain exactly one
`firewall_forward_interface_contract` entry from `awg-evidence0` to its real
uplink. The standalone inventory must retain each echo/server host's rendered
`terraform_public_listeners_b64` host variable; its play decodes that value for
preflight. Both roles verify the live canonical rules; the echo's separate
source gate then restricts its ports to the sentinel's direct address and the
P2 NAT egress address.

Server mode deliberately supports the existing converged P2 Linux host, not a
blank VPS: it refuses to mutate the host unless `/usr/bin/awg`,
`/usr/bin/awg-quick`, and `net.ipv4.ip_forward=1` are already present.

The sentinel never downloads build inputs from GitHub or another forge. Supply
offline Git bundles for the already-pinned `amneziawg-go` and
`amneziawg-tools` commits plus their SHA-256 digests through
`real_vps_awg_nat_awg_go_source_bundle*` and
`real_vps_awg_nat_awg_tools_source_bundle*`. The same bundle helper below can
materialize them from trusted clean checkouts; its printed SHA must equal the
commit pin in role defaults. Also supply a `vendor/`-only tar archive for the
pinned `amneziawg-go` checkout and its SHA-256 through
`real_vps_awg_nat_awg_go_vendor_archive*`. Generate the vendor tree on an
operator-controlled machine at the pinned commit. The sentinel verifies all
three archives, builds inside a network namespace with no network interface,
and stores the result under a digest-keyed read-only toolchain directory. An
existing toolchain is reused only after its manifest, ownership, modes, tree
digest, and command digests all validate. `amneziawg-go`, `awg`, and
`awg-quick` are activated together through one versioned `active-bin` symlink
while holding the recurring lane's lock, so a timer cannot observe a mixed
toolchain.

## Offline exact-source installation

Build the source bundle from a clean committed checkout. The command prints a
JSON object containing the values for `real_vps_awg_nat_expected_source_sha`,
`real_vps_awg_nat_source_bundle_sha256`, and
`real_vps_awg_nat_expected_source_archive_sha256`:

```bash
scripts/build-real-vps-awg-nat-source-bundle.sh \
  --repo "$PWD" \
  --output /secure/tmp/ripdpi-vpn-deploy.bundle
```

Then apply the private vars file without putting values in argv:

```bash
cd ansible
ansible-playbook playbooks/provision-real-vps-awg-nat.yml \
  -i inventory/generated.ini \
  -i /secure/inventory.yml \
  --extra-vars @/secure/real-vps-awg-nat.yml
```

Running from `ansible/` loads the repository's `ansible/ansible.cfg`, including
its role and collection paths.

The sentinel receives the bundle through Ansible, verifies its exact commit,
and invokes `install-real-vps-awg-nat-local.sh`. Each scheduled run streams a
fresh `git archive` to the server's restricted command. The server applies the
archive's local-only Ansible playbook before recording the deployment receipt.

## Validation and evidence

Run once before waiting for the timer:

```bash
sudo systemctl start ripdpi-real-vps-awg-nat.service
sudo systemctl status ripdpi-real-vps-awg-nat.service
sudo jq . /var/lib/ripdpi-real-vps-awg-nat/evidence/latest.json
```

Only `classification: PASS` produces `latest.json`. Missing packages, an
unreachable host, or missing private input is `INFRA_UNAVAILABLE`; a failed
roundtrip, stale counter, no-op restart/reload, accepted old key, or failed
exact-source apply is a product failure. Do not translate either class into a
green skip. Packet captures and private logs remain local; the manifest carries
only their SHA-256 digests.

After a successful run, confirm that the server contains exactly one rule with
comment `awg-nat-awg-evidence0` and that the sentinel timer is enabled. Remove
the temporary source bundle and private operator vars file after provisioning.
