# role: tailnet-management — restricted ordinary OpenSSH overlay

## Design decisions

**Ordinary OpenSSH only** — Tailscale SSH stays disabled. Existing host keys,
authentication and the single effective sshd port remain authoritative.

**No DNS, route or firewall ownership** — enrollment sets accept-dns/routes,
advertised routes, exit-node use and Tailscale netfilter management off. The
firewall role owns exact `tailscale0` SSH source rules.

**Ephemeral enrollment capability** — `TAILSCALE_AUTH_KEY` is accepted only on
Ansible stdin, written to a root-owned mode-0600 file in `/run`, and removed
after the bounded login attempt. It never belongs in inventory or SOPS.

**Durable unconfirmed enrollment recovery** — a private transaction is fsynced
before `tailscale login`; a persistent systemd timer serializes on the same
lock and logs out any unconfirmed enrollment after controller loss or reboot.

## What's done well

- Exact stable package and repository key pins fail closed.
- Existing running nodes with different preferences are refused without writes.
- Resolver bytes, default route and full `sshd -T` policy are compared across
  fresh enrollment; a failed postcondition logs the new node out.
- Armed and confirmed transaction phases make process death unambiguous: only
  an armed receipt authorizes logout, while confirmed recovery is cleanup-only.

## Pitfalls

- This role does not edit Tailnet ACLs. ACL review and application are a
  separate controller-side action requiring a fresh approved policy diff.
- `netfilter-mode=off` means the firewall role must run first and retain the
  exact approved source addresses.
- Recovery state is root-owned mode `0700`/`0600`; an unsafe lock, receipt,
  snapshot or generation refuses without guessing or deleting evidence.
- Local or Molecule success does not prove the Tailnet path, host identity or
  public emergency path on staging or production.
