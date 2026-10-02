#!/usr/bin/env python3
"""Lifecycle fixture: reproduce a quiesced backup's restart in its finally path."""

from pathlib import Path
import signal
import subprocess


def terminate(_signal, _frame):
    raise SystemExit(0)


signal.signal(signal.SIGTERM, terminate)
root = Path('/var/lib/observability-kuma')
subprocess.run(['/usr/bin/systemctl', 'stop', 'observability-kuma.service'], check=True)
(root / 'backup-fixture-ready').write_text('observer quiesced\n')
try:
    while True:
        signal.pause()
finally:
    subprocess.run(['/usr/bin/systemctl', 'start', 'observability-kuma.service'], check=True)
    (root / 'backup-finalizer-ran').write_text('observer restarted by backup finalizer\n')
