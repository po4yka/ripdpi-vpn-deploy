"""Real terminal boundaries for interactive authority."""

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

from vpnd.wizard import choose, confirm, prompt


def test_all_prompt_helpers_refuse_nonterminal_stderr(monkeypatch):
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    for function in (
        lambda: confirm("Proceed?"),
        lambda: prompt("Value", "default"),
        lambda: choose("Pick", ["a", "b"]),
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


def test_piped_stdin_requires_controlling_terminal_answer():
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
            assert time.monotonic() < deadline
            if select.select([terminal], [], [], 0.05)[0]:
                transcript += os.read(terminal, 8192)
        # The piped newline already exists; only this manual terminal answer
        # may decide the operation, matching console's /dev/tty fallback.
        os.write(terminal, b"n\n")
        while b"RESULT=False" not in transcript:
            assert time.monotonic() < deadline
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
