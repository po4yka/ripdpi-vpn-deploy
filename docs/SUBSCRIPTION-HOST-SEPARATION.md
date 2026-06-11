# Subscription delivery host separation

The `subscription-host` role can run on the same VPS as the transport
(xray / hysteria / amneziawg) — that's the v1 default. For tighter
operator separation, run subscription on a dedicated VPS with no
transport surface at all. Closes the SUBSCRIPTION-PLANE.md gap
"Delivery host separate from VPN node".

## What gets separated

The dedicated host runs **only**:

  * `baseline`
  * `firewall` (port 8444 for /sub/ + bootstrap)
  * `subscription-host`
  * `monitoring` / `watchdog` / `backup` if you want them

It does NOT run:

  * `xray`, `geodata`, `nginx-xhttp`, `naive`
  * `hysteria`, `amneziawg`
  * `warp-outbound`, `honeypot`, `policy-ratelimit`

The transport VPS keeps every transport role, drops `subscription-host`
(or keeps it disabled).

## How site.yml decides

A new inventory variable `vpn_subscription_only` gates every
transport-class role. Set it on the subscription host's group / vars
in the inventory:

```ini
# ansible/inventory/generated.ini

[vpn-transport]
vpn-prod-01 ansible_host=…   # transport VPS

[vpn-subscription-only]
vpn-sub-01 ansible_host=…    # subscription VPS

[vpn-subscription-only:vars]
vpn_subscription_only=true
```

`site.yml` reads `vpn_subscription_only` on each host and:

  * skips every transport role for hosts where it's true
  * runs the subscription-host role unconditionally when it's true
    (regardless of `vpn.enable_subscription_host`)

The transport host plays exactly as it did before — no behaviour
change unless you explicitly set the var.

## Operator workflow

1. Provision two VPSes in separate Terraform roots or as two
   `upcloud_server` blocks in the same root (different `hostname`).
2. Tag them in the inventory as above.
3. Use the multi-operator SOPS split from `docs/MULTI-OPERATOR.md` so
   the subscription operator only decrypts `subscription.secrets.
   sops.yaml`. The transport operator sees only
   `prod.secrets.sops.yaml`.
4. Run `make deploy` against both — Ansible reads each host's
   `VPN_SECRETS_FILE` from its inventory variable and applies the
   right role subset.
5. Operators on `vpn-sub-01` can `make issue-bootstrap` without ever
   touching the REALITY private key.

## Bandwidth between hosts

The subscription host needs to fetch per-device payloads that the
transport host generates. Options:

  * Build the payload on the operator workstation (existing
    `emit-singbox.sh`) and scp to the subscription host via
    `issue-bootstrap.sh`. This is the v1 default and stays the
    simplest path.
  * For continuous-issuance scenarios, replicate
    `/var/lib/vpn-sub/` from a build worker via restic / rsync.
    Document the bandwidth + freshness trade-off; not automated in
    v1.

## What this does not buy you

  * Hiding the subscription host from a TSPU operator who already
    knows the transport host's IP. The subscription host is still a
    public HTTPS endpoint with its own IP, vulnerable to the same
    IP-reputation analysis as the transport.
  * Plausible deniability — both hosts share a fingerprint vector
    (operator's OPSEC, common ASN if not split, etc.).

What it does buy you is **operator-side blast radius**: a compromised
subscription operator's workstation doesn't expose the REALITY
private key or any transport credentials.
