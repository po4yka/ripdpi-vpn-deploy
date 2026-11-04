"""Read-only admission and native verification of the baseline module policy."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

POLICY = Path('/etc/modprobe.d/90-vpn-unused-modules.conf')
RECEIPT = Path('/var/lib/vpn-baseline/unused-modules.sha256')
SYS_MODULE = Path('/sys/module')
BUILTIN = Path('/lib/modules') / os.uname().release / 'modules.builtin'
BOOT = Path('/boot')
CONTAINER = Path('/.dockerenv')


def owned_bytes(path: Path, mode: int) -> bytes:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != mode or info.st_size > 65536):
        raise ValueError('unsafe-policy-file')
    return path.read_bytes()


def modules(policy: bytes) -> list[str]:
    names = re.findall(r'^blacklist ([a-z0-9_]+)$', policy.decode('ascii'), re.M)
    if not names or len(names) != len(set(names)):
        raise ValueError('invalid-module-policy')
    return names


def admit(names: list[str]) -> None:
    present = {entry.name.replace('-', '_') for entry in SYS_MODULE.iterdir()}
    if BUILTIN.is_file():
        present.update(Path(line).name.split('.ko')[0].replace('-', '_')
                       for line in BUILTIN.read_text().splitlines())
    elif not CONTAINER.is_file():
        # Containers share another kernel and do not prove host kernel admission.
        raise ValueError('missing-built-in-module-metadata')
    if present.intersection(names):
        raise ValueError('denied-module-present')


def native(argv: list[str]) -> str:
    return subprocess.run(argv, check=True, capture_output=True, text=True,
                          timeout=60).stdout


def effective(policy: bytes) -> None:
    names = modules(policy)
    admit(names)
    if owned_bytes(POLICY, 0o644) != policy:
        raise ValueError('module-policy-mismatch')
    configuration = {' '.join(line.split())
                     for line in native(['modprobe', '--showconfig']).splitlines()}
    for name in names:
        if not {f'blacklist {name}', f'install {name} /bin/false'} <= configuration:
            raise ValueError('ineffective-module-configuration')
        lines = [' '.join(line.split()) for line in
                 native(['modprobe', '--dry-run', '--verbose', '--', name]).splitlines()
                 if line.strip()]
        inserted = {Path(line.split()[1]).name.split('.ko')[0].replace('-', '_')
                    for line in lines if line.startswith('insmod ')}
        if not lines or lines[-1] != 'install /bin/false' or name in inserted:
            raise ValueError('ineffective-module-denial')


def image_state(policy: bytes) -> tuple[int, bool]:
    images = sorted(BOOT.glob('initrd.img-*'))
    missing = False
    for image in images:
        info = image.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError('unsafe-initramfs-image')
        if shutil.disk_usage('/var/tmp').free < max(536870912, info.st_size * 20):
            raise ValueError('insufficient-initramfs-verification-space')
        # The native extractor handles early/main segments. Keep all extracted
        # data and its intermediate archives private on the guest, then remove it.
        with tempfile.TemporaryDirectory(prefix='vpn-module-policy-', dir='/var/tmp') as directory:
            subprocess.run(['unmkinitramfs', str(image), directory], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180,
                           env={**os.environ, 'TMPDIR': directory})
            root = Path(directory)
            relative = 'etc/modprobe.d/90-vpn-unused-modules.conf'
            candidates = [root / relative, *root.glob('*/' + relative)]
            found = [path for path in candidates if path.exists() or path.is_symlink()]
            if not found or any(owned_bytes(path, 0o644) != policy for path in found):
                missing = True
    return len(images), missing


def state(policy: bytes) -> dict:
    digest = hashlib.sha256(policy).hexdigest()
    try:
        receipt = owned_bytes(RECEIPT, 0o600).decode('ascii')
    except FileNotFoundError:
        receipt = None
    count, missing = image_state(policy)
    return {'digest': digest, 'images': count, 'missing_policy': missing,
            'refresh_required': receipt != digest + '\n' or missing}


def main() -> None:
    policy = sys.stdin.buffer.read(65537)
    names = modules(policy)
    mode = sys.argv[1]
    if mode == 'admit':
        admit(names)
    elif mode == 'effective':
        effective(policy)
    elif mode == 'status':
        print(json.dumps(state(policy)))
    elif mode == 'images':
        if image_state(policy)[1]:
            raise ValueError('initramfs-policy-missing')
    elif mode == 'verify':
        effective(policy)
        if state(policy)['refresh_required']:
            raise ValueError('module-policy-not-acknowledged')
    else:
        raise ValueError('invalid-check-mode')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'module-policy-check-failed: {type(error).__name__}', file=sys.stderr)
        sys.exit(1)
