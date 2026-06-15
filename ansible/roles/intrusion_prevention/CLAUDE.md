# role: intrusion_prevention — opt-in sshd ban layer

## Design decisions

**Fail2Ban first, sshd only** — the role installs and configures Fail2Ban for the sshd jail only. CrowdSec is represented only by future/off defaults; no repository setup or installer is present.

**Firewall remains the nftables owner** — the firewall role renders the `f2b_sshd4` / `f2b_sshd6` sets and input-chain drops when `security_controls.fail2ban` is true. This role only keeps Fail2Ban's action pointed at those sets.

**Allowed SSH CIDRs are never bannable** — `allowed_ssh_cidrs` is merged into Fail2Ban `ignoreip` with `intrusion_prevention.ignore_cidrs`.

## What's done well

- **Default-off at site level** — `site.yml` runs the role only behind `security_controls.fail2ban`.
- **nftables-native action** — bans are set membership updates, not UFW or replacement firewall rules.
- **IPv4 and IPv6 are separate** — the action updates `f2b_sshd4` and `f2b_sshd6` so dual-stack sshd logs do not make one address family fail the other.

## Pitfalls

- **Run firewall before this role** — the action assumes the `inet filter` table and input-chain drop rules are managed by the firewall template.
- **Do not broaden jail scope casually** — transport logs have different privacy and NAT-pool risks; add a separate design note before watching anything beyond sshd.
- **CrowdSec is future-only here** — do not add package repositories, enrollments, or `curl | sh` installers without a separate review.
