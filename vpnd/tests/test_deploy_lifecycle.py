"""Real local subprocess orchestration; external infrastructure is doubled."""

from pathlib import Path
from dataclasses import replace
from argparse import Namespace
import asyncio
import errno
import os
import pty
import select
import signal
import subprocess
import sys
import time
import tarfile
import termios
import fcntl
import pytest
from vpnd.config import Context
from vpnd import commands
from vpnd.commands import deploy, reconverge, preflight, fleet, finish_with_cleanup, ensure_host_in_registry
from vpnd.runner import Cmd
from vpnd.state import Registry, Host

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts/vpnd-cli.py"


def fake_ctx(root, explain=False):
    return Context(
        root,
        root / "ansible",
        root / "terraform/providers/upcloud",
        "prod",
        "upcloud",
        root / "source.yaml",
        root / "vpn-prod.secrets.yaml",
        root,
        explain,
        True,
    )


class Fixture:
    def __init__(self, root):
        self.root = root
        for path in (
            "bin",
            "ansible/inventory",
            "terraform/providers/upcloud",
            "runtime",
            "home/.config/vpn-provision",
            "home/Library/Application Support/vpn-provision",
        ):
            (root / path).mkdir(parents=True)
        (root / "Makefile").write_text("# external commands are explicit doubles\n")
        registry = "[hosts.alias]\nenv = 'test'\nprovider = 'upcloud'\nipv4 = '203.0.113.5'\n[hosts.wrong]\nenv = 'staging'\nprovider = 'upcloud'\nipv4 = '203.0.113.5'\n"
        for path in (
            "home/.config/vpn-provision",
            "home/Library/Application Support/vpn-provision",
        ):
            (root / path / "hosts.toml").write_text(registry)
        from artifact_helpers import subscription_fixture
        subscription_fixture(root)
        self.executable(
            "make",
            """#!/bin/sh
set -eu
target=$1
shift
for pair in "$@"; do
  case "$pair" in SECRETS_FILE=*) secret=${pair#SECRETS_FILE=} ;; HOST=*) host=${pair#HOST=} ;; ENV=*) export ENV=${pair#ENV=} ;; esac
done
printf 'make %s\n' "$target" >> "$FIXTURE_ROOT/calls"
case "$target" in
  dry-run|deploy|verify) if [ -n "${ANSIBLE_LIMIT:-}" ]; then test "$ANSIBLE_LIMIT" = fixture-node; fi ;;
  decrypt)
    if [ -n "${SCRIPT_DECRYPT:-}" ]; then
      SECRETS_FILE="$secret" SOPS_FILE="$SOPS_FIXTURE" bash "$SCRIPT_DECRYPT"
    else
      mkdir -p "$(dirname "$secret")"; printf 'fixture: true\n' > "$secret"; chmod 0600 "$secret"
    fi
    case "${HARDEN_TEST_MODE:-regular}" in
      missing) rm -f "$secret" ;;
      directory) rm -f "$secret"; mkdir "$secret" ;;
      symlink) rm -f "$secret"; ln -s "$FIXTURE_ROOT/hardening-target" "$secret" ;;
      immutable) /usr/bin/chflags uchg "$secret" ;;
    esac ;;
  clean)
    rm -f "$secret"
    if [ "${SLOW_TARGET:-none}" = clean ]; then : > "$FIXTURE_ROOT/started"; sleep 2; fi
    exit "${CLEAN_EXIT:-0}" ;;
  test-tls-policing) test "$host" = 203.0.113.5 ;;
  emit-singbox) printf '%s\n' '{"outbounds":[]}' ;;
esac
if [ "${ECHO_SECRET_PATH:-0}" = 1 ]; then printf 'reading %s\n' "$secret"; fi
if [ "$target" = "${FAIL_TARGET:-none}" ]; then exit 31; fi
if [ "$target" = "${SLOW_TARGET:-none}" ]; then : > "$FIXTURE_ROOT/started"; sleep 2; fi
if [ -n "${HUP_RECORD:-}" ]; then
  python3 -c 'import signal; print(signal.getsignal(signal.SIGHUP) == signal.SIG_IGN)' >> "$HUP_RECORD"
fi
if [ -n "${SIGNAL_RECORD:-}" ]; then
  python3 -c 'import os, signal; print(signal.getsignal(int(os.environ["IGNORED_SIGNAL"])) == signal.SIG_IGN)' >> "$SIGNAL_RECORD"
fi
""",
        )
        self.executable(
            "ansible-inventory",
            """#!/bin/sh
printf 'inventory\n' >> "$FIXTURE_ROOT/calls"
printf '%s\n' '{"vpn":{"hosts":["fixture-node","other-env"]},"_meta":{"hostvars":{"fixture-node":{"env":"test","provider":"upcloud","ansible_host":"100.64.0.5","vpn_service_address":"203.0.113.5"},"other-env":{"env":"staging","provider":"upcloud","ansible_host":"203.0.113.6"}}}}'
""",
        )
        self.executable(
            "ansible-playbook",
            """#!/bin/sh
set -eu
test -f "$VPN_SECRETS_FILE"
printf 'playbook %s\n' "$*" >> "$FIXTURE_ROOT/calls"
while [ "$#" -gt 0 ]; do
  if [ "$1" = --limit ]; then shift; test "$1" = fixture-node; fi
  shift
done
exit "${PLAYBOOK_EXIT:-0}"
""",
        )

    def executable(self, name, script):
        path = self.root / "bin" / name
        path.write_text(script)
        path.chmod(0o700)

    def command(self, args, extra=None, remove=(), yes=True, input=None):
        return subprocess.run(
            self.argv(args, yes),
            capture_output=True,
            text=True,
            env=self.environment(extra, remove),
            timeout=20,
            input=input,
        )

    def interactive(self, args, answer, *, yes=True, extra=None, ignore=None):
        """Answer the first terminal prompt that the review gate prints.

        An integer answer delivers that signal to vpnd instead of typing a line.
        """
        master, slave = pty.openpty()
        child = subprocess.Popen(
            self.argv(args, yes),
            stdin=slave,
            stderr=slave,
            stdout=subprocess.DEVNULL,
            env=self.environment(extra),
            preexec_fn=(lambda: signal.signal(ignore, signal.SIG_IGN)) if ignore else None,
        )
        os.close(slave)
        transcript = b""
        try:
            deadline = time.monotonic() + 15
            marker = b"[y/N]" if yes else b"[Y/n]"
            while marker not in transcript:
                assert time.monotonic() < deadline and child.poll() is None, transcript
                if select.select([master], [], [], 0.05)[0]:
                    transcript += os.read(master, 8192)
            if ignore is not None:
                os.kill(child.pid, ignore)
            if isinstance(answer, int):
                os.kill(child.pid, answer)
            else:
                os.write(master, answer)
            # Keep draining: a full terminal buffer would block the child.
            while True:
                assert time.monotonic() < deadline + 15, transcript
                if select.select([master], [], [], 0.05)[0]:
                    try:
                        chunk = os.read(master, 8192)
                    except OSError:
                        chunk = b""
                    transcript += chunk
                    if chunk:
                        continue
                if child.poll() is not None:
                    return child.returncode, transcript.decode(errors="replace")
        finally:
            os.close(master)
            if child.poll() is None:
                child.kill()
            child.wait()

    def signalled(self, args, slow, number, group, extra=None, ignore_hup=False):
        """Signal vpnd while the stub runs `slow`; a group signal also reaches that step."""
        child = subprocess.Popen(
            self.argv(args, True),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=self.environment({"SLOW_TARGET": slow, **(extra or {})}),
            start_new_session=True,
            # nohup leaves SIGHUP ignored for vpnd and every child it starts.
            preexec_fn=(lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN)) if ignore_hup else None,
        )
        try:
            deadline = time.monotonic() + 15
            while not (self.root / "started").exists():
                assert time.monotonic() < deadline and child.poll() is None, child.stderr.read()
                time.sleep(0.02)
            (os.killpg if group else os.kill)(child.pid, number)
            _, stderr = child.communicate(timeout=20)
            return child.returncode, stderr.decode(errors="replace")
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()

    def argv(self, args, yes):
        return [
            sys.executable,
            str(LAUNCHER),
            "--root",
            str(self.root),
            "--env",
            "test",
            *(["--yes"] if yes else []),
            *args,
        ]

    def environment(self, extra=None, remove=()):
        env = os.environ.copy()
        env.update(
            HOME=str(self.root / "home"),
            XDG_CONFIG_HOME=str(self.root / "home/.config"),
            XDG_RUNTIME_DIR=str(self.root / "runtime"),
            FIXTURE_ROOT=str(self.root),
            PATH=f"{self.root / 'bin'}:{env['PATH']}",
        )
        env.update({key: str(value) for key, value in (extra or {}).items()})
        for key in remove:
            env.pop(key, None)
        return env

    def calls(self):
        path = self.root / "calls"
        return path.read_text() if path.exists() else ""

    def secrets(self):
        return self.root / "runtime/vpn-test.secrets.yaml"


def successful(output):
    assert output.returncode == 0, output.stderr


# Rust test: vpnd/src/commands/mod.rs::cleanup_runs_after_failure_and_original_error_wins
def test_cleanup_runs_after_failure_and_original_error_wins(tmp_path):
    (tmp_path / "Makefile").write_text(
        ".PHONY: clean\nclean:\n\t@echo cleaned >> stamp\n\t@exit 7\n"
    )

    async def exercise():
        error = None
        try:
            for program in ("true", "false"):
                await Cmd.new(program).describe(f"test step: {program}").run()
        except Exception as outcome:
            error = outcome
        with pytest.raises(RuntimeError, match="false|exited"):
            await finish_with_cleanup(fake_ctx(tmp_path), error)

    asyncio.run(exercise())
    assert (tmp_path / "stamp").is_file() and (tmp_path / "stamp").read_text().strip() == "cleaned"


# Rust test: vpnd/src/commands/mod.rs::successful_pipeline_requires_successful_cleanup
def test_successful_pipeline_requires_successful_cleanup(tmp_path):
    (tmp_path / "Makefile").write_text("clean:\n\t@exit 7\n")
    with pytest.raises(RuntimeError, match="make clean"):
        asyncio.run(finish_with_cleanup(fake_ctx(tmp_path)))


# Rust test: vpnd/src/commands/mod.rs::ensure_host_rejects_unknown_alias_and_accepts_match
def test_ensure_host_rejects_unknown_alias_and_accepts_match(tmp_path):
    registry = Registry({"prod1": Host("prod", "upcloud", "203.0.113.5")})
    ctx = fake_ctx(tmp_path)
    with pytest.raises(ValueError):
        ensure_host_in_registry(ctx, registry, "ghost")
    ensure_host_in_registry(ctx, registry, None)
    ensure_host_in_registry(ctx, registry, "prod1")


# Rust test: vpnd/src/commands/deploy.rs::pipeline_matches_makefile_order_before_unconditional_cleanup
def test_pipeline_matches_makefile_order_before_unconditional_cleanup(tmp_path):
    rendered = [
        cmd.explain()
        for cmd in deploy.plan_steps(
            fake_ctx(tmp_path), Namespace(skip_precheck=False, tag_on_success=False)
        )
    ]
    expected = [
        "check-prereqs",
        "validate",
        "decrypt",
        "init",
        "plan",
        "apply",
        "inventory",
        "wait",
        "deploy",
        "verify",
        "smoke-test",
    ]
    assert len(rendered) == len(expected)
    assert all(f"make {name} " in value for value, name in zip(rendered, expected))


# Rust test: vpnd/src/commands/deploy.rs::skip_precheck_and_tag_on_success_flow_into_their_targets
def test_skip_precheck_and_tag_on_success_flow_into_their_targets(tmp_path):
    rendered = [
        cmd.explain()
        for cmd in deploy.plan_steps(
            fake_ctx(tmp_path), Namespace(skip_precheck=True, tag_on_success=True)
        )
    ]
    assert "SKIP_PRECHECK=1" in next(s for s in rendered if "make deploy " in s)
    assert "TAG_ON_SUCCESS=1" in next(s for s in rendered if "make verify " in s)


# Rust test: vpnd/src/commands/deploy.rs::plan_summary_renders_placeholders_not_paths
def test_plan_summary_renders_placeholders_not_paths(tmp_path):
    ctx = replace(
        fake_ctx(tmp_path),
        sops_file=Path("/deep/nested/prod.secrets.sops.yaml"),
        secrets_file=Path("/runtime/vpn-prod.secrets.yaml"),
    )
    rows = deploy.build_plan_summary(ctx, Namespace(skip_precheck=False, tag_on_success=True))
    assert rows and all("/" not in value and ".yaml" not in value for _, value in rows)


# Rust test: vpnd/src/commands/preflight.rs::guards_run_in_order_and_include_certs_by_default
def test_guards_run_in_order_and_include_certs_by_default(tmp_path):
    steps = [s.explain() for s in preflight.required_steps(fake_ctx(tmp_path), False)]
    names = ["validate-secrets", "spot-check-secrets", "audit-permissions", "check-certs"]
    assert len(steps) == len(names)
    assert all(f"make {name} " in step for step, name in zip(steps, names))


# Rust test: vpnd/src/commands/preflight.rs::skip_certs_drops_only_the_cert_check
def test_skip_certs_drops_only_the_cert_check(tmp_path):
    steps = [s.explain() for s in preflight.required_steps(fake_ctx(tmp_path), True)]
    assert len(steps) == 3 and all("check-certs" not in s for s in steps)


# Rust test: vpnd/src/commands/fleet.rs::rotate_flags_map_to_make_kvs
def test_rotate_flags_map_to_make_kvs(tmp_path):
    plan = tmp_path / "fleet.yaml"
    plan.write_text("")
    plain = fleet.rotation_target(fake_ctx(tmp_path), plan, False, False).explain()
    assert f"PLAN={plan.resolve()}" in plain and "RESUME=" not in plain and "DRY_RUN=" not in plain
    full = fleet.rotation_target(fake_ctx(tmp_path), plan, True, True).explain()
    assert "RESUME=1" in full and "DRY_RUN=1" in full


# Rust test: vpnd/tests/deploy_lifecycle.rs::reconverge_dry_run_cleans_plaintext_and_uses_scoped_inventory_name
def test_reconverge_dry_run_cleans_plaintext_and_uses_scoped_inventory_name(tmp_path):
    for i, args in enumerate(
        (["reconverge", "--dry-run"], ["reconverge", "--dry-run", "--host", "alias"])
    ):
        f = Fixture(tmp_path / str(i))
        successful(f.command(args))
        assert not f.secrets().exists()
        calls = f.calls()
        assert (
            calls.count("playbook ") == 0
            and "make dry-run\n" in calls
            and calls.endswith("make clean\n")
        )


# Rust test: vpnd/tests/deploy_lifecycle.rs::deploy_and_reconverge_preserve_primary_failures_and_still_clean
def test_deploy_and_reconverge_preserve_primary_failures_and_still_clean(tmp_path):
    for name in ("deploy", "reconverge"):
        f = Fixture(tmp_path / name)
        output = f.command([name], {"FAIL_TARGET": "plan", "CLEAN_EXIT": "7"})
        assert (
            output.returncode != 0
            and not f.secrets().exists()
            and f.calls().endswith("make clean\n")
        )
        assert "make plan" in output.stderr and "cleanup also failed" in output.stderr


# Rust test: vpnd/tests/deploy_lifecycle.rs::registered_probe_uses_address_and_invalid_aliases_fail_before_work
def test_registered_probe_uses_address_and_invalid_aliases_fail_before_work(tmp_path):
    f = Fixture(tmp_path / "positive")
    successful(f.command(["probe", "--profile", "p1", "--host", "alias"]))
    assert "make test-tls-policing" in f.calls()
    for name in ("probe", "doctor", "reconverge"):
        for alias in ("missing", "wrong"):
            f = Fixture(tmp_path / f"{name}-{alias}")
            assert f.command([name, "--host", alias]).returncode != 0
            assert not f.calls()


# Rust test: vpnd/tests/deploy_lifecycle.rs::reconverge_explain_does_not_execute_or_harden_an_existing_file
def test_reconverge_explain_does_not_execute_or_harden_an_existing_file(tmp_path):
    f = Fixture(tmp_path)
    f.secrets().write_text("fixture: true\n")
    f.secrets().chmod(0o644)
    successful(f.command(["--explain", "reconverge"]))
    assert not f.calls() and f.secrets().stat().st_mode & 0o777 == 0o644


# Rust test: vpnd/tests/deploy_lifecycle.rs::doctor_redacts_both_ai_and_every_bundle_entry
def test_doctor_redacts_both_ai_and_every_bundle_entry(tmp_path):
    f = Fixture(tmp_path)
    for name in ("uname", "terraform", "ansible"):
        f.executable(
            name,
            "#!/bin/sh\nprintf 'diagnostic %s/runtime/vpn-test.secrets.yaml\\n' \"$FIXTURE_ROOT\"\n",
        )
    bundle = tmp_path / "report.tar.gz"
    output = f.command(["doctor", "--ai", "--bundle", str(bundle)], {"ECHO_SECRET_PATH": "1"})
    successful(output)
    assert str(f.secrets()) not in output.stdout and str(f.secrets()) not in output.stderr
    assert "<redacted: secrets file path>" in output.stdout
    with tarfile.open(bundle) as archive:
        entries = archive.getmembers()
        assert len(entries) == 6
        assert all(
            str(f.secrets()) not in archive.extractfile(entry).read().decode() for entry in entries
        )


# Rust test: vpnd/tests/deploy_lifecycle.rs::share_without_xdg_decrypts_once_through_the_canonical_script
def test_share_without_xdg_decrypts_once_through_the_canonical_script(tmp_path):
    f = Fixture(tmp_path)
    f.executable("sops", '#!/bin/sh\ncat "$SOPS_FIXTURE"\n')
    source = tmp_path / "source.yaml"
    source.write_text(
        "xray:\n  clients:\n    - name: phone\nsubscription:\n  server_name: sub.example.com\n"
    )
    token = tmp_path / "token"
    token.write_text("synthetic_token\n")
    token.chmod(0o600)
    runtime = tmp_path / "runtime-tmp"
    runtime.mkdir()
    for _ in range(2):
        successful(
            f.command(
                ["share", "phone", "--token-file", str(token)],
                {
                    "TMPDIR": runtime,
                    "SOPS_FIXTURE": source,
                    "SCRIPT_DECRYPT": ROOT / "scripts/decrypt-secrets.sh",
                },
                ("XDG_RUNTIME_DIR", "VPN_RUNTIME_DIR"),
            )
        )
    assert f.calls().count("make decrypt\n") == 1 and f.calls().count("make emit-singbox\n") == 2
    assert (runtime / f"vpn-provision-{os.getuid()}/vpn-test.secrets.yaml").is_file()
    assert (tmp_path / "share/phone/index.html").is_file()


# Rust test: vpnd/tests/deploy_lifecycle.rs::every_decrypting_caller_stops_at_an_unsafe_or_missing_plaintext_file
def test_every_decrypting_caller_stops_at_an_unsafe_or_missing_plaintext_file(tmp_path):
    for i, args in enumerate(
        (["share", "phone", "--token-file", "unused"], ["preflight"], ["reconverge"])
    ):
        for mode in ("missing", "directory", "symlink"):
            f = Fixture(tmp_path / f"{i}-{mode}")
            target = f.root / "hardening-target"
            target.write_text("not a secret\n")
            target.chmod(0o644)
            output = f.command(args, {"HARDEN_TEST_MODE": mode})
            assert output.returncode != 0 and "failed to set 0600" in output.stderr
            assert target.stat().st_mode & 0o777 == 0o644
            assert all(
                f"make {name}" not in f.calls()
                for name in ("init", "validate-secrets", "emit-singbox")
            )


# Rust test: vpnd/tests/deploy_lifecycle.rs::every_decrypting_caller_propagates_a_real_fd_chmod_failure
def test_every_decrypting_caller_propagates_a_real_fd_chmod_failure(tmp_path):
    for i, args in enumerate(
        (["share", "phone", "--token-file", "unused"], ["preflight"], ["reconverge"])
    ):
        f = Fixture(tmp_path / str(i))
        if sys.platform == "darwin":
            try:
                output = f.command(args, {"HARDEN_TEST_MODE": "immutable"})
            finally:
                if f.secrets().exists():
                    subprocess.run(["/usr/bin/chflags", "nouchg", str(f.secrets())], check=True)
        else:
            # Linux procfs is a genuine owner-regular descriptor rejecting chmod.
            f.executable("make", '#!/bin/sh\nprintf \'make %s\\n\' "$1" >> "$FIXTURE_ROOT/calls"\n')
            # Supply the same failure through Context rather than making a symlink.
            ctx = replace(fake_ctx(f.root), secrets_file=Path("/proc/self/cmdline"))
            with pytest.raises(ValueError, match="set 0600 on protected file descriptor"):
                ctx.secure_secrets_file()
            continue
        assert output.returncode != 0 and "set 0600 on protected file descriptor" in output.stderr
        assert all(
            f"make {name}" not in f.calls() for name in ("init", "validate-secrets", "emit-singbox")
        )


def test_piped_default_confirmation_cannot_start_deployment(tmp_path):
    for name in ("deploy", "reconverge"):
        fixture = Fixture(tmp_path / name)
        output = fixture.command([name], yes=False, input="\n")
        assert output.returncode != 0 and "not a terminal" in output.stderr
        assert "make " not in fixture.calls()
        assert not fixture.secrets().exists()
        explained = fixture.command(["--explain", name], yes=False, input="\n")
        successful(explained)
        assert "make " not in fixture.calls()


# Each command, the last target before its review, and the mutation it gates.
REVIEW_GATES = (("deploy", "plan", "apply"), ("reconverge", "dry-run", "deploy"))


@pytest.mark.parametrize(("name", "reviewed", "gated"), REVIEW_GATES)
def test_yes_cannot_answer_the_plan_or_dry_run_review(tmp_path, name, reviewed, gated):
    fixture = Fixture(tmp_path)
    output = fixture.command([name])
    calls = fixture.calls()
    assert output.returncode != 0 and "not a terminal" in output.stderr
    assert f"make {reviewed}\n" in calls and f"make {gated}\n" not in calls
    assert calls.endswith("make clean\n") and not fixture.secrets().exists()


@pytest.mark.parametrize(("name", "reviewed", "gated"), REVIEW_GATES)
@pytest.mark.parametrize(("answer", "accepted"), ((b"\n", False), (b"n\n", False), (b"y\n", True)))
def test_terminal_review_gates_the_mutation(tmp_path, name, reviewed, gated, answer, accepted):
    fixture = Fixture(tmp_path)
    returncode, transcript = fixture.interactive([name], answer)
    calls = fixture.calls()
    assert (returncode == 0) is accepted, transcript
    assert f"make {reviewed}\n" in calls and (f"make {gated}\n" in calls) is accepted
    assert calls.endswith("make clean\n") and not fixture.secrets().exists()


@pytest.mark.parametrize(("name", "reviewed", "gated"), REVIEW_GATES)
@pytest.mark.parametrize("slow", ("decrypt", "reviewed"))
@pytest.mark.parametrize("number", (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGHUP))
@pytest.mark.parametrize("group", (False, True), ids=("vpnd", "group"))
def test_signal_during_a_step_still_cleans_plaintext(tmp_path, name, reviewed, gated, slow, number, group):
    fixture = Fixture(tmp_path)
    step = reviewed if slow == "reviewed" else slow
    returncode, stderr = fixture.signalled([name], step, int(number), group)
    calls = fixture.calls()
    assert returncode == 128 + number, stderr
    assert f"make {step}\n" in calls and f"make {gated}\n" not in calls
    # A signal to vpnd alone lets the step finish; no later step starts.
    assert calls.split(f"make {step}\n", 1)[1] == "make clean\n", calls
    assert not fixture.secrets().exists()


# Success path (no review in dry-run reconverge) and failure path (deploy stops at the review).
@pytest.mark.parametrize("args", (["reconverge", "--dry-run"], ["deploy"]), ids=("success", "failure"))
@pytest.mark.parametrize("number", (signal.SIGINT, signal.SIGTERM))
@pytest.mark.parametrize("group", (False, True), ids=("vpnd", "group"))
def test_signal_during_cleanup_reports_the_signal(tmp_path, args, number, group):
    fixture = Fixture(tmp_path)
    returncode, stderr = fixture.signalled(args, "clean", int(number), group)
    assert returncode == 128 + number, stderr
    assert fixture.calls().endswith("make clean\n") and not fixture.secrets().exists()


def test_an_ignored_hangup_stays_ignored_for_every_step(tmp_path):
    fixture = Fixture(tmp_path)
    record = tmp_path / "hup"
    returncode, stderr = fixture.signalled(["reconverge", "--dry-run"], "plan", int(signal.SIGHUP), True,
                                           extra={"HUP_RECORD": str(record)}, ignore_hup=True)
    assert returncode == 0, stderr
    assert fixture.calls().endswith("make dry-run\nmake clean\n")
    assert set(record.read_text().split()) == {"True"}


@pytest.mark.parametrize(("name", "reviewed", "gated"), REVIEW_GATES)
@pytest.mark.parametrize("number", (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGHUP))
def test_signal_at_the_review_still_cleans_plaintext(tmp_path, name, reviewed, gated, number):
    fixture = Fixture(tmp_path)
    returncode, transcript = fixture.interactive([name], int(number))
    calls = fixture.calls()
    assert returncode == 128 + number, transcript
    assert f"make {reviewed}\n" in calls and f"make {gated}\n" not in calls
    assert calls.endswith("make clean\n") and not fixture.secrets().exists()


@pytest.mark.parametrize(("name", "reviewed", "gated"), REVIEW_GATES)
@pytest.mark.parametrize("number", (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGHUP))
@pytest.mark.parametrize("partial", (False, True), ids=("canonical", "noncanonical-partial"))
def test_worker_signal_at_review_needs_no_terminal_input(tmp_path, name, reviewed, gated, number, partial):
    fixture = Fixture(tmp_path)
    master, slave = pty.openpty()
    reader, writer = os.pipe()
    bootstrap = '''import os, runpy, signal, sys, threading
fd = int(os.environ.pop("WORKER_SIGNAL_FD"))
number = int(os.environ.pop("WORKER_SIGNAL_NUMBER"))
def receive():
    os.read(fd, 1)
    signal.pthread_kill(threading.get_ident(), number)
threading.Thread(target=receive, daemon=True).start()
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
    child = subprocess.Popen(
        [sys.executable, "-c", bootstrap, *fixture.argv([name], True)[1:]],
        stdin=slave, stderr=slave, stdout=subprocess.DEVNULL, pass_fds=(reader,),
        env=fixture.environment({"WORKER_SIGNAL_FD": reader, "WORKER_SIGNAL_NUMBER": number}),
    )
    os.close(slave)
    os.close(reader)
    transcript = b""
    try:
        deadline = time.monotonic() + 15
        while b"[y/N]" not in transcript:
            assert time.monotonic() < deadline and child.poll() is None, transcript
            if select.select([master], [], [], 0.05)[0]:
                transcript += os.read(master, 8192)
        if partial:
            attributes = termios.tcgetattr(master)
            attributes[3] &= ~termios.ICANON
            termios.tcsetattr(master, termios.TCSANOW, attributes)
            os.write(master, b"y")
        os.write(writer, b"x")
        child.wait(timeout=3)
        assert child.returncode == 128 + number, transcript
        calls = fixture.calls()
        assert f"make {reviewed}\n" in calls and f"make {gated}\n" not in calls
        assert calls.count("make clean\n") == 1 and not fixture.secrets().exists()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
        os.close(master)
        os.close(writer)


@pytest.mark.parametrize(("name", "reviewed", "gated"), REVIEW_GATES)
@pytest.mark.parametrize(("answers", "accepted"), ((b"y\nn\n", False), (b"\ny\n", True),
                                                (b"y\ninvalid\nn\n", False)))
def test_queued_answers_keep_initial_and_review_authority_separate(tmp_path, name, reviewed, gated,
                                                                 answers, accepted):
    fixture = Fixture(tmp_path)
    returncode, transcript = fixture.interactive([name], answers, yes=False)
    assert (returncode == 0) is accepted, transcript
    assert (f"make {gated}\n" in fixture.calls()) is accepted
    assert f"make {reviewed}\n" in fixture.calls()
    assert fixture.calls().count("make clean\n") == 1 and not fixture.secrets().exists()


@pytest.mark.parametrize(("name", "reviewed", "gated"), REVIEW_GATES)
def test_eof_at_review_cleans_plaintext(tmp_path, name, reviewed, gated):
    fixture = Fixture(tmp_path)
    returncode, transcript = fixture.interactive([name], b"\x04")
    assert returncode != 0 and "terminal input closed" in transcript
    assert f"make {reviewed}\n" in fixture.calls() and f"make {gated}\n" not in fixture.calls()
    assert fixture.calls().count("make clean\n") == 1 and not fixture.secrets().exists()


@pytest.mark.parametrize(("name", "reviewed", "gated"), REVIEW_GATES)
@pytest.mark.parametrize("number", commands.REVIEW_SIGNALS)
def test_ignored_signal_survives_review_and_make_children(tmp_path, name, reviewed, gated, number):
    fixture = Fixture(tmp_path)
    record = tmp_path / "ignored"
    returncode, transcript = fixture.interactive(
        [name], b"y\n", ignore=number,
        extra={"SIGNAL_RECORD": record, "IGNORED_SIGNAL": int(number)},
    )
    assert returncode == 0, transcript
    assert f"make {gated}\n" in fixture.calls()
    assert fixture.calls().count("make clean\n") == 1 and not fixture.secrets().exists()
    assert set(record.read_text().split()) == {"True"}


@pytest.mark.parametrize("timing", ("recorded", "answer-first", "signal-first"))
def test_review_prioritizes_first_signal_over_ready_answer(tmp_path, monkeypatch, timing):
    opened = []

    async def exercise():
        with commands.StopSignals() as stop:
            async def answer(_label, default):
                opened.append(default)
                if timing == "answer-first":
                    asyncio.get_running_loop().call_soon(stop._record, signal.SIGTERM)
                else:
                    stop._record(signal.SIGTERM)
                return True

            monkeypatch.setattr(commands, "confirm_async", answer)
            if timing == "recorded":
                stop._record(signal.SIGQUIT)
                stop._record(signal.SIGTERM)
            with pytest.raises(commands.OperationInterrupted) as failure:
                await commands.require_review(fake_ctx(tmp_path), "Review?", stop)
            expected = signal.SIGQUIT if timing == "recorded" else signal.SIGTERM
            assert failure.value.exit_code == 128 + expected
            assert opened == ([] if timing == "recorded" else [False])
            assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    asyncio.run(exercise())


@pytest.mark.parametrize("module", (deploy, reconverge), ids=("deploy", "reconverge"))
@pytest.mark.parametrize("cleanup_fails", (False, True))
@pytest.mark.parametrize("primary", ("review-cancel", "step-error"))
def test_pipeline_retains_cleanup_through_repeated_cancellation(tmp_path, monkeypatch, module,
                                                               cleanup_fails, primary):
    master, slave = pty.openpty()
    stdin = os.fdopen(os.dup(slave), encoding="utf-8")
    stderr = os.fdopen(os.open(os.ttyname(slave), os.O_WRONLY), "w", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stderr", stderr)
    flags = fcntl.fcntl(stdin.fileno(), fcntl.F_GETFL)
    original = RuntimeError("primary step error")
    ctx = fake_ctx(tmp_path)
    calls = []

    async def exercise():
        loop = asyncio.get_running_loop()
        reviewing, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        real_add = loop.add_reader
        removed = []
        real_remove = loop.remove_reader

        def add_reader(fd, callback):
            real_add(fd, callback)
            reviewing.set()

        def remove_reader(fd):
            removed.append(fd)
            return real_remove(fd)

        monkeypatch.setattr(loop, "add_reader", add_reader)
        monkeypatch.setattr(loop, "remove_reader", remove_reader)

        async def run(command, explain):
            name = command.argv[0]
            calls.append(name)
            if name == "decrypt":
                ctx.secrets_file.write_text("synthetic: true\n")
            if name == "plan" and primary == "step-error":
                raise original
            if name == "clean":
                if reviewing.is_set():
                    assert len(removed) == 1 and removed[0] != stdin.fileno()
                    with pytest.raises(OSError):
                        os.fstat(removed[0])
                assert fcntl.fcntl(stdin.fileno(), fcntl.F_GETFL) == flags
                cleaning.set()
                await release.wait()
                ctx.secrets_file.unlink()
                if cleanup_fails:
                    raise RuntimeError("cleanup failed")

        async def limit(*_args):
            return "fixture-node"

        monkeypatch.setattr(Cmd, "run", run)
        monkeypatch.setattr(reconverge.ansible, "scoped_limit", limit)
        args = Namespace(skip_precheck=False, tag_on_success=False, host=None, dry_run=False)
        task = asyncio.create_task(module.run(ctx, args))
        try:
            if primary == "review-cancel":
                await reviewing.wait()
                task.cancel("primary cancellation")
            await cleaning.wait()
            assert ctx.secrets_file.exists()
            task.cancel("later cancellation")
            delivered = loop.create_future()
            loop.call_soon(delivered.set_result, None)
            await delivered
            assert not task.done()
            task.cancel("last cancellation")
            release.set()
            if primary == "review-cancel":
                with pytest.raises(asyncio.CancelledError, match="primary cancellation"):
                    await task
            else:
                with pytest.raises(RuntimeError) as failure:
                    await task
                assert failure.value is original
            assert calls.count("clean") == 1 and not ctx.secrets_file.exists()
            assert "apply" not in calls and "deploy" not in calls
            assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(exercise())
    finally:
        stdin.close()
        stderr.close()
        os.close(slave)
        os.close(master)


@pytest.mark.parametrize(("name", "reviewed", "gated"), REVIEW_GATES)
@pytest.mark.parametrize(("answer", "accepted"), ((b"n\n", False), (b"y\n", True)))
def test_launcher_uses_controlling_terminal_for_both_confirmations(tmp_path, name, reviewed, gated,
                                                                  answer, accepted):
    fixture = Fixture(tmp_path)
    pid, terminal = pty.fork()
    if pid == 0:
        reader, writer = os.pipe()
        os.write(writer, b"y\ny\n")
        os.close(writer)
        os.dup2(reader, 0)
        os.close(reader)
        os.execve(sys.executable, fixture.argv([name], False), fixture.environment())
    reaped = False
    transcript = b""
    try:
        deadline = time.monotonic() + 15
        for marker, response in ((b"[Y/n]", b"y\n"), (b"[y/N]", answer)):
            while marker not in transcript:
                assert time.monotonic() < deadline, transcript
                if select.select([terminal], [], [], 0.05)[0]:
                    transcript += os.read(terminal, 8192)
            os.write(terminal, response)
        while True:
            assert time.monotonic() < deadline, transcript
            if select.select([terminal], [], [], 0.05)[0]:
                try:
                    transcript += os.read(terminal, 8192)
                except OSError as error:
                    # A closed PTY slave reports EOF as EIO on this read path.
                    if error.errno != errno.EIO:
                        raise
            found, status = os.waitpid(pid, os.WNOHANG)
            if found:
                reaped = True
                break
        assert os.WIFEXITED(status) and (os.WEXITSTATUS(status) == 0) is accepted, transcript
        assert f"make {reviewed}\n" in fixture.calls()
        assert (f"make {gated}\n" in fixture.calls()) is accepted
        assert fixture.calls().count("make clean\n") == 1 and not fixture.secrets().exists()
    finally:
        if not reaped:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        os.close(terminal)


@pytest.mark.parametrize("name", ("deploy", "reconverge"))
@pytest.mark.parametrize("number", (*commands.REVIEW_SIGNALS, signal.SIGKILL))
def test_initial_prompt_signals_leave_inherited_terminal_flags_unchanged(tmp_path, name, number):
    fixture = Fixture(tmp_path)
    master, slave = pty.openpty()
    # A separate stderr description keeps Darwin's write bookkeeping out of
    # the inherited stdin flags that the parent must retain unchanged.
    error_fd = os.open(os.ttyname(slave), os.O_WRONLY | os.O_NOCTTY)
    before = fcntl.fcntl(slave, fcntl.F_GETFL)
    child = subprocess.Popen(
        fixture.argv([name], False), stdin=slave, stderr=error_fd,
        stdout=subprocess.DEVNULL, env=fixture.environment(),
    )
    transcript = b""
    try:
        deadline = time.monotonic() + 15
        while b"[Y/n]" not in transcript:
            assert time.monotonic() < deadline and child.poll() is None, transcript
            if select.select([master], [], [], 0.05)[0]:
                transcript += os.read(master, 8192)
        during = fcntl.fcntl(slave, fcntl.F_GETFL)
        os.kill(child.pid, number)
        child.wait(timeout=3)
        assert child.returncode == -number, transcript
        assert during == before
        assert fcntl.fcntl(slave, fcntl.F_GETFL) == before
        assert "make " not in fixture.calls() and not fixture.secrets().exists()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
        os.close(error_fd)
        os.close(slave)
        os.close(master)
