# Multi-operator RBAC

> **Status:** Current · **Type:** how-to · **Tier:** TACTICAL · **Reviewed:** 2026-10-21

The v1 model assumes one operator (or one trusted operator-set sharing
the same age recipients). Larger deployments need finer separation:
the subscription-operator should not be able to decrypt the REALITY
private key; CI bots should not be able to decrypt the audit log;
staging-dev access should not extend to prod.

SOPS already supports this via per-file `creation_rules` in
`.sops.yaml`. This doc captures the discipline and shows the working
shape.

## The split

```
                      decrypt scope
─────────────────────  ───────────────────────────────────────────
operator (full fleet)  every *.sops.yaml + audit.log.age
staging-dev            staging.secrets.sops.yaml only
subscription-operator  subscription.secrets.sops.yaml only
CI bot (staging)       staging.secrets.sops.yaml only
```

The split is enforced by listing only the recipients allowed to
decrypt a given path. SOPS will refuse to decrypt for any other key.

## Schema layout

For the multi-operator split to be meaningful, separate the secrets
schema into per-scope files:

```
~/.config/vpn-provision/
  prod.secrets.sops.yaml          xray.* / hysteria.* / amneziawg_*
  subscription.secrets.sops.yaml  subscription.* / bootstrap tokens
  staging.secrets.sops.yaml       same shape as prod, staging cohort
  audit.log.age                   audit-log.sh writes here
```

The subscription-only file carries:

```yaml
subscription:
  port: 8444
  rate_limit: "5r/m"
  rate_burst: 3
  revoked_tokens: []
  enable_bootstrap: true
  bootstrap_dir: /var/lib/vpn-bootstrap
  ...
```

The transport-host file carries everything else. The Ansible play
loads the right file via VPN_SECRETS_FILE per host (see role-scoping
below). A subscription-host operator only ever decrypts the
subscription file.

## Setting it up

1. Each operator generates an age key (software via `age-keygen`, or
   hardware-backed via `scripts/setup-yubikey-age.sh`). Public
   recipient is shared with the central operator who curates
   `.sops.yaml`.
2. Copy `secrets/.sops.yaml.example` to
   `~/.config/vpn-provision/.sops.yaml` and replace the placeholders
   with real recipients per scope.
3. Re-encrypt existing blobs:
   ```bash
   for f in ~/.config/vpn-provision/*.sops.yaml; do sops updatekeys -y "$f"; done
   ```
4. Verify each operator can decrypt only what they should:
   ```bash
   # As subscription-operator with no prod recipient:
   sops --decrypt prod.secrets.sops.yaml          # MUST fail
   sops --decrypt subscription.secrets.sops.yaml  # MUST succeed
   ```

## Role scoping at deploy time

The full-stack site.yml expects one secrets file per host. Split it:

```yaml
# inventory/generated.ini  (rendered by render-inventory.sh)
[vpn-transport]
vpn-prod-01 ansible_host=… vpn_secrets_file=~/.config/vpn-provision/prod.secrets.yaml

[vpn-subscription]
vpn-sub-01 ansible_host=… vpn_secrets_file=~/.config/vpn-provision/subscription.secrets.yaml

[vpn-subscription:vars]
vpn_subscription_only=true
```

The play's role list checks `vpn_subscription_only` (group_vars/all)
and skips transport roles (xray, hysteria, amneziawg) when true. The
mechanism is documented in `docs/how-to/subscription-host-separation.md`.

## Audit boundaries

- The audit log is encrypted under the full-fleet recipient set. A
  subscription-operator emits records to it (via `audit-log.sh
  append`) but cannot read them back. This is intentional — append-
  only without read on the same operator is the standard audit
  pattern.
- Lost-recipient recovery: re-encrypt the audit log with the new
  recipient set the moment an operator leaves. `sops updatekeys -y
  ~/.config/vpn-provision/audit.log.age` does this in one shot.

## Hard rules

- NEVER commit a real `.sops.yaml` into this repo. The
  `secrets/.sops.yaml.example` file is the template; the live
  `.sops.yaml` lives at `~/.config/vpn-provision/.sops.yaml` on each
  operator's workstation.
- Audit the recipient list every time an operator's hardware token
  is replaced or a workstation is reprovisioned.
- When a recipient is removed, treat all data they had decrypt
  access to as "they may still have a plaintext copy on disk" —
  rotate per docs/reference/secrets.md.
