"""Read-only discovery of retained canonical subscription runtime authority.

Absence is scoped to the role's exact files and units. It is not evidence that
an unrelated nginx process reloaded after an out-of-band configuration removal.
"""
from __future__ import annotations

import inspect
import json
import os
import subprocess

from fleet_inspection import InspectionError, bounded_command


def _worker(
    paths=("/usr/local/bin/vpn-bootstrap.py", "/usr/local/sbin/vpn-sub-mirror.py",
           "/usr/local/sbin/vpn-sub-mirror.sh", "/etc/nginx/sites-enabled/vpn-sub.conf",
           "/etc/nginx/sites-available/vpn-sub.conf", "/etc/nginx/conf.d/vpn-sub-ratelimit.conf",
           "/etc/nginx/conf.d/vpn-sub-revoked.conf"),
    units=("vpn-bootstrap.service", "vpn-subscription-maintenance.service",
           "vpn-subscription-maintenance.timer", "vpn-sub-mirror.service", "vpn-sub-mirror.timer"),
    systemctl="/usr/bin/systemctl",
):
    # Arguments are internal test seams, never accepted from the remote stdin.
    import os
    import signal
    import subprocess
    import tempfile
    import time

    for path in paths:
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        return True
    environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"}
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = None
        try:
            process = subprocess.Popen(
                [systemctl, "show", "--property=Id,LoadState,ActiveState,SubState,MainPID", *units],
                stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                env=environment, start_new_session=True,
            )
            deadline = time.monotonic() + 8
            while process.poll() is None:
                if (time.monotonic() >= deadline or os.fstat(output.fileno()).st_size > 16384
                        or os.fstat(errors.fileno()).st_size > 16384):
                    raise ValueError("publisher-discovery-unconfirmed")
                time.sleep(0.01)
            output.seek(0)
            errors.seek(0)
            raw = output.read(16385)
            if process.returncode not in (0, 1) or len(raw) > 16384 or errors.read(1):
                raise ValueError("publisher-discovery-unconfirmed")
        finally:
            # Reclaim the owned group even if the command leader already exited.
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    # The owned process group already exited before the signal.
                    pass
                process.wait(timeout=2)
    records = {}
    for block in raw.decode("utf-8", errors="strict").strip().split("\n\n"):
        record = {}
        for line in block.strip().splitlines():
            key, separator, value = line.partition("=")
            if not separator or key in record:
                raise ValueError("publisher-discovery-unconfirmed")
            record[key] = value
        unit = record.get("Id")
        expected = {"Id", "LoadState", "ActiveState", "SubState"}
        if unit in units and unit.endswith(".service"):
            expected.add("MainPID")
        if unit not in units or unit in records or not expected <= set(record) <= expected | {"MainPID"}:
            raise ValueError("publisher-discovery-unconfirmed")
        if (record["LoadState"] not in {"loaded", "masked", "not-found"}
                or record["ActiveState"] not in {"active", "inactive", "failed", "activating", "deactivating", "reloading"}
                or not record["SubState"] or not record.get("MainPID", "0").isascii()
                or not record.get("MainPID", "0").isdigit() or len(record.get("MainPID", "0")) > 10):
            raise ValueError("publisher-discovery-unconfirmed")
        records[unit] = record
    if set(records) != set(units):
        raise ValueError("publisher-discovery-unconfirmed")
    return any(record["ActiveState"] != "inactive" or record["SubState"] != "dead"
               or int(record.get("MainPID", "0")) != 0 for record in records.values())


def worker_program():
    return (inspect.getsource(_worker) + "\nimport json,signal,sys\n"
            "def cancel(*args):\n    raise KeyboardInterrupt\n"
            "for name in ('SIGINT','SIGTERM','SIGHUP'):\n    signal.signal(getattr(signal,name),cancel)\n"
            "try:\n"
            "    result = _worker()\n"
            "    print(json.dumps({'schema_version':1,'active_possible':result}))\n"
            "except (Exception,KeyboardInterrupt):\n"
            "    print('publisher-discovery-unconfirmed',file=sys.stderr)\n"
            "    raise SystemExit(2)\n").encode()


def probe(host_spec, ssh_argv):
    """Return possible presence; every unreachable or ambiguous host refuses."""
    remote = "sudo -n /usr/bin/python3 -I -B -S -"
    if (not isinstance(host_spec, dict) or not isinstance(ssh_argv, list) or len(ssh_argv) < 3
            or ssh_argv[-2] != host_spec.get("transport") or ssh_argv[-1] != remote):
        raise ValueError("publisher-discovery-transport-unconfirmed")
    try:
        raw = bounded_command(ssh_argv, input_bytes=worker_program(), input_limit=16384,
                              limit=1024, timeout=30, environment=os.environ.copy())
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        result = json.loads(raw, object_pairs_hook=unique)
        if (not isinstance(result, dict) or set(result) != {"schema_version", "active_possible"}
                or type(result["schema_version"]) is not int or result["schema_version"] != 1
                or type(result["active_possible"]) is not bool):
            raise ValueError
        return result["active_possible"]
    except (InspectionError, OSError, TypeError, ValueError, subprocess.SubprocessError):
        raise ValueError("publisher-discovery-unconfirmed") from None
