# Plan 014: Rewrite the split-hop runbook around the shipped ingress role

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, do not edit `plans/README.md`; the reviewer maintains the plan index in the advisory checkout.
>
> **Drift check (run first)**: `git diff --stat 7bdba37..HEAD -- docs/RUNBOOK-split-hop-pilot.md docs/SPLIT-HOP-TOPOLOGY.md tests/unit/test_probe_matrix_provisioning.py`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: MED
- **Depends on**: none
- **Category**: docs
- **Planned at**: commit `7bdba37`, 2026-07-11

## Why this matters

The split-hop pilot runbook still tells operators that Node A lacks Ansible coverage, stores its private key outside SOPS, and must be configured with a hand-written WireGuard file plus persistent iptables rules. The repository now ships a fail-closed `split-hop-ingress` role that owns the responder configuration and conntrack-marked nftables policy. Following the stale procedure bypasses the declared secret schema, omits the research-role allowlist, marks the wrong service users, and leaves unmanaged state behind. Make the runbook describe the code that actually deploys the topology and add a narrow repository contract so this exact drift cannot recur silently.

## Current state

- `docs/RUNBOOK-split-hop-pilot.md:3-6` says Node A does not have full Ansible coverage.
- `docs/RUNBOOK-split-hop-pilot.md:29-40` maps only Node B's private material into SOPS and explicitly says Node A's private key has "no SOPS yet".
- `docs/RUNBOOK-split-hop-pilot.md:51-83` configures only Node B declaratively and omits the required `allow_research_roles` entry for the ingress role.
- `docs/RUNBOOK-split-hop-pilot.md:85-125` instructs operators to hand-write `/etc/wireguard/shop0.conf`, start `wg-quick`, and append owner-matching iptables rules for xray, hysteria, and nginx.
- `docs/RUNBOOK-split-hop-pilot.md:194-205` tears down the unmanaged Node A state manually and disables only the Node B toggle.
- `ansible/roles/split-hop-ingress/defaults/main.yml` defines the responder interface, listen port, tunnel addresses, routing table, and mark, with `split_hop_ingress_secrets.{node_a_private_key,node_b_public_key,preshared_key}`.
- `ansible/roles/split-hop-ingress/tasks/main.yml` asserts the required keys, renders `/etc/wireguard/split-hop-ingress.nft` and `/etc/wireguard/shop0.conf`, and manages `wg-quick@shop0`.
- `ansible/roles/split-hop-ingress/templates/policy.nft.j2` marks only new original-direction connections owned by the repository's declared Xray and MTG runtime UIDs, then restores the packet mark from conntrack state.
- `ansible/roles/split-hop-ingress/templates/split-hop-ingress.conf.j2` deliberately contains no peer `Endpoint` or `PersistentKeepalive`; Node B remains the initiator.
- `ansible/roles/split-hop-egress/defaults/main.yml` and its template own Node B's initiator endpoint, keepalive, forwarding interface, and peer material.
- `secrets/prod.secrets.example.yaml:295-312` documents separate SOPS blocks for Node B and Node A, and `secrets/schema.json:372-390` accepts both shapes.
- `ansible/group_vars/all.yml:67-77`, `ansible/role-tiers.yml`, and `ansible/playbooks/site.yml:259-265` expose separate toggles; `split-hop-ingress` is RESEARCH-tier and requires explicit host allowlisting.
- `tests/unit/test_probe_matrix_provisioning.py` already owns the static split-hop provisioning contracts. Extend its existing ingress-direction test rather than adding another test file or function.
- `docs/SPLIT-HOP-TOPOLOGY.md` correctly describes Node B as initiator but its pilot procedure mentions only `split_hop_egress_secrets`, says Node A uses the standard cohort without naming the ingress toggle/allowlist, and suggests `curl --interface awg0` instead of the shipped `shop0` interface.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Drift check | command in the plan header | no output |
| Focused static contract | `mise exec --no-deps -- python3 -m pytest tests/unit/test_probe_matrix_provisioning.py -q` | all tests in the file pass with unchanged collection count |
| Stale procedure scan | `rg -n 'does not yet have full Ansible coverage|no SOPS yet|configure Node A by hand|until Ansible coverage lands|iptables|netfilter-persistent|curl --interface awg0|future Ansible role' docs/RUNBOOK-split-hop-pilot.md docs/SPLIT-HOP-TOPOLOGY.md` | no output |
| Required declarative terms | `rg -n 'split_hop_ingress_secrets|enable_split_hop_ingress|allow_research_roles|split-hop-ingress|shop0' docs/RUNBOOK-split-hop-pilot.md docs/SPLIT-HOP-TOPOLOGY.md` | each contract appears in the relevant operator procedure; inspect matches |
| Ingress Molecule | `DOCKER_HOST=unix:///Users/po4yka/.docker/run/docker.sock mise exec -- make molecule-test ROLE=split-hop-ingress` | converge, idempotence, and verify pass |
| Egress Molecule | `DOCKER_HOST=unix:///Users/po4yka/.docker/run/docker.sock mise exec -- make molecule-test ROLE=split-hop-egress` | converge, idempotence, and verify pass |
| Full unit regression | `mise exec --no-deps -- python3 -m pytest tests/unit/ -q` | all unit tests pass with unchanged collection count |
| Diff hygiene | `git diff --check --cached` | exit 0, no output |
| Commit-scoped secret scan | after commit, `gitleaks git --redact --no-banner --log-opts=HEAD^..HEAD` | exit 0, no leaks in the new commit |

## Scope

**In scope** (the only files you may modify):

- `docs/RUNBOOK-split-hop-pilot.md`
- `docs/SPLIT-HOP-TOPOLOGY.md`
- `tests/unit/test_probe_matrix_provisioning.py`

**Out of scope** (do not modify):

- Any Ansible role, template, handler, defaults file, inventory, group-vars profile, secret example/schema, Terraform root, Makefile target, generated artifact, or runtime behavior.
- Changing the topology, initiator direction, tunnel subnet, interface name, routing table, fwmark, role tier, role toggle, research allowlist policy, secret field names, or service-user policy.
- Adding a paired deploy orchestrator, per-leg watchdog, automated flow-data collection, new verification script, or a third-party endpoint dependency.
- Claiming the pilot has been run or the flow-level mitigation has been empirically validated. Flow-data collection remains operator-driven and pending.
- Adding or rotating any real key, IP address, hostname, provider credential, secret, or environment-specific inventory.
- Reformatting unrelated prose, updating `CHANGELOG.md`, editing plans, or touching files outside the three listed paths.

## Git workflow

- Branch: `codex/advisor-014-declarative-split-hop-runbook`.
- Create one focused Conventional Commit: `docs(split-hop): use declarative ingress role`.
- Do not push, merge, cherry-pick, or open a pull request.

## Steps

### Step 1: Replace the stale secret and deployment procedure

Rewrite `docs/RUNBOOK-split-hop-pilot.md` so it is an operator procedure for the two shipped roles:

1. Keep the pilot-only framing and two-node prerequisite, but remove every claim that Node A lacks Ansible coverage. State that Node A runs the client-facing transport stack plus `split-hop-ingress`, while Node B runs `split-hop-egress` with client-facing transports disabled.
2. Keep workstation key generation. Rewrite the key-location table so Node A's private key and Node B's public key map to `split_hop_ingress_secrets`, Node B's private key and Node A's public key map to `split_hop_egress_secrets`, and the optional PSK is stored in both nodes' SOPS files. Do not place private material directly in `/etc/wireguard` or add example values that resemble usable secrets.
3. Add separate Node A and Node B SOPS YAML snippets using exactly the fields in `secrets/prod.secrets.example.yaml`. Keep `make validate-secrets` after both files are edited.
4. Add separate host-variable snippets. Node A must set `vpn.enable_split_hop_ingress: true` and `allow_research_roles: [split-hop-ingress]`; Node B must set `vpn.enable_split_hop_egress: true` and keep the existing explicit client-facing transport disables. Do not add `split-hop-egress` to the research allowlist because its live tier does not require it.
5. Deploy each host with the existing `PROVIDER=<provider> ENV=<env> make deploy` surface, making clear that each command targets that node's environment/inventory. State that the roles assert required secrets before rendering and own their respective `shop0` configurations.

Delete the hand-written WireGuard configuration, `systemctl enable`, iptables, and `netfilter-persistent` instructions completely. Do not replace them with equivalent ad hoc commands.

**Verify**: stale procedure scan from the command table produces no output; required declarative terms are present.

### Step 2: Align verification and teardown with role ownership

Keep the useful `wg show shop0` verification on both nodes. Correct the explanatory text so Node A has no configured peer endpoint or keepalive, while a runtime endpoint may appear after Node B initiates the handshake. Verify egress with a neutral command that exercises a transport-owned connection through the role's marked policy; do not claim `curl --interface shop0` proves the UID-based policy. If the runbook retains a direct interface diagnostic, label it only as a tunnel/NAT diagnostic and use `shop0`, not `awg0`.

Preserve the 24–72 hour flow-data collection and pilot-results sections without upgrading their claims. Keep the carrier/geography naming prohibition.

Rewrite teardown declaratively: set both `vpn.enable_split_hop_ingress` and `vpn.enable_split_hop_egress` false in their respective host variables, redeploy both nodes so Ansible disables role participation according to the repository's normal lifecycle, then destroy ephemeral VPSes if the pilot is over. Do not add broad firewall flushes. If current role disable semantics do not remove already-created files/services, describe the safe operator limitation explicitly and stop short of inventing an unmanaged cleanup command; this is documentation correction, not lifecycle implementation.

**Verify**: no manual configuration/iptables teardown remains and no sentence claims empirical pilot completion.

### Step 3: Correct the ADR's high-level pilot procedure and pin the runbook contract

In `docs/SPLIT-HOP-TOPOLOGY.md`, change only the pilot stand procedure:

- Load the paired SOPS blocks on their owning nodes, not only `split_hop_egress_secrets`.
- Enable `split-hop-ingress` on Node A with its RESEARCH allowlist and `split-hop-egress` on Node B.
- Keep the two separate `site.yml` deployments and explicitly preserve Node B as initiator.
- Replace the `awg0` diagnostic with `shop0` and distinguish tunnel health from transport policy verification.
- Keep flow-data validation operator-driven and preserve all architectural/threat-model caveats.

Extend `test_ingress_marks_only_new_original_direction_runtime_connections` in `tests/unit/test_probe_matrix_provisioning.py`; do not add a new test function. Read the runbook and assert that it contains `split_hop_ingress_secrets`, `enable_split_hop_ingress`, `allow_research_roles`, and `split-hop-ingress`, and that it does not contain the stale manual-coverage sentence, `iptables`, or `netfilter-persistent`. This intentionally protects only stable declarative ownership terms, not whole prose paragraphs.

**Verify**: focused static contract passes with the same number of tests collected as before.

### Step 4: Run regressions and commit normally

Run both Molecule scenarios and the full unit suite. Inspect the entire diff and confirm only the three in-scope paths changed, the docs reflect live variable names, and the test is a narrow extension. Stage exactly those paths and run `git diff --check --cached`.

Commit normally with hooks enabled using `docs(split-hop): use declarative ingress role`; never skip hooks. After commit, run the commit-scoped gitleaks scan and confirm the isolated worktree is clean.

**Verify**: `git diff-tree --no-commit-id --name-only -r HEAD | sort` lists exactly the three in-scope paths; scoped gitleaks exits 0; `git status --short` is empty.

## Test plan

- The existing static contract test prevents the operator runbook from reverting to manual Node A ownership or omitting the ingress role's required toggle/allowlist.
- The ingress Molecule scenario proves the responder renders without an endpoint/keepalive and installs the conntrack-based nftables policy.
- The egress Molecule scenario proves the paired initiator configuration and forwarding surface still converge.
- The full unit suite catches repository policy, documentation counts, and adjacent provisioning contract regressions.
- Human diff review checks that the operational steps use exact live variable names while retaining pilot-only evidence limits.

## Done criteria

- [ ] The runbook no longer says Node A lacks Ansible coverage or instructs any manual WireGuard, iptables, or netfilter-persistent configuration.
- [ ] Both nodes' private/public key placement and optional PSK are documented through the correct SOPS secret blocks.
- [ ] Node A's ingress toggle and `allow_research_roles: [split-hop-ingress]` are explicit; Node B's egress toggle and transport disables remain explicit.
- [ ] Verification distinguishes configured initiator direction, runtime handshake state, direct tunnel diagnostics, and transport-owned policy routing.
- [ ] Teardown disables both toggles and does not flush unrelated firewall state.
- [ ] The topology ADR's high-level pilot sequence matches the two shipped roles and `shop0` interface.
- [ ] The existing static contract test pins stable declarative runbook terms without adding a test function.
- [ ] Focused tests, both Molecule scenarios, full unit tests, diff hygiene, hooks, and scoped gitleaks pass.
- [ ] Exactly three in-scope paths are committed; the executor reports the commit SHA; the isolated worktree is clean.

## STOP conditions

Stop and report instead of improvising if:

- Any in-scope file drifted from `7bdba37` or no longer matches the current-state excerpts.
- The live ingress/egress defaults, templates, schema, tier manifest, or site wiring contradict any variable name or ownership statement in this plan.
- Correct verification requires adding/changing an Ansible task, role teardown handler, transport probe, external service, inventory layout, or Makefile target.
- Disabling the toggles cannot honestly be documented as sufficient teardown and a safe correction would require unmanaged broad firewall or routing commands. Document the limitation only if it is already evident; do not implement lifecycle behavior in this plan.
- A real secret, address, hostname, provider choice, environment name, or carrier/geography identifier would be required.
- Either Molecule scenario, focused/full tests, hooks, or the stale-procedure scan fails twice after one reasonable in-scope correction.
- Any fourth file, generated artifact, external URL, network lookup, dependency change, or behavior change is required.

## Maintenance notes

The runbook should describe role-owned state, while role defaults/templates and the secret schema remain the source of truth. Future split-hop lifecycle or observability gaps belong in separate implementation plans; do not hide them behind manual operator mutations in this procedure.
