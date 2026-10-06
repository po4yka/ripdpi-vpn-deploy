#!/usr/bin/env python3
"""Render one private source-bound console ingress capability, without SSH."""
from __future__ import annotations

import ast
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import time
from uuid import UUID
import zlib

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'schema_version', 'bootstrap_config', 'hostname', 'root_filesystem_uuid', 'expires_at', 'output'}


class Refusal(ValueError):
    """Public categorical failure, never private input."""


def bootstrap_module():
    spec = importlib.util.spec_from_file_location('console_bootstrap_controller', ROOT/'scripts/bootstrap-tailnet.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(environment):
    controller = bootstrap_module()
    raw, request_fence = controller.deploy.read_fenced_input(
        environment['CONSOLE_BOOTSTRAP_CONFIG'], private=True, exact_mode=0o600,
    )
    value = controller.inspection.decode_json(raw)
    if set(value) != FIELDS or value['schema_version'] != 1 or type(value['schema_version']) is not int:
        raise Refusal('console-render-input-refused')
    if (not isinstance(value['hostname'], str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', value['hostname'])
            or str(UUID(value['root_filesystem_uuid'])) != value['root_filesystem_uuid']
            or type(value['expires_at']) is not int or not 0 < value['expires_at']-time.time() <= 900):
        raise Refusal('console-render-input-refused')
    output = controller._output_path(value['output'])
    parent = output.parent.stat()
    import tempfile
    with tempfile.TemporaryDirectory(prefix='vpn-console-render-') as work:
        directory = Path(work).resolve()
        directory.chmod(0o700)
        raw_config, config_fence = controller.deploy.read_fenced_input(value['bootstrap_config'], private=True, exact_mode=0o600)
        config = controller.inspection.decode_json(raw_config)
        child = {**environment, 'BOOTSTRAP_TARGET': config['inventory_alias'],
                 'TAILNET_BOOTSTRAP_CONFIG': value['bootstrap_config']}
        inputs = controller.load_inputs(child, directory)
        if inputs.host['name'] != value['hostname']:
            raise Refusal('console-render-target-refused')
        request = {'schema_version': 1, 'nonce': secrets.token_hex(16),
                   'hostname': value['hostname'], 'root_filesystem_uuid': value['root_filesystem_uuid'],
                   'host_key_sha256': config['host_key_sha256'], 'inventory_alias': config['inventory_alias'],
                   'public_address': config['public_address'], 'ssh_port': config['ssh_port'],
                   'public_sources': config['public_sources'], 'source_revision': config['source_revision'],
                   'deployable_digest': config['deployable_digest'], 'expires_at': value['expires_at']}
        source_raw, source_fence = controller.deploy.read_fenced_input(ROOT/'scripts/console_bootstrap_guest.py')
        source = source_raw.decode('utf-8')
        ast.parse(source)
        package = ("scope={'__name__':'vpn_console_guest'}\nexec("+repr(source)+",scope)\n"
                   "scope['boot']("+repr(request)+','+repr(source)+')\n')
        ast.parse(package)
        token = base64.b64encode(zlib.compress(package.encode(), 9)).decode()
        command = 'python3 -I -B -c "import base64,zlib;exec(zlib.decompress(base64.b64decode(\''+token+'\')))"\n'
        if output == Path(inputs.config['output']):
            raise Refusal('console-render-output-collision')
        for fence in [request_fence, config_fence, source_fence, *inputs.fences]:
            controller.deploy.verify_input_fence(fence)
        current = controller.deploy.source_identity(ROOT, inputs.environment, require_clean=True)
        if current != {'DEPLOY_SOURCE_REVISION': request['source_revision'], 'DEPLOYABLE_SOURCE_DIGEST': request['deployable_digest']}:
            raise Refusal('console-render-source-refused')
        now = output.parent.stat()
        if (now.st_dev, now.st_ino) != (parent.st_dev, parent.st_ino) or time.time() >= request['expires_at']:
            raise Refusal('console-render-output-refused')
        parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(parent_fd)
            if (opened.st_dev, opened.st_ino) != (parent.st_dev, parent.st_ino):
                raise Refusal('console-render-output-refused')
            fd = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
            with os.fdopen(fd, 'w') as stream:
                stream.write(command)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    return {'status': 'rendered', 'execution': 'not-performed', 'network_changes': 'not-performed'}


def main():
    try:
        print(json.dumps(render(dict(os.environ))))
        return 0
    except (Refusal, OSError, ValueError, KeyError, TypeError, UnicodeError):
        print(json.dumps({'status': 'refused', 'reason': 'console-render-refused'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
