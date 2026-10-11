"""Read-only service identity discovery; never infer or allocate a UID."""
import json
import grp
import pwd
import sys


def inspect(names):
    allowed = {"transport-normalizer", "transport-gateway", "transport-warp-gateway", "cascade-classifier", "xray", "hysteria"}
    if not isinstance(names, list) or not names or any(type(n) is not str or n not in allowed for n in names):
        raise ValueError("identity-declaration-invalid")
    if len(names) != len(set(names)):
        raise ValueError("identity-declaration-duplicate")
    # Numeric UID and primary-GID authority includes implicit memberships and
    # aliases outside the selected service list. Keep that metadata internal.
    accounts = pwd.getpwall()
    groups = grp.getgrall()
    uids, gids, missing, missing_groups = {}, {}, [], []
    for name in names:
        try:
            group = grp.getgrnam(name)
        except KeyError:
            group = None
        if group is not None:
            if (group.gr_gid <= 0 or set(group.gr_mem) - {name}
                    or any(value.gr_gid == group.gr_gid and value.gr_name != name for value in groups)
                    or any(value.pw_gid == group.gr_gid and value.pw_name != name for value in accounts)):
                raise ValueError("identity-group-invalid")
        try:
            entry = pwd.getpwnam(name)
        except KeyError:
            if group is not None and group.gr_mem:
                raise ValueError("identity-group-invalid")
            missing.append(name)
            if group is None:
                missing_groups.append(name)
            continue
        if entry.pw_uid <= 0 or entry.pw_gid <= 0 or entry.pw_shell not in {"/usr/sbin/nologin", "/sbin/nologin"}:
            raise ValueError("identity-authority-invalid")
        if any(value.pw_uid == entry.pw_uid and value.pw_name != name for value in accounts):
            raise ValueError("identity-authority-shared")
        if group is None:
            raise ValueError("identity-group-absent") from None
        if group.gr_gid != entry.pw_gid or group.gr_gid in gids.values() or set(group.gr_mem) - {name}:
            raise ValueError("identity-group-invalid")
        if entry.pw_uid in uids.values():
            raise ValueError("identity-authority-shared")
        uids[name], gids[name] = entry.pw_uid, entry.pw_gid
    return {"uids": uids, "gids": gids, "missing": missing, "missing_groups": missing_groups}


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise ValueError("identity-input-oversize")
        print(json.dumps(inspect(json.loads(raw))))
    except (ValueError, TypeError, OSError):
        print("transport-identity-refused", file=sys.stderr)
        raise SystemExit(1)
