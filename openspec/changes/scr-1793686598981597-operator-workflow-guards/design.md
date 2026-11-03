# Operator maintenance design

Scope: six approved recommendations; source and local-test delivery only. No provider access, credential rotation, host mutation, paid resource, or production backup operation.
1. Skills select panel-only versus Telegram explicitly and have no historical rollout hold. A continuation guide binds selected checkout/state owner, component source authorities, active inputs, pending journals, and scoped expiring authorization.
2. Release checker consumes a private JSON plan and actual local checksum-pinned tar/zip archives; verifies HTTPS release URLs, all required regular members and architecture mappings without extraction. Optional Linux APT policy checks read actual dpkg-query/apt-cache results and an exact version preference. It never installs or downloads releases.
3. Diagnostics runner consumes a private JSON command plan, bounds combined capture, time and stdin, owns/reclaims its process group, encrypts stdout/stderr and status with age, keeps real exit codes, emits only fixed categories/counts, and never writes plaintext diagnostic output. Encryption/output admission happens before the child. Command authorization remains the caller's responsibility.
4. Kit command consumes an explicit private audit plan with catalog JSON-pointer bindings, selected file hashes/kinds and freshness. It checks filesystem authority and current references. A seal verb creates a bounded age-encrypted tar with a complete manifest of selected files. A verify-backup verb downloads the exact B2 object using checksum-pinned rclone and environment credentials, compares ciphertext, decrypts in RAM and verifies the full manifest against unchanged selected sources. It does not claim fresh host health or bucket policy checks. Working identities, output archive and post-publication acknowledgement are not self-included.
5. New entry points use Make with literal environment inputs. Public docs define strict plan fields and commands. No production dependency is added.
6. Task validation checks installed pinned tool availability before expensive portfolio/history loading; full downstream validation remains intact.
Tests: real age round trips with generated test identities; real tar/zip parsing; external process output/exit/time/descendant tests; B2 transport fake only at the external rclone boundary; wrong hashes/permissions/symlinks/traversal/duplicate members/changed pointers/stale plans/wrong identity/refused encryption; APT command boundary tests; task-check order and existing task tests. Run required full make check once and independent patch/security review before PR.

## Ownership and integration

Own scripts/operator_private.py, scripts/operator-maintenance.py, the task
preflight, matching tests, Make wiring, and the named workflow documentation.
Use the existing private output publisher. Existing inspection helpers do not
retain stderr or failed-command output and cap stdin below kit archive size;
they cannot supply this capture contract without changing remote inspection.
No Terraform, cloud-init, Ansible runtime or vpnd behavior changes.

## Inputs, migration and rollback

Private JSON plans are explicit and versioned. They do not replace the existing
arbitrary private catalog schema. JSON-pointer bindings select current material.
The kit archive format is a selected-file tar plus manifest.json, encrypted by
age. Existing archives are retained; a different archive format is not silently
adopted. The new sealer produces the format consumed by the verifier.
No private files migrate automatically. Rollback removes use of the new commands
and keeps every existing authority and backup. No credential values enter argv.

## Verification limits

Use real age, archives and child processes in local tests. Fake only the B2
transport and APT command boundaries; report those as isolated tests. Local
verification does not prove provider access, host freshness or physical clients.
