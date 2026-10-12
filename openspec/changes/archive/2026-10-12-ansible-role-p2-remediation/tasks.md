# ANS-1791562764586678: Repair P2 role lifecycle and configuration contracts

## Objective

Repair or verify all confirmed P2 audit paths, qualify investigated candidates,
preserve P1 safety and add positively tested source to existing PR 282.

## Ownership

- Host/web worker: `ansible/roles/{baseline,real-vps-awg-nat,tailnet-management,firewall,package_updates,intrusion_prevention,nginx-xhttp,cdn-front,geodata,subscription-host}/`, associated tests and role notes; F11-F24 plus I05/I06. Own the reusable nginx transaction interface in the nginx role scope; primary owns collector integration.
- Transport worker: `ansible/roles/{hysteria-realm,amneziawg,naive,warp-outbound,probe-matrix-target,split-hop-ingress,split-hop-egress,dns-morph-bridge,xray-runtime}/` and directly required measurement-role code/tests/notes; F25-F31 plus I01-I04. Request shared runtime-release changes through primary.
- Primary: `ansible/roles/{observability_agent,observability_control_plane,observability_deadman,policy-ratelimit,watchdog}/`, remaining-role owned disable paths and direct tests/notes; F32-F42/current contract. Serialize common roles/helpers and any overlap.
- Shared files, primary only: `ansible/playbooks/site.yml`, `ansible/CLAUDE.md`, group_vars, schemas/examples, listener/profile and topology contracts, shared scripts, snapshots, CI, documentation/task/spec files and PR publication. Workers request needed edits and preserve concurrent/P1 work; no worker staging or commits.

## Execution

- [x] ANS-1791563231017425 Repair host TLS and SSH prerequisites, predictive Tailnet inspection and effective security policy #bug !high @item:ANS-1791562764586678
- [x] ANS-1791563231572678 Make nginx and geodata publication transactional and preserve vhost privacy and AOP behavior #bug !high @item:ANS-1791562764586678
- [x] ANS-1791563232134870 Deliver supported Realm, complete Naive listeners and exact stable WARP runtime contracts #bug !high @item:ANS-1791562764586678
- [x] ANS-1791563232708226 Reconcile AWG instances and measurement services on binary unit and membership changes #bug !high @item:ANS-1791562764586678
- [x] ANS-1791563233266863 Reconcile site-level disabled ownership without deleting unrelated or retained recovery state #bug !high @item:ANS-1791562764586678
- [x] ANS-1791563233830915 Repair predictive observability and complete retained authority and rollback generation boundaries #bug !high @item:ANS-1791562764586678
- [x] ANS-1791563234416737 Publish bounded idle policy health and durable cohort-aware watchdog and malformed-evidence state #bug !high @item:ANS-1791562764586678
- [x] ANS-1791563234994294 Resolve bounded P2 packet DNS and release-identity investigations with native positive evidence #bug !high @item:ANS-1791562764586678
- [x] ANS-1791563235717247 Preserve P1 regressions and complete independent review snapshots local gates and exact-source PR checks #bug !high @item:ANS-1791562764586678

## Verification

Focused positive/failure, actual check-mode and idempotent lifecycle tests;
exact pinned native parser/runtime and Linux namespace/socket/enforcement
acceptance where named; affected Molecule including transitions and rejected
candidate rollback; reviewed snapshots, schema/listener/profile checks, full
build-gated `make check`, independent review and exact-source PR CI.
Real dry-run, staging/fleet mutation, external client/human acceptance are
outside this source PR; synthetic fixtures never stand in for those layers.
