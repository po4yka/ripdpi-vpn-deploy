# role: security_audit — non-blocking host audit reports

## Design decisions

**Operator-run only** — this role is called by `security-audit.yml`, not `site.yml`. It must never become a deploy or verify blocker by default.

**Reports over enforcement** — command failures and findings are written under `/var/log/ripdpi-vpn-deploy/security-audit/<timestamp>/` with `failed_when: false`. Only `security_audit.fail_on_high_findings` may intentionally convert a finding into failure.

**Heavy scanners stay off** — AIDE, rkhunter, and ClamAV are documented as deferred controls. Do not install or enable them without a separate reviewed implementation.

## What's done well

- Lynis is the only package installed by default, and only for this explicit audit playbook.
- The role collects the current host state without modifying service configs.
- Reports are root-readable by default and avoid secrets-bearing files.

## Pitfalls

- `ss -tulpn`, `nft list ruleset`, and `sshd -T` can expose local topology and process names; keep report permissions at `0640`.
- Do not add decrypted SOPS content, client config files, private keys, subscription URLs, or token logs to report output.
- Keep this role out of `site.yml`; mandatory security gates belong in `security-verify.yml`, not here.
