"""Controller-installed callback: the run ends with its slowest tasks, task names and roles.

Only task names and wall-clock durations leave Ansible, never task arguments or results.
"""
import collections
import time

from ansible.plugins.callback import CallbackBase

LIMIT = 20


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'aggregate'
    CALLBACK_NAME = 'ripdpi_task_timing'
    CALLBACK_NEEDS_ENABLED = True

    def __init__(self):
        super().__init__()
        self._durations = []
        self._current = None

    def _start(self, task):
        # A task lasts until the next task starts, as in profile_tasks: the time includes the
        # include or play overhead that follows it. The last task ends at the stats.
        now = time.monotonic()
        if self._current:
            started, name, role = self._current
            self._durations.append((now - started, name, role))
        self._current = task and (now, task.get_name().strip(), task._role.get_name() if task._role else '(play)')

    def v2_playbook_on_task_start(self, task, is_conditional):
        self._start(task)

    def v2_playbook_on_handler_task_start(self, task):
        self._start(task)

    def v2_playbook_on_stats(self, stats):
        self._start(None)
        names, roles = collections.defaultdict(lambda: [0, 0.0]), collections.defaultdict(lambda: [0, 0.0])
        for seconds, name, role in self._durations:
            for key, table in ((name, names), (role, roles)):
                table[key][0] += 1
                table[key][1] += seconds
        total = sum(seconds for seconds, _name, _role in self._durations)
        lines = [f'TASK TIMING: {len(self._durations)} tasks, {total:.1f}s', 'slowest tasks:']
        lines += [f'{seconds:9.1f}s  {name}' for seconds, name, _role in sorted(self._durations, reverse=True)[:LIMIT]]
        for title, table in (('slowest task names (runs, total):', names), ('slowest roles (tasks, total):', roles)):
            lines.append(title)
            lines += [f'{seconds:9.1f}s {count:5d}  {key}'
                      for key, (count, seconds) in sorted(table.items(), key=lambda item: -item[1][1])[:LIMIT]]
        self._display.display('\n'.join(lines))
