"""Publish one new recipient artifact through private directory authority."""
import os
from pathlib import Path
import stat


def publish(destination, payload):
    path = Path(os.path.abspath(destination))
    repository = Path(__file__).resolve().parents[1]
    if path.is_relative_to(repository) and not path.is_relative_to(repository / 'secrets/local'):
        raise ValueError('unsafe-recipient-output')
    for directory in (path.parent, *path.parent.parents):
        info = directory.lstat()
        sticky = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid())
                or (info.st_mode & 0o022 and not sticky)):
            raise ValueError('unsafe-recipient-output')
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    descriptor = None
    created = None
    complete = False
    try:
        directory = os.fstat(parent)
        if directory.st_uid != os.getuid() or stat.S_IMODE(directory.st_mode) != 0o700:
            raise ValueError('unsafe-recipient-output')
        descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
        created = os.fstat(descriptor)
        remaining = memoryview(payload.encode())
        while remaining:
            count = os.write(descriptor, remaining)
            if count <= 0:
                raise OSError('recipient-publication-refused')
            remaining = remaining[count:]
        os.fsync(descriptor)
        current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        current_directory = path.parent.lstat()
        if ((current.st_dev, current.st_ino) != (created.st_dev, created.st_ino)
                or (current_directory.st_dev, current_directory.st_ino) != (directory.st_dev, directory.st_ino)):
            raise ValueError('recipient-output-changed')
        os.fsync(parent)
        complete = True
    finally:
        if not complete and created is not None:
            try:
                current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                    os.unlink(path.name, dir_fd=parent)
            except FileNotFoundError:
                pass
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)
