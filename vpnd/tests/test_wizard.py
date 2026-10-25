"""Real terminal boundaries for interactive authority."""

import asyncio
import io
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import time

import pytest

from vpnd.wizard import confirm, confirm_async


def test_all_prompt_helpers_refuse_nonterminal_stderr(monkeypatch):
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    for function in (
        lambda: confirm("Proceed?"),
        lambda: asyncio.run(confirm_async("Proceed?")),
    ):
        with pytest.raises(OSError, match="not a terminal"):
            function()


def test_terminal_confirmation_accepts_explicit_manual_answers():
    for response, expected in ((b"n\n", "False"), (b"y\n", "True"), (b"\n", "True")):
        master, slave = pty.openpty()
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from vpnd.wizard import confirm; print(confirm('Proceed?', True))",
            ],
            stdin=slave,
            stderr=slave,
            stdout=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        )
        os.close(slave)
        try:
            os.write(master, response)
            output, _ = child.communicate(timeout=3)
            assert child.returncode == 0 and output.decode().strip() == expected
        finally:
            os.close(master)
            if child.poll() is None:
                child.kill()
            child.wait()


@pytest.mark.parametrize("asynchronous", (False, True), ids=("sync", "async"))
def test_piped_stdin_requires_controlling_terminal_answer(asynchronous):
    pid, terminal = pty.fork()
    if pid == 0:
        source = """import os
from vpnd.wizard import confirm
reader, writer = os.pipe()
os.write(writer, b"\\n")
os.close(writer)
os.dup2(reader, 0)
os.close(reader)
print("RESULT=" + str(confirm("Proceed?", True)), flush=True)
"""
        if asynchronous:
            source = source.replace("from vpnd.wizard import confirm", "import asyncio\nfrom vpnd.__main__ import _terminal_loop\nfrom vpnd.wizard import confirm_async")
            source = source.replace('confirm("Proceed?", True)', 'asyncio.run(confirm_async("Proceed?", True), loop_factory=_terminal_loop)')
        os.execvpe(
            sys.executable,
            [sys.executable, "-c", source],
            {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        )
    reaped = False
    try:
        transcript = b""
        deadline = time.monotonic() + 3
        while b"Proceed?" not in transcript:
            assert time.monotonic() < deadline, transcript
            if select.select([terminal], [], [], 0.05)[0]:
                transcript += os.read(terminal, 8192)
        # The piped newline already exists; only this manual terminal answer
        # may decide the operation, matching console's /dev/tty fallback.
        os.write(terminal, b"n\n")
        while b"RESULT=False" not in transcript:
            assert time.monotonic() < deadline, transcript
            if select.select([terminal], [], [], 0.05)[0]:
                transcript += os.read(terminal, 8192)
        _, status = os.waitpid(pid, 0)
        reaped = True
        assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    finally:
        os.close(terminal)
        if not reaped:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)


@pytest.mark.parametrize("owned", (False, True), ids=("stdin", "controlling-terminal"))
@pytest.mark.parametrize("ending", ("cancel", "eof", "answer", "registration-error"))
def test_async_reader_releases_terminal_resources(monkeypatch, owned, ending):
    import fcntl
    import termios
    from vpnd.wizard import async_prompts

    master, slave = pty.openpty()
    stdin = os.fdopen(os.dup(slave), encoding="utf-8")
    stderr = os.fdopen(os.open(os.ttyname(slave), os.O_WRONLY), "w", encoding="utf-8")
    original_flags = fcntl.fcntl(stdin.fileno(), fcntl.F_GETFL)
    opened = []
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(sys, "stdin", io.StringIO() if owned else stdin)
    real_open = os.open

    def open_terminal(path, flags):
        assert path == ("/dev/tty" if owned else os.ttyname(slave))
        assert flags & os.O_NONBLOCK and flags & os.O_NOCTTY
        fd = real_open(os.ttyname(slave), flags)
        opened.append(fd)
        return fd

    monkeypatch.setattr(async_prompts.os, "open", open_terminal)

    async def exercise():
        loop = asyncio.get_running_loop()
        registered = asyncio.Event()
        removed = []
        real_add, real_remove = loop.add_reader, loop.remove_reader

        def add_reader(fd, callback):
            if ending == "registration-error":
                raise OSError("reader registration failed")
            real_add(fd, callback)
            registered.set()

        def remove_reader(fd):
            removed.append(fd)
            return real_remove(fd)

        monkeypatch.setattr(loop, "add_reader", add_reader)
        monkeypatch.setattr(loop, "remove_reader", remove_reader)
        task = asyncio.create_task(async_prompts.terminal_line("Answer? "))
        if ending == "registration-error":
            with pytest.raises(OSError, match="reader registration failed"):
                await task
            assert not removed
            return
        await registered.wait()
        fd = opened[0]
        assert fcntl.fcntl(stdin.fileno(), fcntl.F_GETFL) == original_flags
        assert fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_NONBLOCK
        if ending == "cancel":
            attributes = termios.tcgetattr(slave)
            attributes[3] &= ~termios.ICANON
            termios.tcsetattr(slave, termios.TCSANOW, attributes)
            consumed = asyncio.Event()
            real_read = os.read

            def read(fd, length):
                chunk = real_read(fd, length)
                if chunk:
                    consumed.set()
                return chunk

            monkeypatch.setattr(async_prompts.os, "read", read)
            os.write(master, b"y")
            await consumed.wait()
            assert not task.done()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif ending == "eof":
            os.write(master, b"\x04")
            with pytest.raises(EOFError, match="terminal input closed"):
                await task
        else:
            os.write(master, "héllo\nnext\n".encode())
            assert await task == "héllo"
            assert os.read(stdin.fileno(), 5) == b"next\n"
        assert removed == [fd]

    try:
        asyncio.run(exercise())
        assert fcntl.fcntl(stdin.fileno(), fcntl.F_GETFL) == original_flags
        for fd in opened:
            with pytest.raises(OSError):
                os.fstat(fd)
    finally:
        stdin.close()
        stderr.close()
        os.close(slave)
        os.close(master)


def test_async_confirmation_defaults_and_invalid_answers(monkeypatch):
    from vpnd.wizard import async_prompts

    prompts = []
    answers = iter(("invalid", "", "", " YES ", " No "))

    async def answer(label):
        prompts.append(label)
        return next(answers)

    monkeypatch.setattr(async_prompts, "terminal_line", answer)

    async def exercise():
        assert not await async_prompts.confirm_async("Review?", default=False)
        assert await async_prompts.confirm_async("Proceed?")
        assert await async_prompts.confirm_async("Review?", default=False)
        assert not await async_prompts.confirm_async("Proceed?")

    asyncio.run(exercise())
    assert prompts == ["Review? [y/N] ", "Review? [y/N] ", "Proceed? [Y/n] ",
                       "Review? [y/N] ", "Proceed? [Y/n] "]


def test_async_reader_rejects_a_changed_stdin_terminal(monkeypatch):
    from vpnd.wizard import async_prompts

    master, slave = pty.openpty()
    other_master, other_slave = pty.openpty()
    stdin = os.fdopen(os.dup(slave), encoding="utf-8")
    stderr = os.fdopen(os.open(os.ttyname(slave), os.O_WRONLY), "w", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stderr", stderr)
    real_open = os.open
    opened = []

    def changed_terminal(path, flags):
        assert path == os.ttyname(slave)
        fd = real_open(os.ttyname(other_slave), flags)
        opened.append(fd)
        return fd

    monkeypatch.setattr(async_prompts.os, "open", changed_terminal)
    try:
        with pytest.raises(OSError, match="terminal input changed"):
            asyncio.run(async_prompts.terminal_line("Answer? "))
        assert len(opened) == 1
        with pytest.raises(OSError):
            os.fstat(opened[0])
        assert os.isatty(stdin.fileno())
    finally:
        stdin.close()
        stderr.close()
        for fd in (master, slave, other_master, other_slave):
            os.close(fd)
