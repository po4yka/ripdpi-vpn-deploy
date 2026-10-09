#!/usr/bin/env python3
"""Fixture-only failed policy diagnosis; emit technical keys, never values."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import time

HELPER = "/usr/local/libexec/vpn-baseline-sysctl"
DEADLINE_SECONDS = 60


def category(message):
    for fragment, name in (
        ("read-only file system", "read-only"),
        ("permission denied", "permission-denied"),
        ("no such file", "unavailable"),
        ("invalid argument", "invalid-setting"),
    ):
        if fragment in message.lower():
            return name
    return "other"


def keys(message):
    names = re.findall(r'(?:setting|on)\s+key\s+["\']?([A-Za-z0-9_./*-]+)', message)
    names += re.findall(r"/proc/sys/([A-Za-z0-9_./*-]+)", message)
    return sorted({name.replace("/", ".")[:256] for name in names})[:16] or [
        "unidentified"
    ]


def main():
    failed = []
    deadline = time.monotonic() + DEADLINE_SECONDS
    status = "diagnostic-unavailable"
    try:
        loader = importlib.machinery.SourceFileLoader("fixture_baseline_sysctl", HELPER)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        policies = module.sources()
        if len(policies) > 64:
            raise ValueError("diagnostic-limit")

        def invoke(argv, *, pass_fds=()):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("diagnostic-limit")
            result = subprocess.run(
                ["/usr/sbin/sysctl", *argv],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                pass_fds=pass_fds,
                timeout=min(10, remaining),
                env={**os.environ, "LC_ALL": "C"},
            )
            if result.returncode:
                # stdout contains key=value and is deliberately never emitted.
                message = result.stderr[:65536]
                failed.append(
                    {
                        "keys": keys(message),
                        "category": category(message),
                        "rc": result.returncode,
                    }
                )
            return result.returncode == 0

        module.invoke = invoke
        status = "replay-completed"
        module.apply(policies)
    except RuntimeError:
        status = "mandatory-failure-reproduced"
    except (OSError, ValueError, TimeoutError, subprocess.SubprocessError):
        status = "diagnostic-unavailable"
    print(json.dumps({"status": status, "failed_calls": failed[:32]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
