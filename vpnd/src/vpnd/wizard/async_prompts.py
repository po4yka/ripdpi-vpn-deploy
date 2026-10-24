"""Terminal confirmation with cancellable, unbuffered input."""

import asyncio
import os
import sys


async def terminal_line(label):
    """Read one line without consuming the next prompt's terminal answer."""
    if not sys.stderr.isatty():
        raise OSError("not a terminal")
    terminal_stdin = sys.stdin.isatty()
    stdin_fd = sys.stdin.fileno() if terminal_stdin else None
    path = os.ttyname(stdin_fd) if stdin_fd is not None else "/dev/tty"
    encoding = sys.stdin.encoding or "utf-8" if terminal_stdin else "utf-8"
    errors = sys.stdin.errors or "strict" if terminal_stdin else "strict"
    loop = asyncio.get_running_loop()
    answer = loop.create_future()
    data = bytearray()
    # A dup would share stdin's open file description. Open the same terminal
    # independently so even SIGKILL cannot leave the parent's stdin nonblocking.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)
    registered = False

    def readable():
        if answer.done():
            return
        try:
            # Read only one byte: a second queued answer belongs to the next
            # confirmation. O_NONBLOCK also protects noncanonical partial input.
            chunk = os.read(fd, 1)
        except BlockingIOError:
            return
        except OSError as error:
            answer.set_exception(error)
            return
        if not chunk or chunk == b"\n":
            if not chunk and not data:
                answer.set_exception(EOFError("terminal input closed"))
            else:
                answer.set_result(bytes(data))
        else:
            data.extend(chunk)

    try:
        if stdin_fd is not None:
            original, reopened = os.fstat(stdin_fd), os.fstat(fd)
            if not os.path.samestat(original, reopened) or original.st_rdev != reopened.st_rdev:
                raise OSError("terminal input changed while opening it")
        loop.add_reader(fd, readable)
        registered = True
        print(label, end="", file=sys.stderr, flush=True)
        return (await answer).decode(encoding, errors).rstrip("\r\n")
    finally:
        try:
            if registered:
                loop.remove_reader(fd)
        finally:
            os.close(fd)


async def confirm_async(label, default=True):
    while True:
        response = (await terminal_line(label + (" [Y/n] " if default else " [y/N] ")))
        response = response.strip().lower()
        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
