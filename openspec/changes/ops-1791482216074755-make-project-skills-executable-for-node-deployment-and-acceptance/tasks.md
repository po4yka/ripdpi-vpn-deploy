# OPS-1791482216074755: Make project skills executable for node deployment and acceptance

## Objective

Deliver concise lifecycle/role skills and a validated local promotion-intent preparer, with realistic decision-boundary evaluation and existing enforcement intact.

## Ownership

- New-skills worker: .agents/skills/vpn-bootstrap/, vpn-deploy/, vpn-acceptance/, vpn-cleanup/ and ansible-role/.
- OpenSpec worker: .agents/skills/openspec-explore/, openspec-sync-specs/ and openspec-apply-change/.
- Root: Makefile, scripts/prepare-disposable-promotion-intent.py, its tests/runbook, evaluation scenarios, aliases, root/subtree notes and generated hashes.
- Root serializes task lifecycle, board generation and shared files. Workers preserve others' edits and do not mutate infrastructure.

## Execution

- [x] OPS-1791482488877561 Specify skill workflows and private intent preparation contract #feature !high @item:OPS-1791482216074755
- [x] OPS-1791482490840434 Deliver concise operator and Ansible skills with supported workflow transitions #feature !high @item:OPS-1791482216074755
- [x] OPS-1791482495146337 Implement canonical private promotion intent preparation and failure tests #feature !high @item:OPS-1791482216074755
- [ ] OPS-1791482498372510 Validate skills with independent scenarios and exact-head PR checks #feature !high @item:OPS-1791482216074755

## Verification

- Private preparer success/failure and Make literal-input tests; relevant promotion and agent-instruction contracts.
- Skill validator plus independent forward-evaluation of realistic requests without live operations.
- make task-check, required local make check and exact-head PR CI. No live evidence is claimed by this local skill/tooling change.
