"""Shared bounded bootstrap checks; callers own selection and SSH trust policy."""

from contextlib import contextmanager
import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time


REMOTE_WAIT = """timeout --kill-after=1 5 cloud-init status --wait >/dev/null 2>&1
case "$?" in
  0) test -f /var/lib/cloud-init-vpn-bootstrap.done || exit 22 ;;
  1) exit 20 ;;
  2) exit 23 ;;
  124|137) exit 21 ;;
  *) exit 24 ;;
esac
"""
_cancelled = 0


class ReadinessError(Exception):
    """Only categorical messages, never remote output or private paths."""


class CommandTimeout(ReadinessError):
    """A bounded local subprocess exceeded its session deadline."""


class SshTransportError(ReadinessError):
    """A pinned SSH/SFTP transport failed before a semantic reply."""


def check_cancelled():
    if _cancelled:
        raise SystemExit(128 + _cancelled)


@contextmanager
def cancellation(signals=(signal.SIGINT, signal.SIGTERM)):
    global _cancelled
    _cancelled = 0
    def interrupted(signum, _frame):
        global _cancelled
        _cancelled = signum
    previous = {sig: signal.signal(sig, interrupted) for sig in signals}
    try:
        yield
        check_cancelled()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


# The session leader stays alive after the command exits, retaining the group
# identity until its owner signals cleanup. Only this supervisor inherits the
# status/control descriptors; the command receives its original stdio and argv.
_SESSION_SUPERVISOR = r"""
import os, selectors, signal, subprocess, sys
status, control = map(int, sys.argv[1:3])
try:
    try:
        command = subprocess.Popen(sys.argv[3:], close_fds=True)
    except OSError:
        command = None
        os.write(status, b"unavailable\n")
    reported = command is None
    with selectors.DefaultSelector() as selector:
        selector.register(control, selectors.EVENT_READ)
        while True:
            if not reported:
                result = command.poll()
                if result is not None:
                    os.write(status, str(result).encode("ascii") + b"\n")
                    reported = True
            if selector.select(0.01) and not os.read(control, 1):
                break
finally:
    os.killpg(os.getpgrp(), signal.SIGKILL)
"""


def run_command(command, *, timeout, environment=None, cwd=None, capture=False, stream=False,
                input_data=None, defer_cancellation=False, output_limit=65536, forward_stderr=False,
                stderr_output=None):
    """Bound an owned session, retaining its leader until descendants stop."""
    if not defer_cancellation:
        check_cancelled()
    if type(output_limit) is not int or not 1 <= output_limit <= 1_049_600:
        raise ReadinessError("command output limit invalid")
    if input_data is not None and (type(input_data) is not bytes or len(input_data) > 65536):
        raise ReadinessError("command input invalid")
    if stderr_output is not None and (not capture or type(stderr_output) is not bytearray):
        raise ReadinessError("command stderr capture invalid")
    output = bytearray()
    target = subprocess.PIPE if capture else (None if stream else subprocess.DEVNULL)
    input_stream, descriptors = None, []
    try:
        if input_data is not None:
            input_stream = tempfile.TemporaryFile()
            input_stream.write(input_data)
            input_stream.seek(0)
        status_read, status_write = os.pipe()
        descriptors.extend((status_read, status_write))
        control_read, control_write = os.pipe()
        descriptors.extend((control_read, control_write))
        child = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", _SESSION_SUPERVISOR,
             str(status_write), str(control_read), *command],
            stdin=input_stream or subprocess.DEVNULL, stdout=target, stderr=target,
            env=environment, cwd=cwd, start_new_session=True,
            pass_fds=(status_write, control_read),
        )
    except OSError:
        for descriptor in descriptors:
            os.close(descriptor)
        if input_stream is not None:
            input_stream.close()
        raise ReadinessError("command unavailable") from None
    signal_attempted = False

    def stop_group():
        nonlocal signal_attempted
        signal_attempted = True
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            # The still-owned session has exited; no process group remains.
            pass
        except OSError:
            raise ReadinessError("command cleanup unavailable") from None

    try:
        for descriptor in (status_write, control_read):
            os.close(descriptor)
            descriptors.remove(descriptor)
        deadline = time.monotonic() + timeout
        status, reply, total = None, bytearray(), 0
        with selectors.DefaultSelector() as selector:
            os.set_blocking(status_read, False)
            selector.register(status_read, selectors.EVENT_READ)
            if capture:
                for pipe in (child.stdout, child.stderr):
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ)
            while True:
                if not defer_cancellation:
                    check_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CommandTimeout("session timeout")
                for key, _event in selector.select(min(0.1, remaining)):
                    try:
                        data = os.read(key.fd, 4096)
                    except (BlockingIOError, InterruptedError):
                        continue
                    if key.fd == status_read:
                        reply.extend(data)
                        if not data or len(reply) > 64:
                            raise ReadinessError("command supervisor unavailable")
                        if not reply.endswith(b"\n"):
                            continue
                        if reply == b"unavailable\n":
                            raise ReadinessError("command unavailable")
                        value = reply[:-1]
                        digits = value[1:] if value.startswith(b"-") else value
                        if not digits.isdigit() or not -255 <= int(value) <= 255:
                            raise ReadinessError("command supervisor unavailable")
                        status = int(value)
                        selector.unregister(status_read)
                        stop_group()
                        continue
                    if not data:
                        selector.unregister(key.fileobj)
                    total += len(data)
                    if total > output_limit:
                        raise ReadinessError("command output limit")
                    if key.fileobj is child.stdout:
                        output.extend(data)
                    else:
                        if stderr_output is not None:
                            stderr_output.extend(data)
                        if forward_stderr:
                            sys.stderr.buffer.write(data)
                            sys.stderr.buffer.flush()
                if status is not None and not selector.get_map():
                    return status, bytes(output)
    finally:
        try:
            if not signal_attempted:
                stop_group()
        finally:
            # EOF also asks the still-owned supervisor to reclaim its session
            # if the owner's signal failed or the owner disappeared.
            os.close(control_write)
            descriptors.remove(control_write)
            try:
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        child.kill()
                        child.wait(timeout=1)
                    except (OSError, subprocess.TimeoutExpired):
                        raise ReadinessError("command cleanup unavailable") from None
                    raise ReadinessError("command cleanup unavailable") from None
            finally:
                for descriptor in descriptors:
                    os.close(descriptor)
                if input_stream is not None:
                    input_stream.close()
                if capture:
                    child.stdout.close()
                    child.stderr.close()


def wait_for_bootstrap(ssh, *, environment=None, first_boot=False):
    """ssh is an already validated argv prefix, without a remote command."""
    if first_boot:
        probe = ["ConnectTimeout=5" if argument == "ConnectTimeout=10" else argument for argument in ssh]
        for _attempt in range(30):
            try:
                status, _ = run_command([*probe, "true"], timeout=15, environment=environment)
            except CommandTimeout:
                raise SshTransportError("SSH session timeout") from None
            if status == 0:
                break
            until = time.monotonic() + 5
            while time.monotonic() < until:
                check_cancelled()
                time.sleep(min(0.1, max(0, until - time.monotonic())))
        else:
            raise SshTransportError("SSH did not come up after 30 attempts")
    for _attempt in range(30):
        try:
            status, _ = run_command([*ssh, REMOTE_WAIT], timeout=10, environment=environment)
        except CommandTimeout:
            raise SshTransportError("SSH session timeout") from None
        if status == 0:
            return
        if status == 21:
            continue
        semantic = {20: "cloud-init error", 23: "cloud-init recoverable error",
                    22: "bootstrap marker missing", 24: "cloud-init status unavailable"}
        if status not in semantic:
            raise SshTransportError("bootstrap SSH transport failure")
        raise ReadinessError(semantic[status])
    raise ReadinessError("cloud-init timeout: still waiting after 30 bounded attempts")


def main():
    # Only the existing Terraform first-boot adapter uses accept-new. Deployment
    # supplies the canonical strict SSH prefix instead, without this CLI path.
    address, user, port, key = sys.argv[1:]
    ssh = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes",
           "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
           "-o", "StrictHostKeyChecking=accept-new",
           "-o", "ConnectTimeout=10", "-p", port, "-i", key, user + "@" + address]
    try:
        with cancellation():
            print("waiting for SSH and bootstrap…", flush=True)
            wait_for_bootstrap(ssh, first_boot=True)
            print("bootstrap ready", flush=True)
    except ReadinessError as error:
        print("error: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
