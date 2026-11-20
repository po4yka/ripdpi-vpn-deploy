## Context

`ansible/roles/monitoring/templates/logrotate-xray.j2` created new log files and then ran `generation.py recover --unit xray.service` (guarded profiles) or `systemctl restart xray.service`. No timer, geodata job or certificate hook in the roles restarts Xray daily; logrotate's daily run is the only midnight trigger. Xray opens `access.log` and `error.log` with `O_APPEND|O_WRONLY|O_CREATE`, holds the descriptor while messages arrive, closes it after an idle minute and reopens by path. It has no reopen signal.

## Goals / Non-Goals

- Goal: daily rotation with no Xray restart on any profile.
- Goal: sniffing for routing only, default buffers, a tighter unit sandbox.
- Non-goal: changes to nginx rotation, the Hysteria unit, the sysctl file, group_vars or the generation controller.

## Decisions

- `copytruncate` with no script. Because the descriptor is `O_APPEND`, writes after the truncate land at the new end of file. Rejected: keep the restart on a random delay (still drops sessions); move logs to journald (changes the policy-ratelimit reader contract).
- Drop `create`, `sharedscripts` and the guarded/unguarded branch; `copytruncate` keeps the provisioned inode, owner and 0640 mode, so the log-reader group contract is unchanged.
- `routeOnly: true` on both inbounds. The only users of the sniff result are the BitTorrent rule, the UDP/443 rule and operator WARP rules, all routing. The normalizer resolves names itself and policy-ratelimit does not read sniffed names.
- Remove `bufferSize: 4`. It arrived in the first hardening commit with no recorded reason; 4 KB per connection throttles throughput and the hosts have 1-2 GB.
- `LimitNOFILE=524288`, half of `fs.file-max` (1048576), so Xray alone cannot exhaust the host file table.

## Contracts and ownership

- Roles `monitoring` and `xray` only. The transport-egress generation controller keeps its `recover` verb for other callers.

## Risks / Trade-offs

- Lines written between copy and truncate can be lost → accepted for diagnostic logs.
- A client that sends an address resolved by a poisoned local resolver is no longer corrected by server-side re-resolution → repository clients send names or resolve through the tunnel.
- Default buffers can hold up to about 512 KB per stalled connection → acceptable at this fleet's connection counts.
- A sandbox option could fail on an old kernel → Molecule converge and the native lanes start the unit.

## Migration Plan

The next deploy publishes the policy, configuration and unit; the guarded transaction restarts Xray once. Rollback is a revert and redeploy. Live acceptance: Xray `ActiveEnterTimestamp` does not move across a midnight rotation.
