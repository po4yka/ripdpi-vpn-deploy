# Runbook: stand up a split-hop pilot

Operator procedure for the two-node research topology in
`docs/SPLIT-HOP-TOPOLOGY.md`. Both halves are Ansible-managed. The current
ingress role policy-routes only dedicated probe-matrix runtime users, so this
runbook proves the research topology, not a family production migration.

## Preconditions

- Two disposable VPS environments provisioned through any supported Terraform
  roots, with separate provider state and SOPS scopes.
- Node A's typed `public_listeners` contract admits the configured
  `split_hop_ingress.listen_port` over UDP.
- SOPS + age and the operator SSH identity are configured as in
  `docs/SECRETS.md`.
- WireGuard tools are available only for local key generation; Ansible installs
  them on both nodes.

## 1. Generate node-specific keys

Run on the operator workstation in a mode-0700 directory:

```bash
umask 077
mkdir -p "$HOME/.config/vpn-provision/split-hop"
cd "$HOME/.config/vpn-provision/split-hop"
wg genkey | tee node-a.key | wg pubkey > node-a.pub
wg genkey | tee node-b.key | wg pubkey > node-b.pub
wg genpsk > shared.psk
```

Never share a private key between nodes. Load the values into the encrypted
SOPS file for each node:

```yaml
# Node A only
split_hop_ingress_secrets:
  node_a_private_key: "<node-a.key>"
  node_b_public_key: "<node-b.pub>"
  preshared_key: "<shared.psk, or empty>"
```

```yaml
# Node B only
split_hop_egress_secrets:
  node_b_private_key: "<node-b.key>"
  node_a_public_key: "<node-a.pub>"
  node_a_public_ip: "<Node A public IPv4>"
  preshared_key: "<same shared.psk, or empty>"
```

Validate each encrypted file through its normal environment:

```bash
PROVIDER=<provider-a> ENV=<env-a> make decrypt validate-secrets clean
PROVIDER=<provider-b> ENV=<env-b> make decrypt validate-secrets clean
```

Delete the temporary key files after both encrypted files have been verified.

## 2. Configure Node B (egress)

In Node B host vars or its lab cohort:

```yaml
allow_research_roles: [split-hop-egress]
vpn:
  enable_split_hop_egress: true
  enable_split_hop_ingress: false
  enable_xray_reality: false
  enable_nginx_xhttp: false
  enable_hysteria: false
  enable_amneziawg: false
```

Review and deploy through the ordinary provider/environment boundary:

```bash
PROVIDER=<provider-b> ENV=<env-b> make dry-run
PROVIDER=<provider-b> ENV=<env-b> make deploy
```

Node B must have no client-facing transport listener. Its `shop0` peer has
Node A as `Endpoint` and `PersistentKeepalive`, which makes B the initiator.

## 3. Configure Node A (ingress)

In Node A host vars or its lab cohort:

```yaml
allow_research_roles: [split-hop-ingress, probe-matrix-target]
vpn:
  enable_split_hop_ingress: true
  enable_split_hop_egress: false
  enable_probe_matrix_target: true
```

If an existing owned probe target is used instead, omit
`probe-matrix-target` from both the allowlist and toggles. Then deploy:

```bash
PROVIDER=<provider-a> ENV=<env-a> make dry-run
PROVIDER=<provider-a> ENV=<env-a> make deploy
```

Node A's peer deliberately has no `Endpoint` and no keepalive. The role owns
`/etc/wireguard/shop0.conf`, routing table 200, the fwmark rule, and nftables
table `inet split_hop_ingress`; hand edits will be overwritten.

## 4. Verify the topology

On Node B, `wg show shop0` must report a recent handshake, increasing RX/TX,
and persistent keepalive. On Node A, the same command must show the learned B
endpoint without a configured keepalive.

On Node A, verify the managed policy:

```bash
sudo nft list table inet split_hop_ingress
ip rule show
ip route show table 200
```

The nftables rule must mark only new original-direction sockets owned by the
dedicated probe runtime UIDs. Do not broaden it to all Xray, nginx, or Hysteria
traffic as part of this pilot.

Generate permission-checked target profiles and run the authenticated matrix
as described in `docs/PROBE-MATRIX.md`. A public-IP lookup alone is not
sufficient evidence: preserve the redacted matrix verdict, handshake age,
per-node flow classification, and direct-control result.

## 5. Observation and acceptance

Collect 24–72 hours of flow data from an independent observation point. The
pilot passes only when:

1. B remains the WireGuard initiator throughout the window.
2. Authenticated split-hop cells pass while the direct control is healthy.
3. The per-node dual-role score stays below the selected research threshold.
4. Added latency and loss remain within the pilot's stated budget.
5. Removing B produces an explicit red result; local listener health is not
   misreported as end-to-end success.

Store only redacted evidence. Do not commit endpoints, provider account data,
keys, client identifiers, raw flow logs, or labels tied to a carrier,
operator, or geography.

## Tear-down

Set both enable toggles false in their respective host variables and remove the
exact allowlist entries. The current roles are skipped when disabled and do not
remove already-created files or services, so a toggle-only redeploy is not a
complete cleanup. End the pilot by destroying its disposable provider
environments; do not repurpose those nodes or invent broad firewall cleanup
commands in this runbook.
