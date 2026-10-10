"""Real descriptor failure cleanup and private runtime permission boundaries."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import importlib.util
import io
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
import uuid

import pytest
import yaml

from scripts.template_render import render_template

ROOT = Path(__file__).resolve().parents[2]


def load(role, name):
    spec = importlib.util.spec_from_file_location(
        f"review_{role}_{name}", ROOT / "ansible/roles" / role / "files" / name
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def track_fds(monkeypatch):
    actual_open, actual_stat = os.open, os.fstat
    acquired = []
    with monkeypatch.context() as patch:

        def record(*args, **kwargs):
            fd = actual_open(*args, **kwargs)
            acquired.append(fd)
            return fd

        patch.setattr(os, "open", record)
        yield patch, acquired, actual_stat
    for fd in set(acquired):
        with pytest.raises(OSError):
            actual_stat(fd)


@pytest.mark.parametrize(
    "failure", ["first-stat", "second-stat", "fdopen", "metadata", "close"]
)
def test_xray_failure_closes_all_files_and_directory_fds(
    tmp_path, monkeypatch, failure
):
    module = load("xray", "xray_log_setup.py")
    logs = tmp_path / "owned"
    logs.mkdir(mode=0o750)
    for name in ("access.log", "error.log"):
        (logs / name).write_bytes(b"prior synthetic bytes\n")
        (logs / name).chmod(0o600)
    with track_fds(monkeypatch) as (patch, acquired, actual_stat):
        actual_open = os.open

        def mapped_open(path, *args, **kwargs):
            return actual_open(tmp_path if path == "/" else path, *args, **kwargs)

        patch.setattr(os, "open", mapped_open)
        inspections = 0

        def inspect(fd):
            nonlocal inspections
            value = actual_stat(fd)
            if stat.S_ISREG(value.st_mode):
                inspections += 1
                if failure == ("first-stat" if inspections == 1 else "second-stat"):
                    raise OSError("injected descriptor inspection failure")
            return value

        patch.setattr(os, "fstat", inspect)
        if failure == "fdopen":
            patch.setattr(
                os,
                "fdopen",
                lambda *a, **kw: (_ for _ in ()).throw(
                    OSError("injected wrapping failure")
                ),
            )
        elif failure == "metadata":
            patch.setattr(
                os,
                "fchmod",
                lambda *a: (_ for _ in ()).throw(OSError("injected metadata failure")),
            )
        if failure == "close":
            original_close = os.close
            first = True

            def close(fd):
                nonlocal first
                original_close(fd)
                if first:
                    first = False
                    raise OSError("injected error after descriptor close")

            patch.setattr(os, "close", close)
        with pytest.raises(OSError):
            module.provision("/owned", os.geteuid(), os.getegid())
    assert acquired
    assert all(
        (logs / name).read_bytes() == b"prior synthetic bytes\n"
        for name in ("access.log", "error.log")
    )
    if failure not in {"metadata", "close"}:
        assert all(
            (logs / name).stat().st_mode & 0o777 == 0o600
            for name in ("access.log", "error.log")
        )


def test_xray_creates_private_then_validates_both_before_authorized_group_grant(
    tmp_path, monkeypatch
):
    module = load("xray", "xray_log_setup.py")
    created, granted = [], []
    with track_fds(monkeypatch) as (patch, _, _):
        actual_open, actual_chmod = os.open, os.fchmod

        def mapped_open(path, flags, mode=0o777, **kwargs):
            if flags & os.O_CREAT:
                created.append(mode)
            return actual_open(tmp_path if path == "/" else path, flags, mode, **kwargs)

        def grant(fd, mode):
            assert (tmp_path / "owned/access.log").exists()
            assert (tmp_path / "owned/error.log").exists()
            granted.append(mode)
            actual_chmod(fd, mode)

        patch.setattr(os, "open", mapped_open)
        patch.setattr(os, "fchmod", grant)
        assert module.provision("/owned", os.geteuid(), os.getegid())
    assert created == [0o600, 0o600]
    assert granted == [0o640, 0o640]


@pytest.mark.parametrize("failure", ["stat", "chmod", "sync"])
def test_naive_failure_closes_leaf_and_directory_without_truncation(
    tmp_path, monkeypatch, failure
):
    module = load("naive", "prepare_log.py")
    directory = tmp_path / "logs"
    directory.mkdir(mode=0o750)
    leaf = directory / "access.log"
    leaf.write_bytes(b"retained log bytes\n")
    leaf.chmod(0o640)
    original_lstat = Path.lstat

    # This portable fault model supplies trusted ancestry. Native coverage below
    # and the canonical Naive tests exercise actual root/service identities.
    def trusted_ancestor(path):
        value = original_lstat(path)
        if path in directory.parents:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        return value

    with track_fds(monkeypatch) as (patch, acquired, actual_stat):
        patch.setattr(Path, "lstat", trusted_ancestor)
        patch.setattr(
            module.pwd,
            "getpwnam",
            lambda _: SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid()),
        )

        def inspect(fd):
            value = actual_stat(fd)
            if failure == "stat" and stat.S_ISREG(value.st_mode):
                raise OSError("injected file inspection failure")
            return value

        patch.setattr(os, "fstat", inspect)
        if failure in {"chmod", "sync"}:
            patch.setattr(
                os,
                "fchmod" if failure == "chmod" else "fsync",
                lambda *a: (_ for _ in ()).throw(OSError("injected metadata failure")),
            )
        with pytest.raises(OSError):
            module.prepare(leaf, "synthetic-owner")
    assert acquired
    assert leaf.read_bytes() == b"retained log bytes\n"


def budget(module):
    return "".join(f"{key}=123\n" for key in module.KEYS)


@pytest.mark.parametrize(
    "failure", ["read-wrap", "write-wrap", "chmod", "sync", "cleanup"]
)
def test_watchdog_failed_publication_closes_every_owned_fd(
    tmp_path, monkeypatch, failure
):
    module = load("watchdog", "vpn-watchdog-state.py")
    path = tmp_path / "state"
    previous = budget(module)
    path.write_text(previous)
    path.chmod(0o600)
    with track_fds(monkeypatch) as (patch, acquired, _):
        original = os.fdopen
        patch.setattr(sys, "stdin", io.StringIO(previous.replace("123", "456")))
        if failure.endswith("wrap"):

            def wrap(fd, mode):
                if mode == ("r" if failure == "read-wrap" else "w"):
                    raise OSError("injected stream wrapping failure")
                return original(fd, mode)

            patch.setattr(os, "fdopen", wrap)
        elif failure in {"chmod", "sync"}:
            patch.setattr(
                os,
                "fchmod" if failure == "chmod" else "fsync",
                lambda *a: (_ for _ in ()).throw(
                    OSError("injected persistence failure")
                ),
            )
        else:
            original_unlink = os.unlink

            def unlink(name, **kwargs):
                if str(name).startswith(".watchdog-state-"):
                    raise PermissionError("injected cleanup failure")
                return original_unlink(name, **kwargs)

            patch.setattr(os, "unlink", unlink)
            patch.setattr(
                os,
                "replace",
                lambda *a, **kw: (_ for _ in ()).throw(
                    OSError("injected publication failure")
                ),
            )
        with pytest.raises(OSError):
            module.operate(path, "write")
    assert acquired
    assert path.read_text() == previous


def test_watchdog_valid_legacy_budget_migrates_preserving_bytes_and_counters(
    tmp_path, capsys
):
    module = load("watchdog", "vpn-watchdog-state.py")
    path = tmp_path / "state"
    raw = budget(module).replace("=123", "=000123")
    path.write_text(raw)
    path.chmod(0o640)
    module.operate(path, "read")
    assert capsys.readouterr().out == budget(module)
    assert path.read_text() == raw
    assert path.stat().st_mode & 0o777 == 0o600
    module.operate(path, "read")
    assert path.read_text() == raw


def test_watchdog_lock_contention_refuses_without_budget_mutation(tmp_path):
    module = load("watchdog", "vpn-watchdog-state.py")
    path = tmp_path / "state"
    raw = budget(module)
    path.write_text(raw)
    path.chmod(0o640)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with pytest.raises(BlockingIOError):
            module.operate(path, "read")
    finally:
        os.close(fd)
    assert path.read_text() == raw
    assert path.stat().st_mode & 0o777 == 0o640


def test_watchdog_candidate_collision_preserves_foreign_inode(tmp_path, monkeypatch):
    module = load("watchdog", "vpn-watchdog-state.py")
    path = tmp_path / "state"
    raw = budget(module)
    path.write_text(raw)
    path.chmod(0o600)
    collision = tmp_path / (".watchdog-state-" + "a" * 32)
    collision.write_bytes(b"foreign candidate bytes")
    prior = collision.stat()
    monkeypatch.setattr(module.secrets, "token_hex", lambda _: "a" * 32)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    with track_fds(monkeypatch):
        with pytest.raises(FileExistsError):
            module.operate(path, "write")
    assert collision.read_bytes() == b"foreign candidate bytes"
    assert collision.stat().st_ino == prior.st_ino
    assert path.read_text() == raw


def test_watchdog_ancestor_failure_never_unlinks_candidate_in_wrong_parent(
    tmp_path, monkeypatch
):
    module = load("watchdog", "vpn-watchdog-state.py")
    collision = tmp_path / (".watchdog-state-" + "b" * 32)
    collision.write_bytes(b"unrelated parent bytes")
    monkeypatch.setattr(module.secrets, "token_hex", lambda _: "b" * 32)
    with track_fds(monkeypatch):
        with pytest.raises(FileNotFoundError):
            module.operate(tmp_path / "missing-child/state", "read")
    assert collision.read_bytes() == b"unrelated parent bytes"


def test_watchdog_replaced_candidate_is_not_published_or_unlinked(
    tmp_path, monkeypatch
):
    module = load("watchdog", "vpn-watchdog-state.py")
    path = tmp_path / "state"
    raw = budget(module)
    path.write_text(raw)
    path.chmod(0o600)
    foreign = tmp_path / (".watchdog-state-" + "c" * 32)
    monkeypatch.setattr(module.secrets, "token_hex", lambda _: "c" * 32)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    real_replace = os.replace

    def replace(source, destination, **kwargs):
        replacement = tmp_path / "foreign-replacement"
        replacement.write_bytes(b"foreign inode bytes")
        real_replace(replacement, foreign)
        raise OSError("injected failure after foreign inode replacement")

    monkeypatch.setattr(os, "replace", replace)
    with track_fds(monkeypatch):
        with pytest.raises(PermissionError):
            module.operate(path, "write")
    assert foreign.read_bytes() == b"foreign inode bytes"
    assert path.read_text() == raw


@pytest.mark.parametrize("bad", ["payload", "link", "ancestor"])
def test_watchdog_rejects_unsafe_budget_before_permission_migration(tmp_path, bad):
    module = load("watchdog", "vpn-watchdog-state.py")
    original = tmp_path / "state"
    raw = "unexpected=secret-free-fixture\n" if bad == "payload" else budget(module)
    original.write_text(raw)
    original.chmod(0o640)
    path = original
    if bad == "link":
        path = tmp_path / "state-alias"
        os.link(original, path)
    elif bad == "ancestor":
        alias = tmp_path / "unsafe-alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        path = alias / "state"
    with pytest.raises((OSError, ValueError)):
        module.operate(path, "read")
    assert original.read_text() == raw
    assert original.stat().st_mode & 0o777 == 0o640


@pytest.mark.native_runtime
def test_actual_policy_tail_reads_only_authorized_xray_group():
    import time

    assert sys.platform == "linux" and os.geteuid() == 0
    name = "p2-log-review-" + uuid.uuid4().hex[:10]
    base = Path("/var/lib") / name
    base.mkdir(mode=0o755)
    base.chmod(0o755)
    unit = name + ".service"
    unit_path = Path("/etc/systemd/system") / unit

    def run(argv):
        result = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, "owned native permission command failed"
        return result.stdout

    try:
        run(["useradd", "--system", "--user-group", name])
        account = pwd.getpwnam(name)
        watchdog = load("watchdog", "vpn-watchdog-state.py")
        foreign_budget = base / "foreign-budget"
        foreign_bytes = budget(watchdog)
        foreign_budget.write_text(foreign_bytes)
        foreign_budget.chmod(0o640)
        os.chown(foreign_budget, account.pw_uid, account.pw_gid)
        with pytest.raises(PermissionError):
            watchdog.operate(foreign_budget, "read")
        assert foreign_budget.read_text() == foreign_bytes
        assert foreign_budget.stat().st_uid == account.pw_uid
        assert foreign_budget.stat().st_mode & 0o777 == 0o640

        private_logs = base / "private-naive-logs"
        private_logs.mkdir(mode=0o750)
        os.chown(private_logs, account.pw_uid, account.pw_gid)
        naive = load("naive", "prepare_log.py")
        for leaf in ("access.log", "site-error.log"):
            path = private_logs / leaf
            assert naive.prepare(path, name)
            assert path.stat().st_mode & 0o777 == 0o600
            assert not naive.prepare(path, name)
            run(["runuser", "-u", name, "--", "test", "-w", str(path)])
        logs = base / "logs"
        module = load("xray", "xray_log_setup.py")
        assert module.provision(str(logs), account.pw_uid, account.pw_gid)
        log = logs / "access.log"
        run(
            [
                "runuser",
                "-u",
                name,
                "--",
                "/bin/sh",
                "-c",
                'printf "synthetic event\\n" >> "$1"',
                "owned-writer",
                str(log),
            ]
        )
        denied = subprocess.run(
            ["runuser", "-u", "nobody", "--", "test", "-r", str(log)],
            capture_output=True,
            timeout=10,
        )
        assert denied.returncode == 1
        (base / "metrics").mkdir(mode=0o700)
        values = {
            "policy_ratelimit": {"textfile_dir": str(base / "metrics")},
            "xray_runtime_group": name,
        }
        (base / "policy.py").write_text(
            render_template(
                ROOT
                / "ansible/roles/policy-ratelimit/templates/policy-ratelimit.py.j2",
                values,
            )
        )
        (base / "reader.py").write_text(
            'import importlib.util, pathlib, sys\ns=importlib.util.spec_from_file_location("policy",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\nt=m.tail(pathlib.Path(sys.argv[2]));_,healthy=next(t);t.close();raise SystemExit(0 if healthy else 13)\n'
        )
        canonical = (
            render_template(
                ROOT
                / "ansible/roles/policy-ratelimit/templates/policy-ratelimit.service.j2",
                values,
            )
            .replace(
                "ExecStart=/usr/local/bin/policy-ratelimit.py",
                f"ExecStart={sys.executable} {base}/reader.py {base}/policy.py {log}",
            )
            .replace("Restart=on-failure", "Restart=no")
        )
        for mode, authorized, expected in [
            (0o640, False, 13),
            (0o600, True, 13),
            (0o640, True, 0),
        ]:
            log.chmod(mode)
            text = (
                canonical
                if authorized
                else canonical.replace("SupplementaryGroups=" + name, "")
            )
            unit_path.write_text(text)
            run(["systemctl", "daemon-reload"])
            subprocess.run(
                ["systemctl", "reset-failed", unit], capture_output=True, timeout=10
            )
            subprocess.run(
                ["systemctl", "start", unit], capture_output=True, timeout=10
            )
            deadline = time.monotonic() + 5
            while True:
                state = dict(
                    line.split("=", 1)
                    for line in run(
                        [
                            "systemctl",
                            "show",
                            unit,
                            "--property=MainPID,ExecMainStatus,CapabilityBoundingSet",
                        ]
                    ).splitlines()
                )
                if state["MainPID"] == "0":
                    break
                assert time.monotonic() < deadline
                time.sleep(0.05)
            assert int(state["ExecMainStatus"]) == expected
            assert state["CapabilityBoundingSet"] == "cap_net_admin"
    finally:
        subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=10)
        unit_path.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True, timeout=10)
        shutil.rmtree(base)
        subprocess.run(["userdel", name], capture_output=True, timeout=10)
        subprocess.run(["groupdel", name], capture_output=True, timeout=10)


@pytest.mark.native_runtime
def test_actual_independent_policy_role_provisions_reader_group_without_gid_drift():
    import time

    assert sys.platform == "linux" and os.geteuid() == 0
    unit = "policy-ratelimit.service"
    unit_path = Path("/etc/systemd/system") / unit
    script = Path("/usr/local/bin/policy-ratelimit.py")
    assert not os.path.lexists(unit_path) and not os.path.lexists(script)
    # This bounded direct-role proof owns only a fresh canonical policy service.
    before = subprocess.run(
        ["systemctl", "show", unit, "--property=LoadState", "--value"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert before.stdout.strip() == "not-found"
    name = "p2-policy-group-" + uuid.uuid4().hex[:10]
    base = Path("/var/lib") / name
    base.mkdir(mode=0o700)
    # The shared textfile exporter tree is an existing role prerequisite.
    (base / "metrics").mkdir(mode=0o700)
    defaults = yaml.safe_load(
        (ROOT / "ansible/roles/policy-ratelimit/defaults/main.yml").read_text()
    )
    defaults["policy_ratelimit"]["textfile_dir"] = str(base / "metrics")
    defaults.update(
        xray_runtime_group=name,
        vpn={"enable_policy_ratelimit": False, "enable_xray_reality": False},
    )
    play = [
        {
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars": defaults,
            "roles": [{"role": str(ROOT / "ansible/roles/policy-ratelimit")}],
        }
    ]
    path = base / "play.yml"
    path.write_text(yaml.safe_dump(play))
    try:
        absent = subprocess.run(
            ["getent", "group", name], capture_output=True, timeout=10
        )
        assert absent.returncode == 2
        argv = ["ansible-playbook", "-i", "localhost,", str(path)]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-1000:]
        group = subprocess.run(
            ["getent", "group", name],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
        deadline = time.monotonic() + 5
        metric = base / "metrics/vpn_policy_ratelimit.prom"
        while not metric.exists():
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert "vpn_policy_ratelimit_input_available 0" in metric.read_text()
        subprocess.run(
            ["systemctl", "is-active", "--quiet", unit], check=True, timeout=10
        )
        result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-1000:]
        assert "changed=0" in result.stdout
        assert (
            subprocess.run(
                ["getent", "group", name],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout
            == group
        )
        subprocess.run(
            ["systemctl", "is-active", "--quiet", unit], check=True, timeout=10
        )
    finally:
        subprocess.run(
            ["systemctl", "disable", "--now", unit], capture_output=True, timeout=10
        )
        unit_path.unlink(missing_ok=True)
        script.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True, timeout=10)
        subprocess.run(["groupdel", name], capture_output=True, timeout=10)
        shutil.rmtree(base)
