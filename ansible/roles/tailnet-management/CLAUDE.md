# role: tailnet-management — restricted ordinary OpenSSH overlay

## Design decisions

**Ordinary OpenSSH only** — Tailscale SSH stays disabled. Existing host keys,
authentication and the single effective sshd port remain authoritative.

**No DNS, route or firewall ownership** — enrollment sets accept-dns/routes,
advertised routes, exit-node use and Tailscale netfilter management off. The
firewall role owns exact `tailscale0` SSH source rules.

**Bootstrap owns first enrollment** — ordinary `tasks/main.yml` only verifies
existing access and rejects enrollment keys. The dedicated bootstrap playbook
uses `tasks/bootstrap.yml` to install inert components. The controller sends
its key only in the guest transaction RPC on strict SSH stdin; Ansible never
receives it. The guest keeps the temporary auth file private and removes it.

**One transaction, two recovery phases** — the early worker restores firewall
without tailscaled or service activation; the late worker completes owned
identity logout and service reconciliation. Both use the same private lock and
journal. `rolling_back` and `firewall_restored` forbid later confirmation.
Early recovery gates `ssh.socket`; late recovery gates only `ssh.service`,
so socket activation cannot cycle through `basic.target` and tailscaled.
Confirmed recovery never logs out a committed node. Installation and runtime
acceptance for this bootstrap change remain in progress; see
`SEC-1788894219568782` before deployment.

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
- `netfilter-mode=off` requires the bootstrap firewall foundation before login
  and exact approved source addresses during ordinary firewall convergence.
- Validate the complete boot graph, including `basic.target` and `ssh.socket`.
  A late service before the socket can cycle through `sockets.target`;
  systemd-analyze may remove a job and return 0, so inspect diagnostics too.
- Real tailscaled startup creates empty ip/ip6 filter/nat tables before
  login. Only that exact object-free quartet qualifies as inert; preserve it
  in snapshots and replay without accepting foreign chains, sets or rules.
- Recovery's address-family sandbox can reorder sshd's IPv4/IPv6 listener
  output. Normalize only listenaddress enumeration, preserving values and
  multiplicity; never sort the whole policy or weaken its validation.
- Recovery state is root-owned mode `0700`/`0600`; an unsafe lock, receipt,
  snapshot or generation refuses without guessing or deleting evidence.
- Local or Molecule success does not prove the Tailnet path, host identity or
  public emergency path on staging or production.
