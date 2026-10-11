# ANS-1790316250156031: Reject public listeners on the effective SSH port before convergence

## Objective

Firewall convergence fails closed whenever a TCP public listener contract entry covers the effective SSH port, before nftables or any listener role changes the host.

## Ownership

- The primary agent owns `ansible/roles/firewall/tasks/main.yml`, `tests/unit/test_firewall_ssh_port_reservation.py`, `ansible/roles/firewall/CLAUDE.md`, `ansible/roles/honeypot/CLAUDE.md`, and this change's artifacts.

## Execution

- [x] ANS-1790316534792016 Add the firewall-role assert rejecting TCP public contract listeners (exact port or range) on the effective SSH port before nftables renders #bug @item:ANS-1790316250156031
- [x] ANS-1790316540041401 Add tests/unit coverage that evaluates the real firewall assert with the pinned ansible-core templar for exact, range, UDP and clean contracts #bug @item:ANS-1790316250156031
- [x] ANS-1790316540566345 Update the firewall and honeypot CLAUDE.md knowledge layer for the SSH port reservation #bug @item:ANS-1790316250156031

## Verification

Use the exact gates and evidence categories in verification.md.
