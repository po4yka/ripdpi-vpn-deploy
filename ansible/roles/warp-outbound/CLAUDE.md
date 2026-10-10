# role: warp-outbound — isolated vendor tunnel backend

## Design decisions

One exact stable vendor package and the canonical `warp-svc.service` own retained registration state. The role never registers an account. A private bounded ownership record claims only the canonical vendor unit and one namespace/veth pair; foreign units, drop-ins or namespace authority refuse before mutation.

The vendor runs in `tunnel_only` inside `ripdpi-warp`, with its private numeric resolver and host bus inaccessible. Package installation suppresses both maintainer-script and direct systemd autostart before namespace guard publication. Host management routing and DNS remain outside the namespace.

Recipient WARP traffic uses a distinct native gateway identity. Namespace policy admits only the verified current UP TUN ifindex; underlay fallback remains denied. TUN replacement updates host and namespace policy together and resets the paired recipient generation. Retirement preserves the vendor package and registration state.

## What's done well

- Namespace ownership uses recorded inode and exact veth ifindices; no broad interface or process cleanup occurs.
- Readiness checks actual kernel TUN kind, type and state, rather than vendor status text alone.
- The exact signing-key checksum and stable package identity remain mandatory.

## Pitfalls

- No local fixture proves registered vendor TCP/UDP capability. Real registered tunnel acceptance requires separately authorized vendor account and client evidence.
- Vendor root authority is isolated because tunnel management requires network administration. Recipient gateway and normalizer processes retain empty capabilities.
- A pinned package upgrade must not start the vendor outside its namespace or bypass guard publication.
- Registration output may contain private identity details; CLI tasks stay under `no_log`.
- The public package version comes from inventory or group vars, not SOPS. Same-pin redesign and fresh install are supported; a claimed different package identity refuses before mutation until its separate upgrade transaction is accepted.
- Molecule exercises the actual namespace/veth/TUN lifecycle and recovery. It deliberately creates no vendor registration and provides no registered vendor traffic claim.
- The isolated vendor backend requires actual systemd 257 or newer before mutation. Older managers are unsupported because ignoring PrivatePIDs would expose host process authority; direct/normalizer operation does not inherit this vendor-only version floor.

- Vendor admission reads only the canonical unit through one comma-separated property selector under `no_log`; extra positional property names would be interpreted as unrelated units and can falsely supply `LoadState=not-found`. Molecule requires actual unclaimed-unit refusal before ownership mutation.

- Partial-install retirement reads exact current lifecycle unit metadata and skips only actual `not-found` units. Existing units must have canonical owned fragments; namespace removal still requires an empty actual process set.
- Resolver comparison and publication consume one canonical rendered byte string, with each numeric nameserver and the options on separate lines. Identical input must compare unchanged; joining directives onto one line both changes resolver behavior and needlessly quiesces the accepted route.
