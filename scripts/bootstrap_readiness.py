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


def check_cancelled():
    if _cancelled:
        raise SystemExit(128 + _cancelled)


@contextmanager
def cancellation():
    global _cancelled
    _cancelled = 0
    def interrupted(signum, _frame):
        global _cancelled
        _cancelled = signum
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
        check_cancelled()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def run_command(command, *, timeout, environment=None, cwd=None, capture=False, stream=False,
                input_data=None, defer_cancellation=False):
    """Bound the owned process group, including spawn-window cancellation.

    Bootstrap discards output. Small local metadata queries use bounded capture.
    Ansible can stream its ordinary reviewed output with debugging disabled.
    """
    if not defer_cancellation:
        check_cancelled()
    if input_data is not None and (type(input_data) is not bytes or len(input_data) > 65536):
        raise ReadinessError("command input invalid")
    output = bytearray()
    target = subprocess.PIPE if capture else (None if stream else subprocess.DEVNULL)
    input_stream = None
    try:
        if input_data is not None:
            # Anonymous private backing avoids pipe-capacity deadlocks while
            # keeping transaction nonces out of argv, environment and logs.
            input_stream = tempfile.TemporaryFile()
            input_stream.write(input_data)
            input_stream.seek(0)
        child = subprocess.Popen(command, stdin=input_stream or subprocess.DEVNULL, stdout=target, stderr=target,
                                 env=environment, cwd=cwd, start_new_session=True)
    except OSError:
        if input_stream is not None:
            input_stream.close()
        raise ReadinessError("command unavailable") from None
    try:
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            if capture:
                for pipe in (child.stdout, child.stderr):
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ)
            total = 0
            while True:
                if not defer_cancellation:
                    check_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ReadinessError("session timeout")
                if capture:
                    for key, _event in selector.select(min(0.1, remaining)):
                        data = os.read(key.fd, 4096)
                        if not data:
                            selector.unregister(key.fileobj)
                        total += len(data)
                        if total > 65536:
                            raise ReadinessError("command output limit")
                        if key.fileobj is child.stdout:
                            output.extend(data)
                    if child.poll() is not None and not selector.get_map():
                        return child.returncode, bytes(output)
                else:
                    try:
                        return child.wait(timeout=min(0.1, remaining)), b""
                    except subprocess.TimeoutExpired:
                        continue
    finally:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            # The owned process group has already exited; nothing remains to kill.
            pass
        child.wait()
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
            except ReadinessError as error:
                if str(error) == "session timeout":
                    raise ReadinessError("SSH session timeout") from None
                raise
            if status == 0:
                break
            until = time.monotonic() + 5
            while time.monotonic() < until:
                check_cancelled()
                time.sleep(min(0.1, max(0, until - time.monotonic())))
        else:
            raise ReadinessError("SSH did not come up after 30 attempts")
    for _attempt in range(30):
        try:
            status, _ = run_command([*ssh, REMOTE_WAIT], timeout=10, environment=environment)
        except ReadinessError as error:
            if str(error) == "session timeout":
                raise ReadinessError("SSH session timeout") from None
            raise
        if status == 0:
            return
        if status == 21:
            continue
        raise ReadinessError({20: "cloud-init error", 23: "cloud-init recoverable error",
                              22: "bootstrap marker missing", 24: "cloud-init status unavailable"}
                             .get(status, "bootstrap SSH transport failure"))
    raise ReadinessError("cloud-init timeout: still waiting after 30 bounded attempts")


def main():
    # Only the existing Terraform first-boot adapter uses accept-new. Deployment
    # supplies the canonical strict SSH prefix instead, without this CLI path.
    address, user, port, key = sys.argv[1:]
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
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
