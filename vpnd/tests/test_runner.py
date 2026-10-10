from pathlib import Path
from dataclasses import replace
import asyncio
import os
import json
import pytest
from vpnd.config import Context
from vpnd.runner import Cmd, CapturePolicy
from vpnd.runner import make, ansible, terraform, sops


def fake_ctx(root=Path("/repo"), explain=False):
    return Context(
        root,
        root / "ansible",
        root / "terraform/providers/upcloud",
        "prod",
        "upcloud",
        Path("/config/prod.secrets.sops.yaml"),
        Path("/tmp/vpn-prod.secrets.yaml"),
        Path("/config"),
        explain,
        True,
    )


# Rust test: vpnd/src/runner/process.rs::explain_plain_program_no_env_no_cwd
def test_explain_plain_program_no_env_no_cwd():
    assert Cmd.new("echo").arg("hello").explain() == "echo hello"


# Rust test: vpnd/src/runner/process.rs::explain_arg_with_spaces_is_quoted
def test_explain_arg_with_spaces_is_quoted():
    s = Cmd.new("echo").arg("hello world").explain()
    assert "'hello world'" in s or '"hello world"' in s


# Rust test: vpnd/src/runner/process.rs::explain_arg_with_single_quote
def test_explain_arg_with_single_quote():
    s = Cmd.new("echo").arg("it's here").explain()
    assert "it" in s and "s here" in s
    assert "it's here" not in s


# Rust test: vpnd/src/runner/process.rs::explain_arg_with_double_quote
def test_explain_arg_with_double_quote():
    s = Cmd.new("echo").arg('say "hi"').explain()
    assert len(s) > 10
    assert s != 'echo say "hi"'


# Rust test: vpnd/src/runner/process.rs::explain_arg_with_dollar_var
def test_explain_arg_with_dollar_var():
    assert not Cmd.new("echo").arg("$HOME").explain().endswith(" $HOME")


# Rust test: vpnd/src/runner/process.rs::explain_arg_with_newline
def test_explain_arg_with_newline():
    s = Cmd.new("echo").arg("line1\nline2").explain()
    assert "\n" not in s or "'" in s or '"' in s


# Rust test: vpnd/src/runner/process.rs::explain_env_vars_appear_before_program
def test_explain_env_vars_appear_before_program():
    s = Cmd.new("make").env("FOO", "bar").env("BAZ", "qux").arg("target").explain()
    assert s.index("FOO=") < s.index("BAZ=") < s.index("make")


# Rust test: vpnd/src/runner/process.rs::explain_env_value_with_spaces_is_quoted
def test_explain_env_value_with_spaces_is_quoted():
    assert "K=value with spaces" not in Cmd.new("echo").env("K", "value with spaces").explain()


# Rust test: vpnd/src/runner/process.rs::explain_cwd_wraps_with_cd_and_ampersand
def test_explain_cwd_wraps_with_cd_and_ampersand():
    s = Cmd.new("make").arg("all").cwd(Path("/some/path")).explain()
    assert s.startswith("(cd ") and "&& make" in s and s.endswith(")")


# Rust test: vpnd/src/runner/process.rs::explain_cwd_with_spaces_is_quoted
def test_explain_cwd_with_spaces_is_quoted():
    assert (
        "(cd /path with spaces" not in Cmd.new("make").cwd(Path("/path with spaces/repo")).explain()
    )


# Rust test: vpnd/src/runner/process.rs::explain_env_ordering_is_stable
def test_explain_env_ordering_is_stable():
    s = Cmd.new("x").env("ZEBRA", "1").env("ALPHA", "2").env("MANGO", "3").explain()
    assert s.index("ZEBRA=") < s.index("ALPHA=") < s.index("MANGO=")


# Rust test: vpnd/src/runner/process.rs::sensitive_paths_are_masked_before_shell_quoting_without_changing_argv
def test_sensitive_paths_are_masked_before_shell_quoting_without_changing_argv():
    path = "/private/O'Brien/runtime secrets.yaml"
    cmd = Cmd.new("make").arg(f"SECRETS_FILE={path}").env("VPN_SECRETS_FILE", path).sensitive(path)
    assert "redacted" in cmd.redacted_explain() and "Brien" not in cmd.redacted_explain()
    assert cmd.argv[0] == f"SECRETS_FILE={path}" and cmd.environment[0][1] == path


# Rust test: vpnd/src/runner/make.rs::target_pushes_env_then_provider_after_name
def test_target_pushes_env_then_provider_after_name():
    s = make.target(fake_ctx(), "deploy").explain()
    assert s.index("deploy") < s.index("ENV=prod") < s.index("PROVIDER=upcloud")


# Rust test: vpnd/src/runner/make.rs::target_carries_resolved_secrets_file_after_provider
def test_target_carries_resolved_secrets_file_after_provider():
    ctx = fake_ctx()
    s = make.target(ctx, "decrypt").explain()
    assert s.index("PROVIDER=upcloud") < s.index(f"SECRETS_FILE={ctx.secrets_file}")


# Rust test: vpnd/src/runner/make.rs::target_program_is_make
def test_target_program_is_make():
    assert "make" in make.target(fake_ctx(), "deploy").explain()


# Rust test: vpnd/src/runner/make.rs::target_cwd_is_repo_root
def test_target_cwd_is_repo_root():
    assert "/repo" in make.target(fake_ctx(), "deploy").explain()


# Rust test: vpnd/src/runner/make.rs::target_with_appends_kvs_after_provider
def test_target_with_appends_kvs_after_provider():
    s = make.target_with(
        fake_ctx(), "emit-singbox", [("CLIENT", "phone"), ("EXTRA", "1")]
    ).explain()
    assert s.index("PROVIDER=") < s.index("CLIENT=phone") < s.index("EXTRA=1")


# Rust test: vpnd/src/runner/make.rs::target_with_no_extra_kvs_matches_target
def test_target_with_no_extra_kvs_matches_target():
    assert (
        make.target(fake_ctx(), "decrypt").explain()
        == make.target_with(fake_ctx(), "decrypt", []).explain()
    )


# Rust test: vpnd/src/runner/make.rs::per_key_acceptance_table_passes_legitimate_values
def test_per_key_acceptance_table_passes_legitimate_values():
    for key, value in [
        ("CLIENT", "phone-2"),
        ("HOST", "203.0.113.5"),
        ("TARGET_ID", "p0-direct-1"),
        ("MATRIX_CONFIG", "/tmp/probe-matrix.yaml"),
        ("PLAN", "/plans/fleet-rotation.yaml"),
        ("ENV", "prod"),
        ("PROVIDER", "upcloud"),
        ("SECRETS_FILE", "/run/user/1000/vpn-runtime/vpn-prod.secrets.yaml"),
        ("RESUME", "1"),
    ]:
        assert (
            f"{key}={value}"
            in make.target_with(fake_ctx(), "probe-matrix-cell", [(key, value)]).explain()
        )


# Rust test: vpnd/src/runner/make.rs::per_key_rejection_table_aborts_naming_key_and_rule
def test_per_key_rejection_table_aborts_naming_key_and_rule():
    for key, value, rule in [
        ("CLIENT", "$(shell touch /tmp/pwned)", "identifier"),
        ("HOST", "$(shell reboot)", "IPv4 literal"),
        ("HOST", "203.0.113.5; rm -rf /", "IPv4 literal"),
        ("TARGET_ID", "p0;id", "identifier"),
        ("MATRIX_CONFIG", "relative/config.yaml", "path"),
        ("MATRIX_CONFIG", "/tmp/../etc/passwd", "path"),
        ("MATRIX_CONFIG", "/tmp/space name.yaml", "path"),
        ("PLAN", "../escape.yaml", "path"),
        ("SECRETS_FILE", "/tmp/$(id)/vpn-prod.secrets.yaml", "runtime path"),
        ("SECRETS_FILE", "/tmp/a #/vpn-prod.secrets.yaml", "runtime path"),
        ("SECRETS_FILE", "/tmp/a b/vpn-prod.secrets.yaml", "runtime path"),
        ("ENV", "prod;id", "identifier"),
        ("PROVIDER", "$(shell id)", "identifier"),
    ]:
        with pytest.raises(ValueError) as error:
            make.validate_kv(key, value)
        assert key in str(error.value) and rule in str(error.value)


# Rust test: vpnd/src/runner/make.rs::unknown_keys_fail_closed_to_identifier_charset
def test_unknown_keys_fail_closed_to_identifier_charset():
    make.validate_kv("BRAND_NEW_KEY", "ok")
    with pytest.raises(ValueError) as error:
        make.validate_kv("BRAND_NEW_KEY", "$(x)")
    assert "BRAND_NEW_KEY" in str(error.value) and "identifier" in str(error.value)


# Rust test: vpnd/src/runner/make.rs::target_gates_context_values_before_building_invocation
def test_target_gates_context_values_before_building_invocation():
    for key, ctx, name in [
        ("ENV", replace(fake_ctx(), env="prod;id"), "deploy"),
        ("PROVIDER", replace(fake_ctx(), provider="$(shell id)"), "plan"),
        (
            "SECRETS_FILE",
            replace(fake_ctx(), secrets_file=Path("/tmp/$(id)/vpn-prod.secrets.yaml")),
            "decrypt",
        ),
    ]:
        with pytest.raises(ValueError, match=key):
            make.target(ctx, name)


# Rust test: vpnd/src/runner/make.rs::secrets_file_rejection_redacts_the_value
def test_secrets_file_rejection_redacts_the_value():
    with pytest.raises(ValueError) as error:
        make.validate_kv("SECRETS_FILE", "/tmp/$(id)/vpn-prod.secrets.yaml")
    assert "SECRETS_FILE" in str(error.value) and "/tmp/$(id)" not in str(error.value)


# Rust test: vpnd/src/runner/make.rs::target_with_first_failing_key_aborts_and_nothing_spawns
def test_target_with_first_failing_key_aborts_and_nothing_spawns():
    with pytest.raises(ValueError, match="EXTRA"):
        make.target_with(fake_ctx(), "emit-singbox", [("CLIENT", "phone"), ("EXTRA", "`id`")])
    with pytest.raises(ValueError) as error:
        make.target_with(fake_ctx(), "test-tls-policing", [("HOST", "not-an-ip")])
    assert "HOST" in str(error.value) and "IPv4 literal" in str(error.value)


# Rust test: vpnd/src/runner/terraform.rs::init_uses_environment_wrapper
def test_init_uses_environment_wrapper():
    s = terraform.init(fake_ctx()).explain()
    assert "scripts/terraform-env.sh" in s and "PROVIDER=upcloud" in s and "ENV=prod" in s


# Rust test: vpnd/src/runner/terraform.rs::init_contains_init_subcommand
def test_init_contains_init_subcommand():
    assert "init" in terraform.init(fake_ctx()).explain()


# Rust test: vpnd/src/runner/terraform.rs::plan_contains_var_file_for_env
def test_plan_contains_var_file_for_env():
    assert "prod.tfvars" in terraform.plan(fake_ctx()).explain()


# Rust test: vpnd/src/runner/terraform.rs::plan_contains_out_flag
def test_plan_contains_out_flag():
    assert "prod.tfplan" in terraform.plan(fake_ctx()).explain()


# Rust test: vpnd/src/runner/terraform.rs::apply_references_tfplan
def test_apply_references_tfplan():
    assert "prod.tfplan" in terraform.apply(fake_ctx()).explain()


# Rust test: vpnd/src/runner/terraform.rs::output_contains_json_flag
def test_output_contains_json_flag():
    assert "-json" in terraform.output(fake_ctx()).explain()


# Rust test: vpnd/src/runner/terraform.rs::all_cmds_use_environment_wrapper
def test_all_cmds_use_environment_wrapper():
    for function in (terraform.plan, terraform.apply, terraform.output):
        assert "scripts/terraform-env.sh" in function(fake_ctx()).explain()


# Rust test: vpnd/src/runner/sops.rs::decrypt_program_is_sops
def test_decrypt_program_is_sops():
    s = sops.decrypt(fake_ctx()).explain()
    assert s.startswith("sops") or " sops " in s


# Rust test: vpnd/src/runner/sops.rs::decrypt_contains_decrypt_flag
def test_decrypt_contains_decrypt_flag():
    assert "--decrypt" in sops.decrypt(fake_ctx()).explain()


# Rust test: vpnd/src/runner/sops.rs::decrypt_contains_output_flag_and_secrets_file
def test_decrypt_contains_output_flag_and_secrets_file():
    s = sops.decrypt(fake_ctx()).explain()
    assert "--output" in s and "/tmp/vpn-prod.secrets.yaml" in s


# Rust test: vpnd/src/runner/sops.rs::decrypt_contains_sops_source_file
def test_decrypt_contains_sops_source_file():
    assert "prod.secrets.sops.yaml" in sops.decrypt(fake_ctx()).explain()


# Rust test: vpnd/src/runner/ansible.rs::playbook_program_is_ansible_playbook
def test_playbook_program_is_ansible_playbook():
    assert "ansible-playbook" in ansible.playbook(fake_ctx(), "site").explain()


# Rust test: vpnd/src/runner/ansible.rs::playbook_path_contains_playbook_name
def test_playbook_path_contains_playbook_name():
    assert "rotate-credentials.yml" in ansible.playbook(fake_ctx(), "rotate-credentials").explain()


# Rust test: vpnd/src/runner/ansible.rs::playbook_sets_ansible_config_env
def test_playbook_sets_ansible_config_env():
    s = ansible.playbook(fake_ctx(), "site").explain()
    assert "ANSIBLE_CONFIG=" in s and "ansible.cfg" in s


# Rust test: vpnd/src/runner/ansible.rs::playbook_sets_vpn_secrets_file_env
def test_playbook_sets_vpn_secrets_file_env():
    s = ansible.playbook(fake_ctx(), "site").explain()
    assert "VPN_SECRETS_FILE=" in s and "/tmp/vpn-prod.secrets.yaml" in s


# Rust test: vpnd/src/runner/ansible.rs::dry_run_appends_check_and_diff
def test_dry_run_appends_check_and_diff():
    s = ansible.dry_run(fake_ctx()).explain()
    assert "--check" in s and "--diff" in s


# Rust test: vpnd/src/runner/ansible.rs::site_uses_site_playbook
def test_site_uses_site_playbook():
    assert "site.yml" in ansible.site(fake_ctx()).explain()


# Rust test: vpnd/src/runner/ansible.rs::rotate_uses_rotate_credentials_playbook
def test_rotate_uses_rotate_credentials_playbook():
    assert "rotate-credentials.yml" in ansible.rotate(fake_ctx()).explain()


def inventory():
    return {
        "vpn": {"children": ["cohort"]},
        "cohort": {"hosts": ["fixture-node", "staging-node", "other-provider"]},
        "_meta": {
            "hostvars": {
                "fixture-node": {
                    "env": "prod",
                    "provider": "upcloud",
                    "ansible_host": "100.64.0.5",
                    "vpn_service_address": "203.0.113.5",
                },
                "staging-node": {
                    "env": "staging",
                    "provider": "upcloud",
                    "ansible_host": "203.0.113.6",
                },
                "other-provider": {
                    "env": "prod",
                    "provider": "vultr",
                    "ansible_host": "203.0.113.7",
                },
            }
        },
    }


# Rust test: vpnd/src/runner/ansible.rs::inventory_scope_uses_public_address_and_exact_host_key
def test_inventory_scope_uses_public_address_and_exact_host_key():
    raw = json.dumps(inventory())
    assert ansible.inventory_limit(raw, "prod", "upcloud", "203.0.113.5") == "fixture-node"
    assert ansible.inventory_limit(raw, "prod", "upcloud") == "fixture-node"
    for provider, ip in (("upcloud", "100.64.0.5"), ("upcloud", "203.0.113.6"), ("hetzner", None)):
        with pytest.raises(ValueError):
            ansible.inventory_limit(raw, "prod", provider, ip)


# Rust test: vpnd/src/runner/ansible.rs::inventory_scope_rejects_ambiguous_addresses_and_group_collisions
def test_inventory_scope_rejects_ambiguous_addresses_and_group_collisions():
    raw = inventory()
    raw["_meta"]["hostvars"]["staging-node"].update(env="prod", ansible_host="203.0.113.5")
    with pytest.raises(ValueError):
        ansible.inventory_limit(json.dumps(raw), "prod", "upcloud", "203.0.113.5")
    raw = inventory()
    raw["fixture-node"] = {"hosts": ["staging-node"]}
    with pytest.raises(ValueError):
        ansible.inventory_limit(json.dumps(raw), "prod", "upcloud", "203.0.113.5")


# Rust test: vpnd/src/runner/ansible.rs::inventory_scope_rejects_pattern_names_and_missing_scope_metadata
def test_inventory_scope_rejects_pattern_names_and_missing_scope_metadata():
    for name in ("all", "vpn:*", "host,other", "@targets", "[nodes]", "!other"):
        raw = inventory()
        variables = raw["_meta"]["hostvars"].pop("fixture-node")
        raw["_meta"]["hostvars"][name] = variables
        raw["cohort"]["hosts"][0] = name
        with pytest.raises(ValueError):
            ansible.inventory_limit(json.dumps(raw), "prod", "upcloud")
    raw = inventory()
    raw["_meta"]["hostvars"]["fixture-node"]["env"] = None
    with pytest.raises(ValueError):
        ansible.inventory_limit(json.dumps(raw), "prod", "upcloud")


# Rust test: vpnd/tests/runner_execution.rs::run_and_capture_report_real_process_outcomes
def test_run_and_capture_report_real_process_outcomes():
    async def exercise():
        foreground = await Cmd.new("sh").args(["-c", "ps -o pgid= -p $$"]).capture()
        assert int(foreground.stdout.strip()) == os.getpgrp()
        output = await Cmd.new("sh").args(["-c", "printf 'first\\nsecond'"]).capture()
        assert output.rc == 0 and output.stdout == "first\nsecond\n"
        assert await Cmd.new("sh").args(["-c", "exit 0"]).run() == 0
        for capture in (False, True):
            for script, expected in (("exit 17", "rc=17"), ("kill -TERM $$", "rc=-1")):
                cmd = Cmd.new("sh").args(["-c", script])
                with pytest.raises(RuntimeError, match=expected):
                    await (cmd.capture() if capture else cmd.run())
            cmd = Cmd.new("/vpnd-no-such-command")
            with pytest.raises(OSError):
                await (cmd.capture() if capture else cmd.run())

    asyncio.run(exercise())


# Rust test: vpnd/tests/runner_execution.rs::capture_timeout_terminates_real_make_child_and_grandchild
def test_capture_timeout_terminates_real_make_child_and_grandchild(tmp_path):
    import subprocess
    import signal

    assert (
        "GNU Make"
        in subprocess.run(["make", "--version"], capture_output=True, text=True, check=True).stdout
    )
    pids = tmp_path / "processes"
    (tmp_path / "Makefile").write_text("probe:\n\t@sh child.sh\n")
    (tmp_path / "child.sh").write_text(
        'sleep 60 &\ngrandchild=$!\nprintf \'%s\\n\' "$PPID" "$$" "$grandchild" > "$PIDS.tmp"\nmv "$PIDS.tmp" "$PIDS"\nwait\n'
    )

    def running(pid):
        status = subprocess.run(["ps", "-o", "stat=", "-p", pid], capture_output=True, text=True)
        text = status.stdout.strip()
        return status.returncode == 0 and bool(text) and not text.startswith("Z")

    async def exercise():
        cmd = (
            Cmd.new("make")
            .capture_policy(CapturePolicy.OWNED_PROCESS_GROUP)
            .arg("probe")
            .cwd(tmp_path)
            .env("PIDS", pids)
            .env("MAKEFLAGS", "")
            .env("MFLAGS", "")
        )
        capture = asyncio.create_task(cmd.capture())
        try:
            deadline = asyncio.get_running_loop().time() + 5
            while not pids.exists():
                assert not capture.done() and asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.02)
            recorded = pids.read_text().splitlines()
            assert len(recorded) == 3 and all(map(running, recorded))
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(capture, 0.05)
            for _ in range(50):
                if all(not running(pid) for pid in recorded):
                    return
                await asyncio.sleep(0.02)
            assert all(not running(pid) for pid in recorded)
        finally:
            if not capture.done():
                capture.cancel()
                try:
                    await capture
                except asyncio.CancelledError:
                    # Teardown requested cancellation and waited for owned
                    # process cleanup before accepting its acknowledgement.
                    pass
            if pids.exists():
                for pid in pids.read_text().splitlines():
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except ProcessLookupError:
                        # Successful cancellation already removed this child.
                        pass

    asyncio.run(exercise())


def test_capture_preserves_non_newline_control_separators():
    async def exercise():
        output = await Cmd.new("sh").args(["-c", "printf 'a\\034b\\r\\nc\\r'"]).capture()
        assert output.stdout == "a\x1cb\nc\r\n"

    asyncio.run(exercise())


def test_make_isolates_parent_control_environment_before_json_capture(tmp_path, monkeypatch):
    inherited = {
        "MAKELEVEL": "1",
        "MAKEFLAGS": "--print-directory",
        "MFLAGS": "--print-directory",
        "GNUMAKEFLAGS": "--print-directory",
        "MAKEFILES": str(tmp_path / "parent.mk"),
    }
    for key, value in inherited.items():
        monkeypatch.setenv(key, value)
    (tmp_path / "parent.mk").write_text("$(error inherited parent Make input)\n")
    (tmp_path / "Makefile").write_text('probe:\n\t@printf \'%s\\n\' \'{"status":"ok"}\'\n')

    async def exercise():
        for detailed in (False, True):
            command = make.target(fake_ctx(tmp_path), "probe")
            output = await (command.capture_detailed() if detailed else command.capture())
            assert output.rc == 0
            assert output.stdout == '{"status":"ok"}\n'
            assert json.loads(output.stdout) == {"status": "ok"}
            assert output.stderr == ""
        assert {key: os.environ[key] for key in inherited} == inherited

    asyncio.run(exercise())


def test_owned_capture_reserves_exited_leader_until_pipe_cleanup(tmp_path):
    import signal
    import subprocess

    pids = tmp_path / "pids"

    def status(pid):
        return subprocess.run(
            ["ps", "-o", "stat=", "-p", pid], capture_output=True, text=True, check=False
        ).stdout.strip()

    async def exercise():
        cmd = (
            Cmd.new("sh")
            .args(["-c", 'sleep 60 & printf \'%s\\n\' "$$" "$!" > "$PIDS"; exit 0'])
            .env("PIDS", pids)
            .capture_policy(CapturePolicy.OWNED_PROCESS_GROUP)
        )
        task = asyncio.create_task(cmd.capture())
        try:
            deadline = asyncio.get_running_loop().time() + 5
            while not pids.exists():
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.02)
            leader, descendant = pids.read_text().splitlines()
            while not status(leader).startswith("Z"):
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.02)
            assert status(descendant) and not status(descendant).startswith("Z")
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(task, 0.05)
            assert not status(leader)
            for _ in range(50):
                observed = status(descendant)
                if not observed or observed.startswith("Z"):
                    break
                await asyncio.sleep(0.02)
            assert not status(descendant) or status(descendant).startswith("Z")
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    # Teardown requested cancellation and waited for owned
                    # process cleanup before accepting its acknowledgement.
                    pass
            if pids.exists():
                for pid in pids.read_text().splitlines():
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except ProcessLookupError:
                        # Successful cancellation already removed this child.
                        pass

    asyncio.run(exercise())


def test_capture_is_not_queued_behind_global_executor(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    async def exercise():
        occupied = threading.Event()
        release = threading.Event()
        executor = ThreadPoolExecutor(max_workers=1)
        asyncio.get_running_loop().set_default_executor(executor)

        def blocker():
            occupied.set()
            release.wait(5)

        blocking = executor.submit(blocker)
        assert occupied.wait(1)
        try:
            output = await asyncio.wait_for(
                Cmd.new("sh").args(["-c", "printf started"]).capture(), 1
            )
            assert output.stdout == "started\n"
        finally:
            release.set()
            blocking.result(timeout=2)

    asyncio.run(exercise())


def test_cancelled_worker_never_spawns_a_queued_command(tmp_path):
    import threading

    marker = tmp_path / "must-not-exist"
    command = Cmd.new("sh").args(["-c", 'printf bad > "$MARKER"']).env("MARKER", marker)
    stopped = threading.Event()
    stopped.set()
    assert command._worker(stopped, True, True) == (0, b"", b"")
    assert not marker.exists()


def test_more_than_32_owned_captures_start_simultaneously(tmp_path):
    ready = tmp_path / "ready"
    ready.mkdir()
    hold = tmp_path / "hold"
    os.mkfifo(hold, 0o600)

    async def exercise():
        tasks = [
            asyncio.create_task(
                Cmd.new("sh")
                .args(["-c", ': > "$READY"; read line < "$HOLD"'])
                .env("READY", ready / str(index))
                .env("HOLD", hold)
                .capture_policy(CapturePolicy.OWNED_PROCESS_GROUP)
                .capture()
            )
            for index in range(40)
        ]
        try:
            deadline = asyncio.get_running_loop().time() + 10
            while len(list(ready.iterdir())) < len(tasks):
                assert not any(task.done() for task in tasks)
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.02)
            assert len(list(ready.iterdir())) == 40
        finally:
            for task in tasks:
                task.cancel()
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            assert all(isinstance(outcome, asyncio.CancelledError) for outcome in outcomes), [
                (index, type(outcome).__name__, repr(outcome))
                for index, outcome in enumerate(outcomes)
                if not isinstance(outcome, asyncio.CancelledError)
            ]

    asyncio.run(exercise())
