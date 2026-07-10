# Secrets — SOPS + age model

## Where things live

```
~/.config/vpn-provision/
  age.key                                # private age key (operator-only, mode 0600)
  prod.secrets.yaml                      # plaintext, EXISTS ONLY MOMENTARILY
  prod.secrets.sops.yaml                 # encrypted, the only durable copy
  staging.secrets.sops.yaml              # same shape, staging environment

vpn-deploy/secrets/
  prod.secrets.example.yaml              # placeholder schema only
```

The only thing in this repo's `secrets/` directory is the example schema
and a README. Real secrets never enter the repo, Terraform state,
Terraform outputs, cloud-init user_data, or any debug log.

## age recipients

```bash
# One-time bootstrap
age-keygen -o ~/.config/vpn-provision/age.key
chmod 0600 ~/.config/vpn-provision/age.key
grep '^# public key:' ~/.config/vpn-provision/age.key | awk '{print $4}'
# → age1xyz…  (this is your "recipient")
```

### Hardware-backed age (YubiKey PIV applet)

For high-value operator workstations, replace the software age key
with a YubiKey-backed identity via the `age-plugin-yubikey` plugin.
The encrypted SOPS blob stays useless to anyone without physical
access to the YubiKey, even if they have the file.

```bash
scripts/setup-yubikey-age.sh              # generate + print recipient
scripts/setup-yubikey-age.sh --reencrypt  # also `sops updatekeys` every blob
```

Migration discipline:

1. Generate the YubiKey identity and add its recipient as a SECOND
   recipient on every SOPS blob — do not yet remove the software
   recipient.
2. Verify decryption from `SOPS_AGE_KEY_FILE=…yubikey-identity.txt`
   on every operator workstation that needs it.
3. Once verified everywhere, remove the software recipient via
   `sops updatekeys` per blob. Skipping step 2 means losing access
   the moment the software key is rotated out.

`scripts/setup-yubikey-age.sh` does steps 1 and 3 explicitly; step
2 (verification) is left to the operator because failure modes are
human-specific (forgot the PIN, slot wasn't the one expected, etc.).

Encrypt against one or more recipients (multiple operators):

```bash
sops --encrypt \
  --age age1aaa…,age1bbb… \
  ~/.config/vpn-provision/prod.secrets.yaml \
  > ~/.config/vpn-provision/prod.secrets.sops.yaml
```

The recipient list is also stored at `.sops.yaml` if you have one — the
runtime needs only **the private key matching one of the recipients** to
decrypt.

## Day-to-day operations

| Action | Command |
|---|---|
| Edit existing secrets | `sops ~/.config/vpn-provision/prod.secrets.sops.yaml` |
| Add a new client | `SOPS_FILE=~/.config/vpn-provision/prod.secrets.sops.yaml ./scripts/new-client.sh laptop` |
| Re-encrypt under a new recipient | `sops updatekeys ~/.config/vpn-provision/prod.secrets.sops.yaml` |
| Decrypt for deploy | `make decrypt` (writes `/tmp/vpn-prod.secrets.yaml` mode 0600) |
| Wipe plaintext | `make clean` (shred or rm) |

`sops <file>` opens your `$EDITOR` against a temp plaintext file in `/tmp`
with mode 0600, re-encrypts on save, and deletes the plaintext. It never
writes plaintext to a path you can `cat` later.

## What's in the secrets file

See `secrets/prod.secrets.example.yaml` for the full schema. High-level:

```
xray.{version, linux_*_sha256, reality_*, target, server_names, xhttp_path, clients[*]}
nginx_xhttp.{server_name, cert_pem, key_pem}
hysteria.{version, linux_*_sha256, cert_pem, key_pem, bandwidth_*, salamander_*, clients[*]}
geodata.{geosite_url, geoip_url, geosite_sha256, geoip_sha256, install_dir, refresh_interval}
amneziawg_go_version + amneziawg_go_commit / amneziawg_tools_version + amneziawg_tools_commit
amneziawg_secrets.{server_private_key, jc/jmin/jmax/s1/s2/h1-h4, peers[*]}
backup.restic_password
subscription.{port, server_name}     # optional
```

## Rotation

Three rotation scopes:

1. **Per-client** (one device leaks): regenerate that one client's
   `uuid`+`shortId` (Xray), password (Hysteria), or peer keypair (AWG).
   Use `scripts/new-client.sh` to add the replacement, edit secrets to
   remove the old entry, then `make rotate-credentials`.
2. **Server-wide REALITY keypair**: regenerate via `xray x25519`, update
   `xray.reality_private_key` + `xray.reality_public_key`, redistribute
   the new public key + shortIds to clients, run `make deploy`. All
   clients must reissue.
3. **Restic password**: regenerate `backup.restic_password`. Existing
   restic snapshots become unrecoverable — keep the OLD password until
   you've taken a fresh snapshot under the new one and verified restore.

See `RUNBOOK-rotate.md` for full procedures.

## Recovery — what to do when…

### Lost the age private key

Without it you cannot decrypt the SOPS file. Three options:

1. You encrypted to multiple recipients → use the other operator's age key.
2. You backed up the age key out of band → restore it.
3. Neither → all secrets are unrecoverable. Treat this as a **complete
   credential leak** (assume an attacker may possess the encrypted blob
   forever, even if computationally hard today). Rotate every credential:
   provision a new VPS, generate fresh REALITY keypair, fresh per-client
   UUIDs/passwords/peer keys, fresh restic password. Migrate clients.

### Plaintext secrets file leaked to disk

`shred -u` the file. If shred is not available (some filesystems don't
support it), `rm` and overwrite the free space. Treat the secrets as
compromised and rotate per the per-server rotation above.

### Operator workstation lost

If the age private key was in `~/.config/vpn-provision/age.key`, treat as
"lost the age key" plus the SSH private key. Add: rotate SSH access on
the VPS (`make deploy` with a new `admin_ssh_public_key` in tfvars), and
if Terraform state was on that workstation, see `RUNBOOK-incident.md` §
"State loss".

## Hard rules

- Never `cat` a decrypted secrets file into the terminal.
- Never paste secrets into GitHub issues, PRs, Slack, or Discord.
- Never run `ansible-playbook -vvv` against a host with secrets in scope —
  `-vvv` can dump task vars. Use `--diff` only on roles that mark
  templates `no_log: true, diff: false` (the templates here do).
- The `.gitleaks.toml` ruleset must pass on every commit. `make validate`
  enforces this locally; CI enforces it on push.
