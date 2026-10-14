#!/usr/bin/env python3
"""Pause only archive creation while exercising the production backup lifecycle."""

import fcntl
import importlib.util
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace

root = Path('/var/lib/observability-kuma')
spec = importlib.util.spec_from_file_location('backup', '/usr/local/libexec/observability-kuma-backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
destination = Path('/run/observability-kuma-lifecycle/archive')
destination.mkdir(mode=0o700, exist_ok=True)
original_command = backup.command


def command(argv):
    original_command(argv)
    if argv[1] == 'start':
        (root / 'backup-finalizer-ran').write_text('observer restarted by backup finalizer\n')


def paused_archive(*_args, **_kwargs):
    (root / 'backup-fixture-ready').write_text('observer quiesced\n')
    signal.pause()
    raise ValueError('archive-interrupted')


backup.command = command
backup.subprocess = SimpleNamespace(run=subprocess.run, Popen=paused_archive, PIPE=subprocess.PIPE, DEVNULL=subprocess.DEVNULL)
with open('/run/observability-kuma-lifecycle/lock', 'a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    backup.backup({'directory': str(destination), 'image': 'fixture'}, destination)
