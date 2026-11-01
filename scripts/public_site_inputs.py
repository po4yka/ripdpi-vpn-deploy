"""Read one bounded operator-owned static tree without following links."""

import hashlib
import os
from pathlib import Path
import stat


class SiteInputError(ValueError):
    """Categorical input errors with no local paths or file contents."""


def read_site(value):
    if (not isinstance(value, str) or not Path(value).is_absolute()
            or str(Path(value)) != value or ".." in Path(value).parts
            or any(ord(char) < 32 or ord(char) == 127
                   or 0xD800 <= ord(char) <= 0xDFFF for char in value)):
        raise SiteInputError("public site directory must be an absolute normalized path")
    entries, fingerprints, total = {}, [], 0

    def identity(info):
        return (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def walk(fd, relative, depth):
        nonlocal total
        before = os.fstat(fd)
        if (before.st_uid != os.geteuid() or before.st_mode & 0o022
                or not (stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode))):
            raise SiteInputError("unsafe public site entry")
        if len(entries) >= 1024 or depth > 16:
            raise SiteInputError("public site tree exceeds its entry or depth limit")
        if stat.S_ISDIR(before.st_mode):
            entries[relative] = None
            with os.scandir(fd) as iterator:
                names = []
                for item in iterator:
                    names.append(item.name)
                    if len(names) > 1024:
                        raise SiteInputError("public site tree exceeds its entry limit")
            for name in sorted(names):
                if name.startswith('.') or any(ord(char) < 32 or ord(char) == 127 for char in name):
                    raise SiteInputError("unsafe public site entry name")
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                try:
                    walk(child, str(Path(relative) / name), depth + 1)
                finally:
                    os.close(child)
        else:
            if before.st_nlink != 1 or before.st_size > 4 * 1024 * 1024:
                raise SiteInputError("unsafe or oversized public site file")
            with os.fdopen(os.dup(fd), "rb") as stream:
                data = stream.read(4 * 1024 * 1024 + 1)
            total += len(data)
            if len(data) > 4 * 1024 * 1024 or total > 16 * 1024 * 1024:
                raise SiteInputError("public site tree exceeds its byte limit")
            entries[relative] = data
        if identity(before) != identity(os.fstat(fd)):
            raise SiteInputError("public site changed while reading")
        content = entries[relative]
        fingerprints.append((relative, identity(before),
                             hashlib.sha256(content).digest() if content is not None else None))

    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in Path(value).parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            if info.st_uid not in (0, os.geteuid()) or (info.st_mode & 0o022 and not sticky_root):
                raise SiteInputError("unsafe public site ancestry")
            fingerprints.append(("ancestor", info.st_dev, info.st_ino, info.st_uid, info.st_mode))
        walk(fd, ".", 0)
        if entries.get("404.html") is None:
            raise SiteInputError("public site requires a regular 404.html")
        return entries, fingerprints
    except OSError:
        raise SiteInputError("unreadable or unsafe public site") from None
    finally:
        os.close(fd)
