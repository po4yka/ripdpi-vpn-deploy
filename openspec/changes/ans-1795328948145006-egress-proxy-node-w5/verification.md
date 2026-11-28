---
task_id: ANS-1795328948145006
change: ans-1795328948145006-egress-proxy-node-w5
commit_sha: 8c0f207ef3bc094b84e2b44ea135becf35645ec6
local: passed
local_evidence: "At 8c0f207ef: pytest over tests/unit/test_egress_proxy*.py, test_sshd_ownership.py, test_resolver_roundtrip.py, test_fleet_inspection*.py and test_bootstrap_tailnet*.py, 367 passed; make tf-test passed (egress-proxy root 3 passed, native provider lifecycle 24 passed); make tf-policy-verify 101 of 101 passed. The egress-proxy Molecule scenario (method, port, host and IP-literal denials, exposure floor 3.0) ran in the PR CI of the role (step ANS-1795329034006860)."
remote_ci: passed
remote_ci_evidence: "Owner decision on 2026-11-28: po4yka/ripdpi-vpn-deploy ci run 46141602707 on main at 8c0f207ef concluded failure, but every W5 job passed: molecule (firewall monitoring split-hop-egress package_updates egress-proxy), tofu fmt + validate and tofu test for egress-proxy, hetzner, upcloud, vultr and scaleway, tf-policy / conftest, and pytest groups 1-4 with the pytest unit tests aggregate. The failing jobs are not W5's: native runtime integration 2-4 and native four-transport acceptance fail since f9c0988a3 (client IPv4 rotation), and contract-sync plus the two observability-kuma image scans failed before W5 (af80c8a00 and earlier)."
dry_run: passed
dry_run_evidence: "On 2026-11-28, egress playbook --check over the Tailnet at 964c12b63: failed=0, 24 planned changes (kit log egress-proxy-dryrun-5-20261128.log); migrate-ssh-ownership check mode: would-change (egress-proxy-ssh-ownership-check-20261128.log)."
staging: not_applicable
staging_evidence: "Owner decision on 2026-11-28: staging evidence moves to CIC-1795329226354380 (W7), whose CI-driven staging plans run through the egress proxy as tag:ci-tofu (mapping below). The W5 provider proof was read-only plans with no resource mutation, so a staging-first run added no distinct risk over the passed live proof; the egress node is a single production node with no staging counterpart."
live: passed
live_evidence: "2026-11-28 on the production egress node: server recreated on the retained IPv4 (server-only destroy and apply), host key verified against the provider console, Tailnet bootstrap configured with a signed tag:egress key, migrate-ssh-ownership committed, converge failed=0 and rerun changed=0 (kit receipt w5-egress-deploy-20261128.json); five provider plans and the state backend through the proxy with squid CONNECT to each host, Vultr access list holding only the egress /32 with a direct call 401 and a proxied call 200 (ops receipts/egress-proxy-w5-20261128/provider-proof.json); stopped-service drill and lost-server recovery (ops receipts/egress-proxy-w5-20261128/break-glass.json)."
client: not_applicable
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-EGRESS-CONNECT-ONLY | ANS-1795329034006860 | Molecule denial tests including IPv4/IPv6 literals with allowlisted PTR names: Molecule egress-proxy scenario in protected-main ci run 46139360314 at 3887e5617 (success; the role is unchanged at 8c0f207ef); live: non-listed host and IP literal refused at CONNECT with 403, plain HTTP 403 | passed 2026-11-28 |
| REQ-EGRESS-TAILNET-ONLY | ANS-1795329045195870 | public scan negative and tag:ci-deploy negative receipts: TCP 3128, 22, 80 and 443 on the public IPv4 closed from the operator network at 2026-11-28T11:58Z; Tailnet policy tests deny tag:ci-deploy to tag:egress:3128 (ops tailnet-policy run 46012837542, success) | passed 2026-11-28 |
| REQ-EGRESS-SECRETLESS | ANS-1795329034006860 | Molecule file audit: Molecule egress-proxy scenario in protected-main ci run 46139360314 at 3887e5617 (success; the role is unchanged at 8c0f207ef); the converge takes no SOPS input (extra vars hold only admin public keys, the SSH placeholder, approved sources and the state host) | passed 2026-11-28 |
| REQ-EGRESS-HARDENED | ANS-1795329034006860 | Molecule `systemd-analyze security` score at or below the 3.0 floor: Molecule egress-proxy scenario in protected-main ci run 46139360314 at 3887e5617 (success; the role is unchanged at 8c0f207ef) | passed 2026-11-28 |
| REQ-EGRESS-FIXED-ADDRESS | ANS-1795329022845451 | `tofu test` replacement case (make tf-test at 8c0f207ef, egress-proxy root 3 passed); recreation on 2026-11-28 kept the retained primary IPv4 and the Vultr access list stayed valid | passed 2026-11-28 |
| REQ-EGRESS-PROVIDER-PROOF | ANS-1795329056411801 | proxy log per provider in the ops repository receipt (`receipts/egress-proxy-w5-20261128/provider-proof.json`): five plans through the proxy, CONNECT to every provider host and the state host | passed 2026-11-28 |
| REQ-EGRESS-ALLOWLISTS | ANS-1795329068636739 | Vultr direct-call negative receipt (same file): access list holds only the egress `/32`; direct call 401, proxied call 200 | passed 2026-11-28 |
| REQ-EGRESS-BREAK-GLASS | ANS-1795329082564404 | Stopped-service SSH repair and lost-server direct bootstrap with retained address and backend lock: ops receipt `receipts/egress-proxy-w5-20261128/break-glass.json` (stopped-service drill; lost-server path run as a real recovery; temporary Vultr entry documented, not exercised) | passed 2026-11-28 |

## Shared operational evidence ownership

| Source task | Operational owner | Requirement | Acceptance command | Evidence category | Source revision |
|---|---|---|---|---|---|
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-CONNECT-ONLY | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-TAILNET-ONLY | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-SECRETLESS | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-HARDENED | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-FIXED-ADDRESS | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-PROVIDER-PROOF | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-ALLOWLISTS | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
| ANS-1795328948145006 | CIC-1795329226354380 | REQ-EGRESS-BREAK-GLASS | `make plan ENV=staging` | staging | 8c0f207ef3bc094b84e2b44ea135becf35645ec6 |
