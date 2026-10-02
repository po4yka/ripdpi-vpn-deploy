#!/usr/bin/env python3
"""Exercise the production extractor under the actual Linux restore capability set."""

import io
import json
import os
from pathlib import Path
import runpy
import stat
import tarfile
import tempfile


def main():
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    expected = (1 << 0) | (1 << 2)  # CAP_CHOWN | CAP_DAC_READ_SEARCH
    for field in ('CapEff', 'CapPrm', 'CapBnd'):
        assert int(status[field].strip(), 16) == expected, field
    assert int(status['NoNewPrivs'].strip()) == 1
    extract = runpy.run_path('/usr/local/libexec/observability-kuma-backup.py')['extract_private']
    parent = Path('/var/lib/observability-kuma-restores')
    destination = Path(tempfile.mkdtemp(prefix='capability-proof-', dir=parent))
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name in ('.', './nested'):
            member = tarfile.TarInfo(name)
            member.type = tarfile.DIRTYPE
            member.mode = 0o700
            archive.addfile(member)
        for name, payload in (('./nested/kuma.db', b'bounded-extractor-proof'), ('./later/child.bin', b'later-write-proof')):
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    stream.seek(0)
    extract(stream, destination)
    assert (destination / 'nested/kuma.db').read_bytes() == b'bounded-extractor-proof'
    assert (destination / 'later/child.bin').read_bytes() == b'later-write-proof'
    for path in (destination, destination / 'nested', destination / 'later', destination / 'nested/kuma.db', destination / 'later/child.bin'):
        info = path.stat()
        assert (info.st_uid, info.st_gid) == (1000, 1000)
        assert stat.S_IMODE(info.st_mode) == (0o700 if path.is_dir() else 0o600)
    # This would succeed with CAP_DAC_OVERRIDE: verify the actual kernel
    # enforces the permission boundary after the final ownership handoff.
    try:
        fd = os.open(destination / 'forbidden-after-handoff', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except PermissionError:
        pass
    else:
        os.close(fd)
        raise AssertionError('DAC write boundary was not enforced')
    print(json.dumps({'production_extractor': 'passed', 'capabilities': 'CHOWN|DAC_READ_SEARCH', 'dac_override': False, 'root_member_then_nested_write': 'passed', 'final_owner': 1000}))


if __name__ == '__main__':
    main()
