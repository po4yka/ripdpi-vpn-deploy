# SEC-1794807596362904: Close baseline hardening gaps from the live fleet audit

## Objective

Managed VPN nodes converge to the kernel, account, package and journal-budget properties in `security/baseline-host-hardening`.

## Ownership

`ansible/roles/baseline/` (sysctl template, `tasks/main.yml`, Molecule verify, role note), `ansible/roles/monitoring/tasks/enable.yml` and its role note, `tests/snapshot/golden/baseline/`, and the unit tests that render these files. One writer; no shared-file lane.

## Execution

- [x] SEC-1794807731415728 Add IPv6 redirect, kexec and BPF JIT keys to the baseline sysctl policy with Molecule and snapshot coverage #bug @item:SEC-1794807596362904
- [x] SEC-1794807783915807 Lock the root account password in the baseline role with Molecule coverage #bug @item:SEC-1794807596362904
- [x] SEC-1794807812667879 Purge modemmanager, apport, open-vm-tools and snapd in the baseline role with Molecule coverage #bug @item:SEC-1794807596362904
- [x] SEC-1794807838451591 Raise the journald size budget to 1G in the monitoring role with a test that pins the policy #bug @item:SEC-1794807596362904
- [x] SEC-1794815487021281 Flush the journal to persistent storage in the monitoring role with Molecule and unit coverage #bug @item:SEC-1794807596362904
- [x] SEC-1794807863934919 Run the narrow checks and make check, then record evidence in verification.md #bug @item:SEC-1794807596362904

## Verification

Local: the unit tests that render the sysctl template and the journald policy, `make snapshot-check`, `make molecule-test ROLE=baseline`, `make molecule-test ROLE=monitoring`, `make check`. Remote CI: the pull request checks. Dry run and live: `make dry-run` and deployment per node under separate operator authorization, then the running values read back. Staging, client and artifact gates do not apply.
