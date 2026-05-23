# Runbook: stand up a split-hop pilot

Operator-side procedure for piloting the two-VPS split-hop topology
described in `docs/SPLIT-HOP-TOPOLOGY.md`. Pilot only — the Node A
side does not yet have full Ansible coverage; this runbook documents
the manual steps until that lands.

## Pre-requisites

- Two VPSes already provisioned via Terraform (any combination of
  upcloud / hetzner / vultr; typically two different zones so the
  cross-leg RTT stays in the same continent).
- The egress VPS (Node B) is the one that will run
  `enable_split_hop_egress: true`. The ingress VPS (Node A) runs the
  standard transport stack.
- WireGuard installed on the operator's workstation (`apt install
  wireguard-tools` or equivalent) — needed for keygen only.
- SOPS + age keys configured per `docs/SECRETS.md`.

## Step 1 — generate the WG keypairs

Run on the operator workstation. Never on the VPSes.

```bash
mkdir -p ~/secrets-split-hop/ && cd ~/secrets-split-hop/
wg genkey | tee node_b.key | wg pubkey > node_b.key.pub
wg genkey | tee node_a.key | wg pubkey > node_a.key.pub
# optional preshared key
wg genpsk > shared.psk
```

The four files become:

| File | Lives on | Loaded as |
|------|----------|-----------|
| `node_b.key`     | Node B SOPS | `split_hop_egress_secrets.node_b_private_key` |
| `node_a.key.pub` | Node B SOPS | `split_hop_egress_secrets.node_a_public_key` |
| `node_a.key`     | Node A side (no SOPS yet — keep on disk in `/etc/wireguard/shop0.conf` directly) | `[Interface] PrivateKey =` |
| `node_b.key.pub` | Node A side | `[Peer] PublicKey =` on A |
| `shared.psk`     | Both sides  | `split_hop_egress_secrets.preshared_key` on B; `[Peer] PresharedKey =` on A |

Wipe the workstation copies after they are loaded:

```bash
shred -u ~/secrets-split-hop/*.key
```

## Step 2 — load Node B's secrets into SOPS

Edit the egress VPS's SOPS file and add the
`split_hop_egress_secrets` block:

```yaml
split_hop_egress_secrets:
  node_b_private_key: "<contents of node_b.key>"
  node_a_public_key:  "<contents of node_a.key.pub>"
  node_a_public_ip:   "<Node A's public IPv4>"
  preshared_key:      "<contents of shared.psk, or empty string>"
```

Validate the schema with `make validate-secrets`.

## Step 3 — flip the toggle on Node B

In Node B's group_vars (typically a host-specific
`ansible/inventory/<env>.host_vars/<node-b-hostname>.yml`):

```yaml
vpn:
  enable_split_hop_egress: true
  # The standard transport toggles stay off on Node B — Node B
  # carries no client-facing inbound. Disable explicitly:
  enable_xray_reality: false
  enable_nginx_xhttp: false
  enable_hysteria: false
  enable_amneziawg: false
```

Run the standard deploy:

```bash
PROVIDER=<provider-of-node-b> ENV=<env> make deploy
```

The deploy applies the `split-hop-egress` role; the role asserts the
secrets are populated before writing anything to disk.

## Step 4 — configure Node A by hand (until Ansible coverage lands)

SSH into Node A and create `/etc/wireguard/shop0.conf`:

```ini
[Interface]
PrivateKey = <contents of node_a.key>
Address = 10.200.0.1/30
ListenPort = 51821
# A is the WG responder. No PersistentKeepalive on A — that property
# enforces the initiator direction documented in
# docs/SPLIT-HOP-TOPOLOGY.md.
PostUp = ip route add default dev shop0 table 200; ip rule add fwmark 0x1 table 200
PostDown = ip rule del fwmark 0x1 table 200 2>/dev/null; ip route flush table 200

[Peer]
PublicKey = <contents of node_b.key.pub>
PresharedKey = <contents of shared.psk>     # omit when no PSK
AllowedIPs = 0.0.0.0/0
# Do NOT set Endpoint here — Node A waits for B to handshake.
```

```bash
sudo install -o root -g root -m 0600 /dev/stdin /etc/wireguard/shop0.conf <<< "<the file above>"
sudo systemctl enable --now wg-quick@shop0.service
```

Direct Node A's egress through the tunnel via policy routing:

```bash
sudo iptables -t mangle -A OUTPUT -m owner --uid-owner xray  -j MARK --set-mark 0x1
sudo iptables -t mangle -A OUTPUT -m owner --uid-owner hysteria -j MARK --set-mark 0x1
sudo iptables -t mangle -A OUTPUT -m owner --uid-owner nginx -j MARK --set-mark 0x1
sudo netfilter-persistent save
```

(These rules will move into a future Ansible role; for the pilot we
write them by hand to keep the scope tight.)

## Step 5 — verify the tunnel

On Node B:

```bash
sudo wg show shop0
# Look for: latest handshake within the last minute, RX/TX counters
# rising, persistent-keepalive: 25 seconds.
```

On Node A:

```bash
sudo wg show shop0
# A should show: B's pubkey, no "endpoint" until the handshake
# completes (B's IP is whatever NAT it came from), persistent
# keepalive absent.
```

Test that A's xray egress now exits via B's public IP:

```bash
ssh root@<node-a-public-ip>
curl --interface shop0 -sS https://ifconfig.me
# Must return Node B's public IP, not Node A's.
```

## Step 6 — collect 24–72 h of flow data

The ADR's threat-model test (acceptance criterion #3) requires that
each node appears single-role in a flow record from an upstream
observer. Capture with the provider's flow logs if available
(UpCloud private interfaces support NetFlow; Hetzner does not), or
with `tcpdump` on a separate observation host bridged onto the
upstream side.

The classifier metric to compute:

```
RSS(IP) = (count of flows where IP is both inbound-receiver and
           outbound-initiator within a 5-min window)
          /
          (total flows involving IP in that window)
```

The FOCI 2026 threshold for relay-suspicion classification is RSS
> 0.5. After deploy, both Node A and Node B should sit RSS ≈ 0 — A
because it has no outbound flows the observer can see, B because it
has no client-inbound flows.

## Step 7 — publish the pilot results

Write up the flow-data results as
`docs/SPLIT-HOP-PILOT-<YYYY-MM-DD>.md` with:

- Per-node RSS over the observation window
- Latency added per hop (Node A → Node B → upstream)
- Operational cost (USD/mo for the two-VPS pair vs single-VPS)
- Recommendation on whether to promote split-hop from pilot to
  default-on for high-risk operators

Per the repo hard rules, do not name the operator, carrier, or
geography in the pilot writeup; describe by technical signature only.

## Tear-down

```bash
# Stop the tunnel
sudo systemctl disable --now wg-quick@shop0.service

# Re-disable on B
# (edit group_vars: vpn.enable_split_hop_egress: false; redeploy)

# On A, remove mangle rules
sudo iptables -t mangle -F OUTPUT
sudo netfilter-persistent save
```

The ephemeral VPSes can then be destroyed via `make destroy` per
their respective provider envs.
