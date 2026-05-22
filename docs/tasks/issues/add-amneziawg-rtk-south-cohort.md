---
title: Add AmneziaWG RTK South cohort YAML
type: task
status: backlog
area: ansible
priority: medium
owner: unassigned
parent: null
blocks: []
blocked_by: []
created: 2026-05-22
updated: 2026-05-22
source_wiki_pages:
  - "[[wireguard-rtk-south-amneziawg-bypass]]"
linked_task: ../../../../RIPDPI/docs/tasks/issues/wire-amneziawg-rtk-south-jc4-cohort-into-android-client.md
---

- [ ] #task Add AmneziaWG RTK South cohort YAML #repo/RIPDPI-VPN-DEPLOY #area/ansible #status/backlog 🔼

## Motivation

Companion to RIPDPI Android `wire-amneziawg-rtk-south-jc4-cohort-into-android-client`. Per CLAUDE.md §"New AmneziaWG cohort", a new cohort lands as a YAML file under `ansible/roles/amneziawg/vars/cohorts/<carrier>.yml` plus a row in `docs/AWG-COHORTS.md`. RTK South (Rostelecom South, Rostov Oblast) would be the FIRST cohort in this repo — community-tested parameters (`Jc=4 Jmin=10 Jmax=50 S1-4=0 H1-4=1/2/3/4`) confirmed working against TSPU at that ISP per the source wiki page.

## Proposed change

1. Create `ansible/roles/amneziawg/vars/cohorts/rtk-south.yml` with the full parameter set documented in the source wiki page.
2. Add a row to `docs/AWG-COHORTS.md` (carrier=Rostelecom South Rostov, junk packet sizes, init/response packet sizes, obfuscation key reference).
3. If the `amneziawg` role does not already select a cohort YAML based on `group_vars` hint, add the selection logic.
4. Update molecule scenario to cover the cohort-selection path.

## Canonical recipe

new-awg-cohort — follows §"New AmneziaWG cohort" in CLAUDE.md verbatim:
1. Create `ansible/roles/amneziawg/vars/cohorts/rtk-south.yml` with obfuscation parameters.
2. Add row to `docs/AWG-COHORTS.md` (carrier, junk packet sizes, init/response packet sizes, obfuscation key).
3. `group_vars` hint or comment if the cohort requires non-default operator awareness at deploy time.

### Linked client task

`linked_task:` points to RIPDPI Android. Both must ship together.

## Acceptance criteria

- [ ] `ansible/roles/amneziawg/vars/cohorts/rtk-south.yml` checked in with the full parameter set from the wiki page.
- [ ] `docs/AWG-COHORTS.md` updated with RTK South row.
- [ ] Molecule scenario validates cohort selection logic (or new scenario added if cohorts directory is first-of-kind).
- [ ] Operator instructions documented if RTK South requires explicit toggle in `group_vars/all.yml`.

## Risks / open questions

- "Sometimes stalls on handshake requiring 3–4 connection attempts" — cohort parameters may need refinement after broader deployment data.
- Per-node variance within RTK South — parameters were measured at one vantage; other Rostov-region Rostelecom nodes may have different thresholds.
- The `amneziawg` Ansible role's current `defaults/main.yml` overrides via group_vars and playbook vars; cohort-file-based selection may require additional role logic (the role didn't have a `vars/cohorts/` directory at first-run time).

## References

- [[wireguard-rtk-south-amneziawg-bypass]] — wiki concept page with full parameter set + observed behavior at RTK South
- Linked client task: `wire-amneziawg-rtk-south-jc4-cohort-into-android-client` in RIPDPI repo
- Canonical recipe: CLAUDE.md §"New AmneziaWG cohort"
