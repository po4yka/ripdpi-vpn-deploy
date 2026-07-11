# Runbook: stand up a split-hop pilot

Operator-side procedure for piloting the two-VPS split-hop topology described in `docs/SPLIT-HOP-TOPOLOGY.md`. Node A runs the client-facing transports plus the declarative `split-hop-ingress` role. Node B runs the declarative `split-hop-egress` role with client-facing transports disabled. This remains a pilot; flow-data verification is operator-driven.

## Pre-requisites

- Two VPSes already provisioned via Terraform, each with its own provider environment and inventory.
- WireGuard installed on the operator workstation for key generation only.
- SOPS + age keys configured per `docs/SECRETS.md`.

## Step 1 — generate the WireGuard material

Run on the operator workstation, never on either VPS:

```bash
mkdir -p ~/secrets-split-hop/ && cd ~/secrets-split-hop/
wg genkey | tee node_a.key | wg pubkey > node_a.key.pub
wg genkey | tee node_b.key | wg pubkey > node_b.key.pub
wg genpsk > shared.psk  # optional
```

Load the material into the owning SOPS files:

| Material | Node A ingress SOPS | Node B egress SOPS |
|---|---|---|
| Node A private key | `split_hop_ingress_secrets.node_a_private_key` | — |
| Node A public key | — | `split_hop_egress_secrets.node_a_public_key` |
| Node B private key | — | `split_hop_egress_secrets.node_b_private_key` |
| Node B public key | `split_hop_ingress_secrets.node_b_public_key` | — |
| Optional PSK | `split_hop_ingress_secrets.preshared_key` | `split_hop_egress_secrets.preshared_key` |

No private material is written directly to `/etc/wireguard`; each role renders its managed `shop0` configuration from SOPS.

## Step 2 — load the paired SOPS blocks

Add this shape to Node A's SOPS file:

```yaml
split_hop_ingress_secrets:
  node_a_private_key: "REPLACE_WITH_NODE_A_WG_PRIVATE_KEY"
  node_b_public_key: "REPLACE_WITH_NODE_B_WG_PUBLIC_KEY"
  preshared_key: "REPLACE_WITH_SHARED_PSK_OR_EMPTY"
```

Add this shape to Node B's SOPS file:

```yaml
split_hop_egress_secrets:
  node_b_private_key: "REPLACE_WITH_NODE_B_WG_PRIVATE_KEY"
  node_a_public_key: "REPLACE_WITH_NODE_A_WG_PUBLIC_KEY"
  node_a_public_ip: "REPLACE_WITH_NODE_A_PUBLIC_IPV4"
  preshared_key: "REPLACE_WITH_SHARED_PSK_OR_EMPTY"
```

Validate both edited SOPS files in their respective environments:

```bash
PROVIDER=<node-a-provider> ENV=<node-a-env> make validate-secrets
PROVIDER=<node-b-provider> ENV=<node-b-env> make validate-secrets
```

After both files are encrypted and validated, securely remove the workstation copies according to the operator workstation's storage policy.

## Step 3 — configure each node declaratively

In Node A's host vars, keep the required client-facing transport toggles enabled and add:

```yaml
vpn:
  enable_split_hop_ingress: true

allow_research_roles: [split-hop-ingress]
```

In Node B's host vars, enable only the egress role and explicitly disable client-facing transports:

```yaml
vpn:
  enable_split_hop_egress: true
  enable_xray_reality: false
  enable_nginx_xhttp: false
  enable_hysteria: false
  enable_amneziawg: false
```

`split-hop-ingress` is RESEARCH-tier and therefore requires the explicit allowlist on Node A. `split-hop-egress` is not RESEARCH-tier and must not be added to Node B's allowlist.

Deploy each node against its own environment and inventory:

```bash
PROVIDER=<node-a-provider> ENV=<node-a-env> make deploy
PROVIDER=<node-b-provider> ENV=<node-b-env> make deploy
```

The roles assert their required secrets before rendering `/etc/wireguard/shop0.conf`. Node A also receives the role-owned nftables/conntrack policy; Node B owns the initiator endpoint, keepalive, forwarding interface, and NAT policy.

## Step 4 — verify tunnel direction and policy

On Node B:

```bash
sudo wg show shop0
```

Confirm a recent handshake, rising RX/TX counters, the configured Node A endpoint, and persistent keepalive.

On Node A:

```bash
sudo wg show shop0
```

Node A has no configured peer endpoint and no persistent keepalive. After Node B initiates, `wg show` may display the learned runtime endpoint; that does not change the configured initiator direction.

First verify only tunnel/NAT reachability with an interface-bound diagnostic if needed; this does not prove the UID policy. Then exercise the marked policy with a neutral connection owned by a declared runtime user:

```bash
sudo -u <declared-runtime-user> curl --silent --show-error https://example.com/
```

Choose a transport runtime user whose numeric UID matches one of the declared `probe_matrix_runtime_users` values used by the ingress policy. Confirm the request succeeds through Node B and correlate it with `shop0` counters. This checks the declared runtime UID's marked route; it is distinct from an interface-bound tunnel diagnostic and does not replace the normal client-facing transport smoke test against Node A.

## Step 5 — collect 24–72 h of flow data

The ADR's threat-model test requires that each node appears single-role in a flow record from an upstream observer. Capture with provider flow logs where available or with `tcpdump` on a separate observation host bridged onto the upstream side.

The classifier metric to compute:

```
RSS(IP) = (count of flows where IP is both inbound-receiver and
           outbound-initiator within a 5-min window)
          /
          (total flows involving IP in that window)
```

The published pilot threshold for relay-suspicion classification is RSS > 0.5. After deploy, both Node A and Node B should sit RSS approximately 0: A because it has no newly initiated upstream flows the observer can see, and B because it has no client-inbound flows. Treat this as a result to measure, not a completed claim.

## Step 6 — publish the pilot results

Write up the flow-data results as `docs/SPLIT-HOP-PILOT-<YYYY-MM-DD>.md` with:

- Per-node RSS over the observation window
- Latency added per hop
- Operational cost for the two-VPS pair versus a single VPS
- Recommendation on whether to promote split-hop from pilot status

Do not name the operator, carrier, or geography in the pilot writeup; describe cohorts and paths by technical signature only.

## Tear-down

Set `vpn.enable_split_hop_ingress: false` in Node A's host vars and `vpn.enable_split_hop_egress: false` in Node B's host vars, then redeploy both environments separately:

```bash
PROVIDER=<node-a-provider> ENV=<node-a-env> make deploy
PROVIDER=<node-b-provider> ENV=<node-b-env> make deploy
```

Disabling a role prevents further management but does not remove state that an earlier converge created. The safe pilot lifecycle boundary is therefore the ephemeral nodes: after recording results and disabling both toggles, destroy each VPS through its respective provider environment. Do not flush host firewall tables or hand-delete role-owned configuration.
