#!/usr/bin/env python3
"""Inspect one legacy managed policy through source-bound pinned public SSH."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(environment):
    spec = importlib.util.spec_from_file_location('policy_bootstrap', ROOT/'scripts/bootstrap-tailnet.py')
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    with tempfile.TemporaryDirectory(prefix='vpn-policy-inspect-') as directory:
        inputs = controller.load_inputs(environment, Path(directory).resolve())
        from bootstrap_readiness import ReadinessError
        try:
            plan = controller.inspect_policy(inputs)
        except ReadinessError:
            raise ValueError('policy-transport-refused') from None
        output = Path(inputs.config['output'])
        parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(parent_fd)
            if (info.st_dev, info.st_ino) != inputs.output_parent_identity:
                raise ValueError('policy-output-parent-changed')
            controller._verify_inputs(inputs)
            controller._require_source(inputs)
            fd = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(json.dumps(plan, sort_keys=True).encode()+b'\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    return {'status': 'inspected', 'plan_sha256': plan['plan_sha256'], 'guest_changes': 'not-performed'}


if __name__ == '__main__':
    try:
        print(json.dumps(run(dict(os.environ)), sort_keys=True))
    except (OSError, ValueError, RuntimeError, TypeError, KeyError):
        print(json.dumps({'status': 'refused', 'reason': 'policy-inspection-refused'}))
        raise SystemExit(1) from None
