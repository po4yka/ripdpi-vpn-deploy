# role: tailnet-management — restricted ordinary OpenSSH overlay

## Design decisions

**Ordinary OpenSSH only** — Tailscale SSH stays disabled. Existing host keys,
authentication and the single effective sshd port remain authoritative.

**No DNS, route or firewall ownership** — enrollment sets accept-dns/routes,
advertised routes, exit-node use and Tailscale netfilter management off. The
firewall role owns exact `tailscale0` SSH source rules.

**Ephemeral enrollment capability** — `TAILSCALE_AUTH_KEY` is accepted only on
Ansible stdin, written to a root-owned mode-0600 file in the dedicated
`/run/vpn-tailnet-management` directory, and removed after the bounded login
attempt. The recovery unit preserves the same volatile runtime directory across
timer runs so a busy recovery cannot remove another controller's key. The key
never belongs in inventory or SOPS, and an already enrolled host receives empty
stdin even when an ambient key still exists.

**Durable unconfirmed enrollment recovery** — a private transaction is fsynced
before `tailscale login`; the controller first executes the sandboxed worker as
a readiness proof. A persistent timer serializes on the same lock, while a
required boot unit reconciles after `tailscaled` and before the ordinary SSH
listener starts. Lock contention is a boot-gate failure, not a successful
recovery exit. The fresh worker result is revalidated under the controller lock
immediately before the receipt is armed. Any confirmation-directory fsync
ambiguity reports failure rather than treating page-cache bytes as a durable
commit.

## What's done well

- Exact stable package and repository key pins fail closed.
- Existing running nodes with different preferences are refused without writes.
- Resolver bytes, default route and full `sshd -T` policy are compared across
  fresh enrollment; a failed postcondition logs the new node out.
- Armed and confirmed transaction phases make process death unambiguous: only
  an armed receipt authorizes logout, while confirmed recovery is cleanup-only.

## Pitfalls

- `tailscale get --json all` represents no advertised routes as the empty
  string, not an array. Both the existing-node guard and enrollment verifier
  must reject arrays, null and nonempty route strings.
- This role does not edit Tailnet ACLs. ACL review and application are a
  separate controller-side action requiring a fresh approved policy diff.
- `netfilter-mode=off` means the firewall role must run first and retain the
  exact approved source addresses.
- Recovery state is root-owned mode `0700`/`0600`; an unsafe lock, receipt,
  snapshot or generation refuses without guessing or deleting evidence.
- Local or Molecule success does not prove the Tailnet path, host identity or
  public emergency path on staging or production.
