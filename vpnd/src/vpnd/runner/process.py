"""Argv-only process runner with explicit capture group lifetime."""

import asyncio
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import selectors
import shlex
import signal
import subprocess
import sys
import threading


class CapturePolicy(Enum):
    FOREGROUND = "foreground"
    OWNED_PROCESS_GROUP = "owned_process_group"
    Foreground = FOREGROUND
    OwnedProcessGroup = OWNED_PROCESS_GROUP


@dataclass
class Output:
    rc: int
    stdout: str
    stderr: str


class Cmd:
    def __init__(self, program):
        self.program = str(program)
        self.argv = []
        self.environment = []
        self.removed_environment = set()
        self.directory = None
        self.description = None
        self.secrets = []
        self.policy = CapturePolicy.FOREGROUND

    @classmethod
    def new(cls, program):
        return cls(program)

    def arg(self, value):
        self.argv.append(str(value))
        return self

    def args(self, values):
        self.argv.extend(map(str, values))
        return self

    def env(self, key, value):
        self.environment.append((str(key), str(value)))
        return self

    def env_remove(self, *keys):
        self.removed_environment.update(map(str, keys))
        return self

    def cwd(self, value):
        self.directory = Path(value)
        return self

    def describe(self, value):
        self.description = str(value)
        return self

    def sensitive(self, value):
        if value:
            self.secrets.append(str(value))
        return self

    def capture_policy(self, policy):
        self.policy = CapturePolicy(policy)
        return self

    def redacted(self, value):
        for secret in self.secrets:
            value = value.replace(secret, "<redacted: secrets file path>")
        return value

    def render(self, redact=False):
        display = self.redacted if redact else str
        parts = [f"{k}={shlex.quote(display(v))}" for k, v in self.environment]
        parts += [shlex.quote(self.program)] + [shlex.quote(display(a)) for a in self.argv]
        value = " ".join(parts)
        if self.directory is not None:
            value = f"(cd {shlex.quote(str(self.directory))} && {value})"
        return value

    def explain(self):
        return self.render()

    def redacted_explain(self):
        return self.render(True)

    def print_explain(self):
        if self.description:
            print("→ " + self.redacted(self.description), file=sys.stderr)
        print("  $ " + self.redacted_explain(), file=sys.stderr)

    def _failure(self, rc):
        return RuntimeError(
            f"command failed (rc={rc}): {self.redacted(self.description or self.program)}"
        )

    def _worker(self, stopped, capture, detailed, spawn_lock=None):
        """One thread owns pipes, group cleanup and the unreaped group leader."""
        if stopped.is_set():
            return 0, b"", b""
        owned = capture and self.policy == CapturePolicy.OWNED_PROCESS_GROUP
        environment = os.environ.copy()
        for key in self.removed_environment:
            environment.pop(key, None)
        environment.update(self.environment)
        # Popen has no asyncio child watcher: the leader stays unreaped while
        # a descendant holds a pipe, reserving its PID/group ID until cleanup.
        with spawn_lock or threading.Lock():
            if stopped.is_set():
                return 0, b"", b""
            child = subprocess.Popen(
                [self.program, *self.argv],
                env=environment,
                cwd=self.directory,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.PIPE if capture and detailed else None,
                process_group=0 if owned else None,
            )
        reaped = False
        stdout = bytearray()
        stderr = bytearray()
        try:
            with selectors.DefaultSelector() as selector:
                for stream, buffer in ((child.stdout, stdout), (child.stderr, stderr)):
                    if stream is not None:
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ, buffer)
                while selector.get_map():
                    if stopped.is_set():
                        break
                    for key, _ in selector.select(timeout=0.05):
                        try:
                            chunk = os.read(key.fd, 65536)
                        except BlockingIOError:
                            continue
                        if chunk:
                            key.data.extend(chunk)
                        else:
                            selector.unregister(key.fileobj)
                # Never poll/wait while captured descriptors remain open.
                # On cancellation, kill before reaping the reserved leader.
                if stopped.is_set():
                    self._terminate(child, owned)
                while True:
                    try:
                        child.wait(timeout=0.05)
                        reaped = True
                        break
                    except subprocess.TimeoutExpired:
                        if stopped.is_set():
                            self._terminate(child, owned)
            return child.returncode, bytes(stdout), bytes(stderr)
        finally:
            if not reaped:
                self._terminate(child, owned)
                child.wait()
            for stream in (child.stdout, child.stderr):
                if stream is not None:
                    stream.close()

    @staticmethod
    def _terminate(child, owned):
        try:
            if owned:
                os.killpg(child.pid, signal.SIGKILL)
            elif child.returncode is None:
                child.kill()
        except ProcessLookupError:
            # Exiting children can disappear before the cancellation signal;
            # the owning worker still reaps its reserved leader below.
            pass

    async def _execute(self, explain, capture, detailed):
        self.print_explain()
        if explain:
            return Output(0, "", "")
        stopped = threading.Event()
        spawn_lock = threading.Lock()
        loop = asyncio.get_running_loop()
        worker = loop.create_future()

        def complete(result, error):
            if error is None:
                worker.set_result(result)
            else:
                worker.set_exception(error)

        def work():
            try:
                result = self._worker(stopped, capture, detailed, spawn_lock)
            except Exception as error:
                loop.call_soon_threadsafe(complete, None, error)
            except BaseException as error:
                # Wake the caller for every fatal worker exit, then preserve
                # thread termination instead of swallowing the exception.
                loop.call_soon_threadsafe(complete, None, error)
                raise
            else:
                loop.call_soon_threadsafe(complete, result, None)

        # A private worker starts immediately. The global asyncio executor must
        # not silently queue matrix cells, alter sweep simultaneity, or spawn
        # an expired queued job after its caller has already cancelled it.
        threading.Thread(target=work, name="vpnd-capture").start()
        try:
            returncode, stdout, stderr = await asyncio.shield(worker)
        except asyncio.CancelledError:
            # Serialize cancellation with the final stop-check and spawn. A
            # delayed worker cannot cross this boundary after cancellation.
            with spawn_lock:
                stopped.set()
            # Cancellation completes only after owned descendants are killed
            # and the direct child is reaped; no background cleanup is orphaned.
            await asyncio.shield(worker)
            raise
        rc = returncode if returncode >= 0 else -1
        if not detailed and rc:
            raise self._failure(rc)

        def lines(value):
            # Rust BufReader.lines splits LF, removes CR only before LF,
            # and restores one LF per line, including an unterminated tail.
            if not value:
                return ""
            chunks = value.decode("utf-8").split("\n")
            terminated = chunks[-1] == ""
            if terminated:
                chunks.pop()
            return "".join(
                (
                    chunk[:-1]
                    if chunk.endswith("\r") and (terminated or index < len(chunks) - 1)
                    else chunk
                )
                + "\n"
                for index, chunk in enumerate(chunks)
            )

        return Output(rc, lines(stdout), lines(stderr))

    async def run(self, explain=False):
        return (await self._execute(explain, False, False)).rc

    async def capture(self, explain=False):
        return await self._execute(explain, True, False)

    async def capture_detailed(self, explain=False):
        return await self._execute(explain, True, True)
