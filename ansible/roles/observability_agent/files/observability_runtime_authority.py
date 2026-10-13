"""Read-only admission before installing the sender's privileged helper files."""
import os
from pathlib import Path
import stat
import sys


def validate(ancestor_check, *, uid=0, helper=Path('/usr/local/libexec/observability-runtime'),
             state=Path('/var/lib/observability-agent-activation'),
             guard=Path('/etc/systemd/system/observability-agent.service.d')):
    files = {'transport_runtime_transaction.py', 'observability_runtime_accept.py',
             'observability_runtime_queue.py', 'observability_agent_readiness.py',
             'observability_queue_boundary.py'}
    for path, mode in ((helper, 0o700), (state, 0o700), (guard, 0o755)):
        nearest = path
        while not os.path.lexists(nearest):
            nearest = nearest.parent
        fd = ancestor_check(nearest, uid)
        os.close(fd)
        if os.path.lexists(path):
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != mode:
                raise ValueError('sender-directory-authority')
    for path, mode in [(helper / name, 0o600) for name in files] + [(guard / 'acceptance.conf', 0o644)]:
        if os.path.lexists(path):
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or
                    stat.S_IMODE(info.st_mode) != mode or info.st_nlink != 1):
                raise ValueError('sender-helper-authority')


if __name__ == '__main__':
    try:
        source = sys.stdin.buffer.read(262145)
        if len(source) > 262144:
            raise ValueError('sender-authority-source-budget')
        namespace = {'__name__': 'sender_authority_library'}
        exec(source, namespace)
        validate(namespace['ancestors'])
    except Exception:
        raise SystemExit('sender-helper-authority-refused') from None
