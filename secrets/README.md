# secrets/

**Real secrets never live in Git.** The default operator layout is external,
under `~/.config/vpn-provision/`, encrypted with SOPS + age. This repository
also supports `secrets/local/` for git-ignored, checkout-local operator state.

This directory only holds:

- `prod.secrets.example.yaml` — placeholder structure showing every field the
  Ansible roles will look up. Copy it to `~/.config/vpn-provision/prod.secrets.yaml`,
  fill in real values, then `sops --encrypt` it.
- This README.

The `.gitignore` excludes everything else under `secrets/` to make accidental
commits hard. Treat ignored files as sensitive anyway: directories mode 0700,
files mode 0600, and plaintext runtime files removed with `make clean`.

## Workflow

```bash
mkdir -p ~/.config/vpn-provision
cp secrets/prod.secrets.example.yaml ~/.config/vpn-provision/prod.secrets.yaml

# Generate an age keypair (one-time)
age-keygen -o ~/.config/vpn-provision/age.key
# Public recipient is printed at the top of age.key (line "# public key: age1...")
RECIPIENT=$(grep '^# public key:' ~/.config/vpn-provision/age.key | awk '{print $4}')

# Edit ~/.config/vpn-provision/prod.secrets.yaml in your editor.

# Encrypt
sops --encrypt --age "$RECIPIENT" \
  ~/.config/vpn-provision/prod.secrets.yaml \
  > ~/.config/vpn-provision/prod.secrets.sops.yaml

# Wipe plaintext
shred -u ~/.config/vpn-provision/prod.secrets.yaml || rm -f ~/.config/vpn-provision/prod.secrets.yaml
```

For day-to-day editing of an already-encrypted file, use `sops <file>` —
it decrypts to a temp file, opens your $EDITOR, re-encrypts on save, and
never writes plaintext to disk.

See `docs/SECRETS.md` for the full lifecycle, recovery, and rotation
procedure.

## Optional checkout-local layout

```text
secrets/local/config/   # age identity and encrypted SOPS files
secrets/local/runtime/  # temporary decrypted secrets
secrets/local/clients/  # generated client profiles and QR artifacts
```

Point the ignored `.fleet.mk` at the encrypted and runtime files as documented
in `docs/SECRETS.md`. Never use `git add -f` for this tree.
