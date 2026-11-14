"""Controller-installed callback: only aggregate check-mode counts leave Ansible."""
import json
import os

from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'aggregate'
    CALLBACK_NAME = 'ripdpi_check_statistics'
    CALLBACK_NEEDS_ENABLED = True

    def v2_playbook_on_stats(self, stats):
        totals = {'hosts': len(stats.processed), 'changed': 0, 'failures': 0, 'unreachable': 0}
        for host in stats.processed:
            summary = stats.summarize(host)
            for field in ('changed', 'failures', 'unreachable'):
                totals[field] += summary[field]
        fd = os.open(os.environ['RIPDPI_CHECK_STATS_FILE'],
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(totals, stream)
            stream.flush()
            os.fsync(stream.fileno())
