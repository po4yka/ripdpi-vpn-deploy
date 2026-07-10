# Runbook — credential rotation

Three rotation scopes. Pick the smallest one that addresses the threat.

Infrastructure rotation caused by sustained protocol failure is separate from credential rotation. Follow `docs/PROTOCOL-LIVENESS.md`: only fresh authenticated client-path failures with a successful direct control can create a quorum candidate, and the resulting OTP still enters the normal blue-green verification and operator-confirmation flow.

## 1. Single client leak

A device was lost / stolen / decommissioned, or one client URI showed up
where it shouldn't.

```bash
# Edit the encrypted secrets file
sops ~/.config/vpn-provision/prod.secrets.sops.yaml
```

Remove the leaked client from:

- `xray.clients[*]` (matching `name`)
- `hysteria.clients[*]` (matching `name`)
- `amneziawg_secrets.peers[*]` (matching `name`)

Save and exit (sops re-encrypts automatically). Then:

```bash
make decrypt
make rotate-credentials      # re-renders configs, reloads services
make verify
make clean
```

Other clients are unaffected. The dropped client now gets `403`/`reset` /
`Authentication failure` on every transport.

## 2. Server-wide REALITY keypair

Use when the REALITY private key is suspected leaked, or you want to
invalidate every existing client URI in one move.

```bash
# Generate new REALITY keypair
docker run --rm ghcr.io/xtls/xray-core x25519
# or: xray x25519

# Update secrets
sops ~/.config/vpn-provision/prod.secrets.sops.yaml
# Replace xray.reality_private_key and xray.reality_public_key

# Optionally regenerate every client's shortId (good hygiene with this rotation)
sops ~/.config/vpn-provision/prod.secrets.sops.yaml
# For each xray.clients[*], replace short_id with `openssl rand -hex 4`

make decrypt
make deploy                  # full deploy — REALITY change is server-wide
make verify
make clean
```

Every existing client URI is now invalid. Reissue URIs to every device
through `scripts/new-client.sh --emit-uri <name>` (the script reads the
new public key from secrets) and redistribute.

## 3. Hysteria server-wide / AmneziaWG server-wide

If the Hysteria server password format or AWG server private key leaks,
rotate similarly: generate new server-side material, update secrets, run
`make deploy`. AWG client public keys remain valid (only the server
private key changed); Hysteria per-user passwords remain valid when only the server certificate or canonical `hysteria.obfs_password` changes. Rotate the obfuscation password only as a synchronized server-and-bundle cutover, retain the previous configuration and bundle for rollback, and confirm every target device has imported the replacement before removing the old material.

## 4. Restic password

`backup.restic_password` rotation is destructive — old snapshots become
unreadable. Procedure:

```bash
# Take a fresh full backup under the OLD password
ssh deploy@<vps> sudo systemctl start vpn-backup.service

# Gate deletion on a real isolated restore from the selected repository
ssh deploy@<vps> sudo systemctl start vpn-backup-restore-drill.service
ssh deploy@<vps> sudo python3 -m json.tool /var/lib/vpn-backup/restore-drill-last-success.json

# Generate new password
openssl rand -base64 32

# Update secrets
sops ~/.config/vpn-provision/prod.secrets.sops.yaml

# On the server: re-init the restic repo with the new password
ssh deploy@<vps>
sudo rm -rf /var/backups/vpn-restic
exit

# Run the role; it will re-init and take the first new snapshot
make decrypt
make deploy
make verify
make clean

# Take the first snapshot under the NEW password and verify it by real restore
ssh deploy@<vps> sudo systemctl start vpn-backup.service
ssh deploy@<vps> sudo systemctl start vpn-backup-restore-drill.service
ssh deploy@<vps> sudo python3 -m json.tool /var/lib/vpn-backup/restore-drill-last-success.json

# Discard the old password ONLY after the new restore drill succeeds.
```

## 5. SSH key for the deploy user

If the operator workstation is compromised:

```bash
# Generate a new key
ssh-keygen -t ed25519 -f ~/.ssh/vpn_deploy_new -N '' -C 'vpn-deploy operator'

# Edit tfvars to put the new public key in admin_ssh_public_key
$EDITOR terraform/providers/upcloud/environments/prod.tfvars

# cloud-init.user_data is ignored by lifecycle, so the new key won't apply
# automatically. Instead, push it via Ansible by adding a temporary one-off
# task — or, faster, SSH in once with the OLD key and run:
ssh-copy-id -i ~/.ssh/vpn_deploy_new.pub deploy@<vps>

# Then revoke the old key on the server
ssh -i ~/.ssh/vpn_deploy_new deploy@<vps>
$EDITOR ~/.ssh/authorized_keys   # remove the old key line
exit

# From now on, use the new key
export ANSIBLE_SSH_PRIVATE_KEY_FILE=~/.ssh/vpn_deploy_new
shred -u ~/.ssh/vpn_deploy
```

If you've truly lost the old key (no remaining SSH access), see
`RUNBOOK-incident.md` § "lost SSH access".

## What to NOT do during rotation

- Don't reuse a UUID, shortId, peer keypair, or password. Always generate
  fresh.
- Don't keep the previous secrets file around as a "backup". The encrypted
  blob in your SOPS file IS the only durable copy; rotation overwrites it.
- Don't leave the old client entry in secrets and just disable on the
  server. The server is the only enforcement point — secrets are a record
  of what should be enforced. Mismatch breaks rotation hygiene.
