"""Actual local process-boundary cases transferred from Rust lifecycle tests."""

import array
import fcntl
import json
import os
import pty
import select
import signal
import subprocess
import sys
import termios
import time
from artifact_helpers import scaffold, private, command, environment, executable
from vpnd.commands.probe_matrix import companion_path

OK = 'printf \'%s\\n\' \'{"verdict":"ok","rtt_ms":1}\''


class Fixture:
    def __init__(self, root, control=OK, cell=OK):
        self.root = scaffold(root)
        (root / "Makefile").write_text(
            f"probe-matrix-control:\n\t@{control}\nprobe-matrix-cell:\n\t@{cell}\n"
        )
        targets = []
        for id, topology in [
            ("pair-dual", "single-ip-dual-role"),
            ("pair-split", "split-hop-ingress"),
        ]:
            path = private(
                root / (id + ".json"),
                json.dumps(
                    dict(
                        schema_version=1,
                        target_id=id,
                        endpoint="192.0.2.1",
                        protocols={"mtproto": dict(port=10443, secret=id)},
                    )
                ),
            )
            targets.append(
                dict(
                    id=id,
                    comparison_set="pair",
                    destination_class="neutral-pattern",
                    topology=topology,
                    profile_file=str(path),
                )
            )
        config = dict(
            schema_version=2,
            vantage="test-path",
            poll_interval_seconds=1,
            control=dict(
                url="https://control.example",
                expected_status=204,
                timeout_seconds=1,
                degraded_after_ms=500,
            ),
            protocols=["mtproto"],
            targets=targets,
        )
        (root / "matrix.yaml").write_text(json.dumps(config))
        self.children = []

    def argv(self, duration="1s", output=None, *extra):
        return command(
            self.root,
            "probe-matrix",
            "--config",
            self.root / "matrix.yaml",
            "--duration",
            duration,
            "--output",
            output or self.root / "report.json",
            *extra,
        )

    def run(self, duration="1s", output=None, *extra):
        return subprocess.run(
            self.argv(duration, output, *extra),
            env=environment(self.root),
            capture_output=True,
            text=True,
            timeout=12,
        )

    def start(self, duration="120s", output=None, *extra):
        child = subprocess.Popen(
            self.argv(duration, output, *extra),
            env=environment(self.root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self.children.append(child)
        return child

    def close(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait()
        for path in self.root.glob("*.pids"):
            for pid in path.read_text().splitlines():
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except ProcessLookupError:
                    # Successful cancellation may already have reclaimed this fixture job.
                    pass


def ready(predicate, child=None, timeout=5):
    end = time.monotonic() + timeout
    while not predicate():
        assert child is None or child.poll() is None, "CLI exited before readiness"
        assert time.monotonic() < end, "readiness deadline exceeded"
        time.sleep(0.02)


def checkpoint(path):
    def read():
        try:
            value = json.loads(path.read_text())
            return value if value["controls"] else None
        except (OSError, ValueError, KeyError):
            return None

    ready(read)
    return read()


def report(fixture):
    return json.loads((fixture.root / "report.json").read_text())


def journal(path):
    return [json.loads(line) for line in companion_path(path, ".jsonl").read_text().splitlines()]


def running(pid):
    output = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return (
        output.returncode == 0
        and bool(output.stdout.strip())
        and not output.stdout.strip().startswith("Z")
    )


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::normal_run_checkpoints_private_report_and_jsonl_journal
def test_normal_run_checkpoints_private_report_and_jsonl_journal(tmp_path):
    f = Fixture(tmp_path)
    output = f.run()
    assert output.returncode == 0, output.stderr
    value = report(f)
    path = tmp_path / "report.json"
    records = journal(path)
    assert (
        value["schema_version"] == 3
        and value["completed"] is True
        and value["interrupted"] is False
    )
    assert len(value["controls"]) == 1 and len(value["cells"]) == 2
    assert len(records) >= 3 and all(r["schema_version"] == 3 for r in records)
    assert records[0]["completed"] is False and records[0]["interrupted"] is False
    assert records[-1]["completed"] is True and records[-1]["interrupted"] is False
    assert sum(r["control"] is not None for r in records) == len(value["controls"])
    assert [c for r in records for c in r["cells"]] == value["cells"]
    for p in [path, companion_path(path, ".jsonl"), companion_path(path, ".lock")]:
        assert p.stat().st_mode & 0o777 == 0o600


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::signal_during_scheduled_wait_flushes_prior_ticks_without_synthetic_cells
def test_signal_during_scheduled_wait_flushes_prior_ticks_without_synthetic_cells(tmp_path):
    f = Fixture(tmp_path)
    child = f.start("120s", None, "--poll-interval-seconds", "60")
    try:
        observed = checkpoint(tmp_path / "report.json")
        child.send_signal(signal.SIGINT)
        assert child.wait(timeout=8) == 130
        value = report(f)
        terminal = journal(tmp_path / "report.json")[-1]
        assert value["completed"] is False and value["interrupted"] is True
        assert len(value["controls"]) == len(observed["controls"]) and len(value["cells"]) == len(
            observed["cells"]
        )
        assert (
            terminal["completed"] is False
            and terminal["interrupted"] is True
            and terminal["control"] is None
            and terminal["cells"] == []
        )
    finally:
        f.close()


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::signals_during_cells_flush_partial_evidence_and_reclaim_descendants
def test_signals_during_cells_flush_partial_evidence_and_reclaim_descendants(tmp_path):
    for signum in [signal.SIGINT, signal.SIGTERM]:
        root = tmp_path / str(signum)
        root.mkdir()
        f = Fixture(root, OK, "sh cell.sh")
        (root / "cell.sh").write_text("""if [ "$TARGET_ID" = pair-dual ]; then
 printf '%s\\n' '{"verdict":"blocked"}'
 touch quick-cell-complete
 exit 0
fi
sleep 60 &
grandchild=$!
printf '%s\\n' "$PPID" "$$" "$grandchild" > slow-cell.pids.tmp
mv slow-cell.pids.tmp slow-cell.pids
wait
""")
        child = f.start("120s", None, "--poll-interval-seconds", "60")
        try:
            ready(
                lambda: (
                    (root / "quick-cell-complete").exists() and (root / "slow-cell.pids").exists()
                ),
                child,
            )
            pids = (root / "slow-cell.pids").read_text().splitlines()
            assert all(map(running, pids))
            time.sleep(0.05)
            child.send_signal(signum)
            assert child.wait(timeout=8) == 128 + signum
            value = report(f)
            cells = value["cells"]
            assert (
                value["schema_version"] == 3
                and value["completed"] is False
                and value["interrupted"] is True
            )
            assert (
                len(cells) == 2
                and cells[0]["target_id"] == "pair-dual"
                and cells[0]["verdict"] == "blocked"
            )
            assert (
                cells[1]["target_id"] == "pair-split"
                and cells[1]["verdict"] == "unknown"
                and cells[1]["error_kind"] == "interrupted"
            )
            records = journal(root / "report.json")
            assert records[-1]["completed"] is False and records[-1]["interrupted"] is True
            assert [c for r in records for c in r["cells"]] == cells
            ready(lambda: all(not running(pid) for pid in pids), timeout=3)
        finally:
            f.close()


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::same_output_sessions_are_exclusive_and_lock_survives_reuse
def test_same_output_sessions_are_exclusive_and_lock_survives_reuse(tmp_path):
    f = Fixture(tmp_path)
    first = f.start("120s", None, "--poll-interval-seconds", "60")
    try:
        checkpoint(tmp_path / "report.json")
        prior = (tmp_path / "report.json").read_bytes()
        second = f.run()
        assert second.returncode != 0 and "already in use" in second.stderr
        assert (tmp_path / "report.json").read_bytes() == prior
        lock = companion_path(tmp_path / "report.json", ".lock")
        meta = lock.stat()
        assert meta.st_mode & 0o777 == 0o600 and meta.st_size == 0
        first.kill()
        assert first.wait(timeout=8) != 0
        assert f.run().returncode == 0 and lock.stat().st_ino == meta.st_ino
    finally:
        f.close()


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::output_names_with_shared_stems_keep_distinct_companions
def test_output_names_with_shared_stems_keep_distinct_companions(tmp_path):
    f = Fixture(tmp_path)
    paths = [tmp_path / "report.json", tmp_path / "report.txt"]
    for path in paths:
        assert f.run(output=path).returncode == 0
    for suffix in [".jsonl", ".lock"]:
        assert companion_path(paths[0], suffix) != companion_path(paths[1], suffix)
        for path in paths:
            assert companion_path(path, suffix).exists()


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::unsafe_output_locks_and_reserved_suffixes_fail_before_make
def test_unsafe_output_locks_and_reserved_suffixes_fail_before_make(tmp_path):
    for kind in ["jsonl", "lock", "permissive", "nonempty", "symlink"]:
        root = tmp_path / kind
        root.mkdir()
        f = Fixture(root, "touch invoked", "touch invoked")
        output = root / ("report." + kind if kind in ["jsonl", "lock"] else "report.json")
        lock = companion_path(output, ".lock")
        if kind == "permissive":
            lock.touch()
            lock.chmod(0o644)
        if kind == "nonempty":
            private(lock, "not a lock")
        if kind == "symlink":
            (root / "lock-target").touch()
            lock.symlink_to(root / "lock-target")
        assert f.run(output=output).returncode != 0 and not (root / "invoked").exists()


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::failed_interrupted_checkpoint_preserves_last_valid_report_and_exits_one
def test_failed_interrupted_checkpoint_preserves_last_valid_report_and_exits_one(tmp_path):
    f = Fixture(tmp_path)
    child = f.start("120s", None, "--poll-interval-seconds", "60")
    mode = tmp_path.stat().st_mode & 0o777
    try:
        checkpoint(tmp_path / "report.json")
        prior = (tmp_path / "report.json").read_bytes()
        tmp_path.chmod(0o500)
        child.send_signal(signal.SIGTERM)
        status = child.wait(timeout=8)
    finally:
        tmp_path.chmod(mode)
        f.close()
    assert status == 1 and (tmp_path / "report.json").read_bytes() == prior
    terminal = journal(tmp_path / "report.json")[-1]
    assert terminal["completed"] is False and terminal["interrupted"] is True


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::hanging_control_records_unknown_and_continues_real_make_cells
def test_hanging_control_records_unknown_and_continues_real_make_cells(tmp_path):
    f = Fixture(tmp_path, "sh control.sh", "touch cell-invoked; " + OK)
    (tmp_path / "control.sh").write_text(
        'printf \'%s\\n\' "$PPID" "$$" > control.pids.tmp\nmv control.pids.tmp control.pids\nexec sleep 60\n'
    )
    try:
        output = f.run()
        assert output.returncode == 0, output.stderr
        assert (tmp_path / "control.pids").exists() and (tmp_path / "cell-invoked").exists()
        value = report(f)
        assert (
            value["schema_version"] == 3
            and value["controls"][0]["verdict"] == "unknown"
            and value["controls"][0]["error_kind"] == "control_timeout"
            and len(value["cells"]) == 2
        )
        assert all(not running(pid) for pid in (tmp_path / "control.pids").read_text().splitlines())
    finally:
        f.close()


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::invalid_durations_fail_before_probes_without_panicking
def test_invalid_durations_fail_before_probes_without_panicking(tmp_path):
    f = Fixture(tmp_path, "touch invoked", "touch invoked")
    for duration in ["0", "0s", "0m", "0h", "0d", "18446744073709551615d", "18446744073709551615s"]:
        for explain in [False, True]:
            output = f.run(duration, None, *(["--explain"] if explain else []))
            assert output.returncode not in [0, 101] and not (tmp_path / "invoked").exists()


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::unrepresentable_next_poll_finishes_with_observed_results
def test_unrepresentable_next_poll_finishes_with_observed_results(tmp_path):
    for override in [False, True]:
        root = tmp_path / str(override)
        root.mkdir()
        f = Fixture(root, OK, "touch cell-invoked; " + OK)
        extra = ["--poll-interval-seconds", "18446744073709551615"] if override else []
        if not override:
            config = json.loads((root / "matrix.yaml").read_text())
            config["poll_interval_seconds"] = 2**64 - 1
            (root / "matrix.yaml").write_text(json.dumps(config))
        output = f.run("1s", None, *extra)
        assert output.returncode == 0, output.stderr
        assert (root / "cell-invoked").exists()
        value = report(f)
        assert (
            value["schema_version"] == 3
            and len(value["controls"]) == 1
            and value["controls"][0]["verdict"] == "ok"
        )
        assert len(value["cells"]) == 2 and all(
            c["tick"] == 0 and c["verdict"] == "ok" for c in value["cells"]
        )


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::direct_and_foreground_signals_reclaim_probe_jobs_and_doctor_captures
def test_direct_and_foreground_signals_reclaim_probe_jobs_and_doctor_captures(tmp_path):
    for doctor in [False, True]:
        for signum in [signal.SIGINT, signal.SIGTERM]:
            for foreground in [False, True]:
                root = tmp_path / f"{doctor}-{signum}-{foreground}"
                root.mkdir()
                f = Fixture(root, OK, "sh hanging.sh")
                config = json.loads((root / "matrix.yaml").read_text())
                config["control"]["timeout_seconds"] = 10
                (root / "matrix.yaml").write_text(json.dumps(config))
                (root / "hanging.sh").write_text(
                    'record="${1:-$TARGET_ID}.pids"\nsleep 60 &\ngrandchild=$!\nprintf \'%s\\n\' "$PPID" "$$" "$grandchild" > "$record.tmp"\nmv "$record.tmp" "$record"\nwait\n'
                )
                if doctor:
                    (root / "Makefile").write_text("fleet-status:\n\t@sh hanging.sh doctor\n")
                argv = command(root, "doctor") if doctor else f.argv("30s")
                child = subprocess.Popen(
                    argv,
                    env=environment(root),
                    process_group=0,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                f.children.append(child)
                try:
                    ready(lambda: len(list(root.glob("*.pids"))) == (1 if doctor else 2), child, 8)
                    pids = [
                        pid for path in root.glob("*.pids") for pid in path.read_text().splitlines()
                    ]
                    assert all(map(running, pids))
                    deadline = time.monotonic() + 3
                    (os.killpg if foreground else os.kill)(child.pid, signum)
                    assert child.wait(timeout=max(0, deadline - time.monotonic())) == 128 + signum
                    while any(running(pid) for pid in pids) and time.monotonic() < deadline:
                        time.sleep(0.02)
                    assert all(not running(pid) for pid in pids), (
                        "captured descendant survived the shared signal deadline"
                    )
                finally:
                    f.close()


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::invalid_config_and_profile_inputs_fail_before_probe_execution
def test_invalid_config_and_profile_inputs_fail_before_probe_execution(tmp_path):
    valid = tmp_path / "valid"
    valid.mkdir()
    f = Fixture(valid, "touch invoked", "touch invoked")
    assert f.run("1s", None, "--explain").returncode == 0 and not (valid / "invoked").exists()
    for case in range(19):
        root = tmp_path / str(case)
        root.mkdir()
        f = Fixture(root, "touch invoked", "touch invoked")
        config = json.loads((root / "matrix.yaml").read_text())
        path = root / "pair-dual.json"
        profile = json.loads(path.read_text())
        if case == 0:
            config["schema_version"] = 99
        elif case == 1:
            config["vantage"] = "UPPER invalid"
        elif case == 2:
            config["control"]["url"] = "http://example.com"
        elif case == 3:
            config["control"]["expected_status"] = 600
        elif case == 4:
            config["control"]["timeout_seconds"] = 0
        elif case == 5:
            config["control"]["degraded_after_ms"] = 0
        elif case == 6:
            config["protocols"] = []
        elif case == 7:
            config["protocols"] = ["mtproto", "mtproto"]
        elif case == 8:
            config["targets"][1]["id"] = "pair-dual"
        elif case == 9:
            config["targets"][0]["profile_file"] = "relative.json"
        elif case == 10:
            config["targets"][1]["topology"] = "single-ip-dual-role"
        elif case == 11:
            config["targets"][1]["destination_class"] = "allowlist-pattern"
        elif case == 12:
            profile["schema_version"] = 99
        elif case == 13:
            profile["target_id"] = "other-target"
        elif case == 14:
            profile["protocols"] = {}
        elif case == 15:
            profile["protocols"]["mtproto"]["port"] = 999
        elif case == 16:
            path.chmod(0o640)
        elif case == 17:
            config["poll_interval_seconds"] = 0
        elif case == 18:
            config["control"]["timeout_seconds"] = 61
        (root / "matrix.yaml").write_text(json.dumps(config))
        path.write_text(json.dumps(profile))
        output = f.run("1s", None, "--explain")
        assert output.returncode != 0, case
        assert not (root / "invoked").exists()
    for kind in ["missing", "symlink", "directory", "malformed"]:
        root = tmp_path / kind
        root.mkdir()
        f = Fixture(root, "touch invoked", "touch invoked")
        path = root / "pair-dual.json"
        path.unlink()
        if kind == "symlink":
            path.symlink_to(root / "pair-split.json")
        elif kind == "directory":
            path.mkdir()
        elif kind == "malformed":
            private(path, "not json")
        assert f.run("1s", None, "--explain").returncode != 0


# Rust test: vpnd/tests/probe_matrix_lifecycle.rs::share_stdin_and_reconverge_prompt_preserve_signal_termination
def test_share_stdin_and_reconverge_prompt_preserve_signal_termination(tmp_path):
    scaffold(tmp_path)
    (tmp_path / "Makefile").write_text("emit-singbox:\n\t@touch emitted\n")
    private(
        tmp_path / "runtime/vpn-test.secrets.yaml",
        "xray:\n  clients:\n    - name: phone\nsubscription:\n  server_name: sub.example.com\n",
    )
    data = {
        "vpn": {"hosts": ["fixture-node"]},
        "_meta": {
            "hostvars": {
                "fixture-node": {"env": "test", "provider": "upcloud", "ansible_host": "192.0.2.1"}
            }
        },
    }
    executable(
        tmp_path, "ansible-inventory", "#!/bin/sh\nprintf '%s\\n' '" + json.dumps(data) + "'\n"
    )
    env = environment(tmp_path)
    for signum in [signal.SIGINT, signal.SIGTERM]:
        read_fd, write_fd = os.pipe()
        os.write(write_fd, b"synthetic-token")
        child = subprocess.Popen(
            command(tmp_path, "share", "phone", "--token-stdin"),
            stdin=read_fd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        try:

            def consumed():
                pending = array.array("i", [0])
                fcntl.ioctl(read_fd, termios.FIONREAD, pending)
                return pending[0] == 0

            ready(consumed, child)
            child.send_signal(signum)
            assert child.wait(timeout=3) == -signum
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()
            os.close(read_fd)
            os.close(write_fd)
        assert not (tmp_path / "emitted").exists()
        pid, terminal = pty.fork()
        if pid == 0:
            os.execvpe(sys.executable, command(tmp_path, "reconverge"), env)
        reaped = False
        try:
            transcript = b""
            end = time.monotonic() + 5
            while b"Proceed?" not in transcript:
                assert time.monotonic() < end, "reconverge never reached confirmation"
                if select.select([terminal], [], [], 0.05)[0]:
                    transcript += os.read(terminal, 8192)
            os.kill(pid, signum)
            end = time.monotonic() + 3
            while time.monotonic() < end:
                waited, status = os.waitpid(pid, os.WNOHANG)
                if waited:
                    reaped = True
                    assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signum
                    break
                if sys.platform == "darwin" and terminal is not None:
                    state = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True
                    ).stdout.strip()
                    if "E" in state:
                        os.close(terminal)
                        terminal = None
                time.sleep(0.01)
            assert reaped, "interactive signal deadline exceeded"
        finally:
            if terminal is not None:
                os.close(terminal)
            if not reaped:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
