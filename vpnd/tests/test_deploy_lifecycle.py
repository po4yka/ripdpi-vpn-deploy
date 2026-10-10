"""Real local subprocess orchestration; external infrastructure is doubled."""

from pathlib import Path
from dataclasses import replace
from argparse import Namespace
import asyncio
import os
import subprocess
import sys
import tarfile
import pytest
from vpnd.config import Context
from vpnd.commands import deploy, preflight, fleet, finish_with_cleanup, ensure_host_in_registry
from vpnd.runner import Cmd
from vpnd.state import Registry, Host

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts/vpnd.py"


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
  clean) rm -f "$secret"; exit "${CLEAN_EXIT:-0}" ;;
  test-tls-policing) test "$host" = 203.0.113.5 ;;
  emit-singbox) printf '%s\n' '{"outbounds":[]}' ;;
esac
if [ "${ECHO_SECRET_PATH:-0}" = 1 ]; then printf 'reading %s\n' "$secret"; fi
if [ "$target" = "${FAIL_TARGET:-none}" ]; then exit 31; fi
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
        return subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                "--root",
                str(self.root),
                "--env",
                "test",
                *(["--yes"] if yes else []),
                *args,
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
            input=input,
        )

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
