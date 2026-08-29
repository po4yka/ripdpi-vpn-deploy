## Context

Seven verification-honesty findings share a mechanism: gates assert less than deploy produces, or scenarios test less than their docs claim. The idempotence contract (second converge reports changed=0) is stated in ansible/CLAUDE.md as universal but is enforced nowhere for the integration tests that matter most. Fixing the amneziawg scenario may surface latent task bugs — those are in scope to fix minimally when revealed.

## Goals / Non-Goals

- Goal: verification output is trustworthy for every host class and scenario docs describe reality.
- Non-goal: adding new production runtime behavior; expanding molecule coverage to roles that deliberately have none (documented skips stay).

## Decisions

- Idempotence phases appended to existing sequences rather than a new scenario: the contract applies to the same converge.
- amneziawg converge rewritten around include_role with explicit synthetic source/build fixtures and no-TUN tools: executes real task code without claiming an upstream build or tunnel proof.
- Fallback-listener assertions conditional on fallback_enabled: mirrors deployment conditions, avoids failing hosts that never open those ports.
- TESTING.md synced by observation (read each molecule.yml), not by intent.

### AWG fixture boundary (step TST-1787496118906595)

Preparation creates two local Git repositories containing synthetic Makefiles and
no-TUN shell tools. Fixture-owned Git configuration redirects the two exact
upstream URLs to these repositories; `GIT_ALLOW_PROTOCOL=file` rejects external
fallback. The configuration exists only inside the isolated scenario container.
The fixture pins its own resolved commits, not upstream release identities.
Preparation does not install role binaries, write build receipts, or render role
templates. The unchanged role performs package installation, cloning, commit
verification, build/install/receipt writes, configuration, and systemd convergence.
Verification checks those outputs and the real unit's execution of the fixture
tool; the ordinary second converge must report no changes. This proves role
orchestration, not upstream source authenticity, AWG traffic or physical-device
behavior. Docker's resolver remains container-owned through the package's
documented debconf setting; the role's apt task is not skipped.

### Xray idempotence boundary (step TST-1787496118907291)

The default scenario retains its synthetic release binary but does not stage a
second regular file at `/usr/local/bin/xray`: the real runtime role owns that
symlink. A second converge must preserve both runtime links and release bytes
with zero changes, including fixture setup. Add the explicit idempotence phase;
do not suppress changed results, skip production tasks or substitute a success
declaration for a real repeat. A local replay of the actual filesystem tasks
captures the regression before implementation; isolated Molecule must still
verify the whole scenario. This slice does not change production roles, baseline
or either full-stack scenario and remains separate from AWG delivery.

## Contracts and ownership

- Playbooks owned here: verify.yml, smoke-test.yml, source-drift.yml.
- Molecule trees owned here: full-stack, full-stack-published, roles/xray, roles/amneziawg.
- docs/TESTING.md edited exclusively within this change.

## Risks / Trade-offs

- Enabling full-stack idempotence can reveal pre-existing non-idempotent tasks → fix minimally and record each fix in the change notes; do not weaken assertions.
- Stricter source-drift can fail legitimately drifted nodes → intended; runbook already prescribes redeploy on drift.
- CI runtime grows with two added idempotence phases → bounded by existing scenario durations.

## Migration Plan

- Forward: single commit per concern; no production state changes.
- Rollback: revert commits independently.
- Gates: touched molecule scenarios, live-inventory verify cycle, `make ci-fast`, `make validate`.

## Published scenario prerequisites — 2026-08-29

- Before step `TST-1787496118906321` can exercise repeat convergence, the published scenario must resolve Galaxy requirements to this checkout's pinned root file from its documented `ansible/` working directory and supply the provider listener contract consumed by site preflight.
- The contract describes the scenario's actual toggles, ports and shared synthetic secrets. Local tests use the canonical template renderer and listener validator with only those inputs; they must not inject unrelated group-vars defaults that Molecule does not load. A changed declared port must fail the comparison.
- A separate installed-Ansible regression loads all actual site roles with literal false conditions and runs only the source manifest pre-task plus an observation. It checks static-default visibility against the declared active listener surface without executing role tasks. This scenario leaves the Xray fallback undefined/off; it does not inherit the separate group-vars value of 2053.
- This bounded prerequisite slice preserves the published port mappings, role set and sequence. It does not run roles, prove idempotence or replace full Molecule acceptance; baseline/SSH changes require separate coordination.

## Smoke host-class slice — 2026-08-28

- A single outer smoke transport block gates protocol credentials, local facts, resource preflight/claim, clients and cleanup on `not vpn_subscription_only` plus an enabled supported transport. Subscription-only and all-disabled hosts require no transport credentials and perform no smoke-client or workdir operation; the existing secrets-file entrypoint requirement remains.
- Protocol-local assertions and client selection execute only for that protocol. Existing ports, enable defaults and client credential formats remain unchanged. Local tests run the real source task graph with no transport credentials for subscription-only hosts and assert zero temporary-executable calls and no workdir.

## Verification host-class slice — 2026-08-28

- Step TST-1787496118906453 adds the existing subscription-only predicate to all eleven remaining transport tasks: REALITY TCP, nginx public TCP/configuration, P1 IPv4/IPv6 prerequisites and resolution, Hysteria service, Snell configuration/service/listeners, and AmneziaWG interface checks. Existing toggle defaults and task bodies are unchanged.
- The guard follows site.yml's subscription-only transport skip. Shared bootstrap, manifest, firewall, SSH and sysctl checks remain outside transport gating. No role, watchdog, SSH setting, listener contract or source-drift behavior changes.
- Tests extend the existing real-Ansible listener fixture to execute unchanged task slices with temporary executables at external inspection boundaries. Every added guard has a subscription-only regression; enabled and disabled controls plus shared-hardening checks prevent blanket skipping. This is conditional/task-slice proof, not full-playbook or live-host acceptance.
