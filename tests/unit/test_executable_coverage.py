"""Execute skip-policy regressions and guard mandatory native/Go lane wiring."""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "body,expected",
    [
        ("pass", 0),
        ("pytest.skip('missing native tool')", 1),
        ("assert False", 1),
    ],
)
def test_required_lane_rejects_skips_and_failures(tmp_path, body, expected):
    (tmp_path / "conftest.py").write_text((ROOT / "tests/conftest.py").read_text())
    (tmp_path / "test_sample.py").write_text(
        f"import pytest\ndef test_sample():\n    {body}\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "--fail-on-skip", "-q"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == expected, result.stdout + result.stderr


def test_native_and_go_lanes_remain_executable_and_dependency_gated():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    for name, target in [
        ("native-runtime", "test-native-runtime"),
        ("go-helper", "test-probe-matrix-mtproto"),
    ]:
        job = jobs[name]
        assert name in jobs["required"]["needs"]
        assert (
            job["if"]
            == "${{ fromJSON(needs.selection.outputs.checks)['" + name + "'] }}"
        )
        assert "continue-on-error" not in job
        assert any(f"make {target}" in step.get("run", "") for step in job["steps"])
    native = jobs["native-runtime"]["steps"]
    assert any(s.get("uses") == "./.github/actions/setup-disposable-ci" for s in native)
    assert any(s.get("run") == 'sudo env "PATH=$PATH" make test-mtg-native-compatibility' for s in native)
    setup = yaml.safe_load(
        (ROOT / ".github/actions/setup-disposable-ci/action.yml").read_text()
    )
    terraform = next(
        s for s in setup["runs"]["steps"] if "setup-terraform@" in s.get("uses", "")
    )
    assert terraform["with"]["terraform_wrapper"] is False
    ech_step = next(step["run"] for step in native if "make test-hysteria-ech-runtime" in step.get("run", ""))
    assert "PATH=$PATH" in shlex.split(ech_step.replace("\\\n", ""))
    complete = next(step for step in native if step.get("name") == "Execute native tests with UID and GID capabilities")
    command = shlex.split(complete["run"].replace("\\\n", ""))
    assert command[:2] == ["sudo", "env"]
    assert command[-4:] == ["make", "test-native-runtime", "test-xhttp-delivery-matrix", "test-topology-authenticated-probes"]
    environment = {}
    for assignment in command[2:-4]:
        name, value = assignment.split("=", 1)
        assert name not in environment, f"duplicate native environment override: {name}"
        environment[name] = value
    assert environment["PATH"] == (
        "$NATIVE_RUNTIME_ROOT/.cache/native-transport-semantics/bin:$PATH"
    )
    assert environment["ALERTMANAGER_BIN"] == (
        "$NATIVE_RUNTIME_ROOT/.cache/native-alertmanager/alertmanager"
    )
    assert environment["NAIVE_NATIVE_BINARY"] == (
        "$NATIVE_RUNTIME_ROOT/.cache/p2-native-caddy/caddy"
    )
    pins = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    for variable, source, pin in (
        ("AWG_NATIVE_GO_SOURCE", "amneziawg-go", "amneziawg_go_commit"),
        ("AWG_NATIVE_TOOLS_SOURCE", "amneziawg-tools", "amneziawg_tools_commit"),
    ):
        assert environment[variable] == (
            f"$NATIVE_RUNTIME_ROOT/.cache/native-transport-semantics/{source}-{pins[pin]}"
        )

    early = next(step for step in native if step.get("name") ==
                 "Check native AWG rollback before the complete runtime suite")
    early_command = shlex.split(early["run"].replace("\\\n", ""))
    assert early_command[:2] == ["sudo", "env"]
    assert early_command[-2:] == ["make", "test-awg-dualstack-runtime"]
    assert sum(shlex.split(step.get("run", "")).count("test-awg-dualstack-runtime")
               for step in native) == 1
    assert native.index(early) < next(index for index, step in enumerate(native)
                                    if "make test-hysteria-ech-runtime" in step.get("run", ""))
    early_environment = dict(assignment.split("=", 1) for assignment in early_command[2:-2])
    for variable in ("TRANSPORT_NATIVE_ISOLATED", "AWG_NATIVE_GO_SOURCE", "AWG_NATIVE_TOOLS_SOURCE", "PATH"):
        assert early_environment[variable] == environment[variable]
    assert "continue-on-error" not in early and "if" not in early


def native_staging_steps():
    steps = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["native-runtime"]["steps"]
    stage = next(step for step in steps if step.get("name") == "Stage trusted native runtime sources and artifacts")
    cleanup = next(step for step in steps if step.get("name") == "Remove owned native runtime staging")
    return steps, stage, cleanup


def test_native_root_consumers_follow_owned_staging_and_always_cleanup():
    steps, stage, cleanup = native_staging_steps()
    builds = [index for index, step in enumerate(steps) if "make native-" in step.get("run", "")]
    assert max(builds) < steps.index(stage)
    consumers = steps[steps.index(stage) + 1:steps.index(cleanup)]
    assert len(consumers) == 4
    for step in consumers:
        assert step["working-directory"] == "${{ env.NATIVE_RUNTIME_ROOT }}"
        assert "$GITHUB_WORKSPACE" not in step["run"]
    assert "sudo chown -hR 0:0" in stage["run"]
    assert "always()" in cleanup["if"] and "env.NATIVE_RUNTIME_ROOT != ''" in cleanup["if"]


@pytest.mark.parametrize("missing_artifact", [False, True])
def test_actual_native_staging_preserves_sources_and_scopes_cleanup(tmp_path, missing_artifact):
    _, stage_step, cleanup_step = native_staging_steps()
    workspace, runner, owned = (tmp_path / name for name in ("workspace", "runner", "owned"))
    for path in (workspace / ".cache", runner, owned):
        path.mkdir(parents=True)
    source = workspace / ".cache/binary"
    source.write_bytes(b"reviewed fixture artifact")
    source.chmod(0o755)
    (workspace / ".cache/alias").symlink_to("binary")
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"preserve unrelated authority")
    (workspace / "external-link").symlink_to(foreign)
    previous = [(path.stat().st_ino, path.stat().st_ctime_ns, path.read_bytes()) for path in (source, foreign)]
    if not missing_artifact:
        alertmanager = runner / "alertmanager-0.28.1.linux-amd64"
        alertmanager.mkdir()
        (alertmanager / "alertmanager").write_bytes(b"verified fixture download")
    environment_file = tmp_path / "github-env"
    environment_file.touch()
    environment = {**os.environ, "GITHUB_WORKSPACE": str(workspace), "RUNNER_TEMP": str(runner),
                   "GITHUB_ENV": str(environment_file)}
    prefix = owned / "ripdpi-native-runtime"
    # Execute the workflow shell. Only the privileged location, UID/GID and
    # sudo boundary change; cp, symlinks, ownership, traps and rm stay real.
    sudo = f'''sudo() {{
      if [[ "$1" == chown ]]; then
        [[ "$2" == -hR && "$3" == 0:0 ]] || return 91
        command chown -hR {os.geteuid()}:{os.getegid()} "$4"
      else
        command "$@"
      fi
    }}
'''
    stage_script = stage_step["run"].replace("/opt/ripdpi-native-runtime.XXXXXXXX", shlex.quote(str(prefix) + ".XXXXXXXX"))
    result = subprocess.run(["bash", "-c", sudo + stage_script], env=environment, capture_output=True, text=True, timeout=20, check=False)
    assert (result.returncode != 0) == missing_artifact, result.stdout + result.stderr
    assert previous == [(path.stat().st_ino, path.stat().st_ctime_ns, path.read_bytes()) for path in (source, foreign)]
    if missing_artifact:
        assert not list(owned.iterdir()) and environment_file.read_text() == ""
        return
    stage = Path(environment_file.read_text().strip().split("=", 1)[1])
    assert stage.parent == owned and stage.stat().st_mode & 0o777 == 0o755
    assert (stage / ".cache/binary").read_bytes() == source.read_bytes()
    assert (stage / ".cache/binary").stat().st_ino != source.stat().st_ino
    assert os.readlink(stage / ".cache/alias") == "binary"
    assert os.readlink(stage / "external-link") == str(foreign)
    assert (stage / ".cache/native-alertmanager/alertmanager").read_bytes() == b"verified fixture download"
    cleanup_script = cleanup_step["run"].replace("^/opt/ripdpi-native-runtime\\.", "^" + re.escape(str(prefix)) + "\\.")
    for target in (foreign, stage / "..", owned / "ripdpi-native-runtime.ABC12345"):
        if target.name == "ripdpi-native-runtime.ABC12345":
            target.symlink_to(foreign)
        refused = subprocess.run(["bash", "-c", sudo + cleanup_script], env={**environment, "NATIVE_RUNTIME_ROOT": str(target)}, capture_output=True, timeout=20, check=False)
        assert refused.returncode != 0 and stage.exists() and foreign.exists()
    removed = subprocess.run(["bash", "-c", sudo + cleanup_script], env={**environment, "NATIVE_RUNTIME_ROOT": str(stage)}, capture_output=True, timeout=20, check=False)
    assert removed.returncode == 0 and not stage.exists() and foreign.exists()


def test_local_and_ci_partition_native_tests_without_silent_skips():
    makefile = (ROOT / "Makefile").read_text()
    assert (
        'pytest tests/unit/ scripts/tests/ -m "not native_runtime" --fail-on-skip'
        in makefile
    )
    baseline = makefile.split('test-native-runtime:\n', 1)[1].split('\n\n', 1)[0]
    consumer = makefile.split('test-transport-runtime-acceptance:\n', 1)[1].split('\n\n', 1)[0]
    endpoints = makefile.split('test-xhttp-endpoint-contract:\n', 1)[1].split('\n\n', 1)[0]
    assert 'pytest tests/unit/ -m native_runtime' in baseline
    assert '--ignore=tests/unit/test_transport_runtime_acceptance_native.py' in baseline
    topology = makefile.split('test-topology-authenticated-probes:\n', 1)[1].split('\n\n', 1)[0]
    assert '--fail-on-skip' in topology and ' -k ' not in topology
    assert 'tests/unit/test_transport_runtime_acceptance_native.py' in consumer
    assert '--fail-on-skip' in baseline and '--fail-on-skip' in consumer and '--fail-on-skip' in endpoints
    assert '--ignore' not in consumer + endpoints and ' -k ' not in baseline + consumer + endpoints
    import subprocess
    import sys
    commands = [
        ['tests/unit/', '-m', 'native_runtime'],
        ['tests/unit/', '-m', 'native_runtime', '--ignore=tests/unit/test_transport_runtime_acceptance_native.py',
         '--ignore=tests/unit/test_xhttp_endpoint_contract_native.py',
         '--ignore=tests/unit/test_awg_device_binding_native.py', '--ignore=tests/unit/test_hysteria_ech_native.py',
         '--ignore=tests/unit/test_topology_authenticated_probes_native.py',
         '--ignore=tests/unit/test_topology_awg_warm_native.py',
         '--ignore=tests/unit/test_awg_dualstack_native.py', '--ignore=tests/unit/test_awg_activation_native.py',
         '--ignore=tests/unit/test_validate_reality_target_native.py'],
        ['tests/unit/test_transport_runtime_acceptance_native.py'],
        ['tests/unit/test_xhttp_endpoint_contract_native.py'],
        ['tests/unit/test_awg_device_binding_native.py'],
        ['tests/unit/test_hysteria_ech_native.py'],
        ['tests/unit/test_topology_authenticated_probes_native.py', 'tests/unit/test_topology_awg_warm_native.py'],
        ['tests/unit/test_awg_dualstack_native.py', 'tests/unit/test_awg_activation_native.py'],
        ['tests/unit/test_validate_reality_target_native.py'],
        *[['tests/unit/test_transport_runtime_acceptance_native.py', '--splits', '2', '--group', str(group),
           '--splitting-algorithm', 'least_duration'] for group in (1, 2)],
    ]
    selected = []
    for arguments in commands:
        result = subprocess.run([sys.executable, '-m', 'pytest', *arguments, '--collect-only', '-q'],
            cwd=ROOT, text=True, capture_output=True, check=True, timeout=60)
        selected.append({line for line in result.stdout.splitlines()
                         if line.startswith('tests/unit/') and '::' in line})
    all_native, existing, transactions, endpoint_cases, awg_cases, ech_cases = selected[:6]
    topology_cases, dualstack_cases, reality_cases, first, second = selected[6:]
    assert transactions == first | second and not first & second
    assert all(sum('test_native_ingress_egress_commit_sigkill' in item for item in group) == 3
               for group in (first, second))
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["transport-runtime-acceptance"]
    assert workflow["strategy"]["matrix"]["group"] == [1, 2]
    assert workflow["strategy"]["fail-fast"] is False
    assert any("--splits 2 --group $PYTEST_NATIVE_GROUP --splitting-algorithm least_duration" in s.get("run", "") for s in workflow["steps"])
    assert all_native == existing | transactions | endpoint_cases | awg_cases | ech_cases | topology_cases | dualstack_cases | reality_cases
    groups = [existing, transactions, endpoint_cases, awg_cases, ech_cases, topology_cases, dualstack_cases, reality_cases]
    assert all(not left & right for index,left in enumerate(groups) for right in groups[index+1:])
    assert reality_cases and len(reality_cases) == 5
    reality_workflow = yaml.safe_load((ROOT / ".github/workflows/reality-target-validation.yml").read_text())["jobs"]["reality-target-validation"]
    assert any("make test-reality-target-validation" in s.get("run", "") for s in reality_workflow["steps"])
    assert transactions and len(transactions) == 12
    assert ('tests/unit/test_transport_runtime_acceptance_native.py::'
            'test_native_ech_admission_retains_custom_configuration_directory') in transactions
    assert awg_cases and len(ech_cases) == 13
    assert endpoint_cases and len(endpoint_cases) == 10
    assert "$(MAKE) test-probe-matrix-mtproto" in makefile.split("ci-fast:", 1)[1]
    assert "go test -mod=readonly -count=1" in makefile
    names = []
    import ast

    for path in (ROOT / "tests/unit").glob("test_*.py"):
        module = ast.parse(path.read_text())
        names.extend(
            node.name
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and any(
                ast.unparse(d) == "pytest.mark.native_runtime"
                for d in node.decorator_list
            )
        )
    assert set(names) == {
        "test_actual_terraform_render_matches_ci_scalar_document",
        "test_actual_terraform_render_refuses_null_bootstrap_scalars",
        "test_adapter_command_uses_reviewed_terraform_fd_and_snapshot",
        "test_actual_builtin_terraform_data_plan_can_be_saved_if_terraform_exists",
        "test_alertmanager_v0281_enforces_the_webhook_request_timeout",
        "test_adapter_accepts_shared_textfile_directory_and_publishes_collector_readable_output",
        "test_native_nft_conversion_preserves_listener_policy",
        "test_native_plan_approval_apply_and_bridge_free_restore",
        "test_native_console_witness_accepts_only_exact_inert_install_delta",
        "test_console_lease_real_pid1_expiry_and_private_runtime_paths",
        "test_ci_sentinel_real_loopback_sshd_pinned_key_and_owned_stop",
        "test_ci_seed_real_guest_mount_digest_binding_and_unmount",
        "test_ci_generator_real_crypto_passes_secret_schema",
        "test_absent_bundle_never_adopts_orphaned_durable_state",
        "test_absent_bundle_accepts_only_absent_or_empty_safe_state",
        "test_current_bundle_refuses_unknown_old_or_invalid_records_readonly",
        "test_complete_agent_check_mode_never_publishes_private_candidates",
        "test_retained_receiver_complete_check_mode_never_mutates_authority",
        "test_memory_only_tls_preflight_validates_actual_authority",
        "test_real_policy_daemon_idle_heartbeat_and_enabled_disabled_idempotence",
        "test_exact_realm_pin_accepts_supported_config_and_authenticated_rendezvous",
        "test_actual_fresh_disabled_caller_preserves_inactive_shared_nginx",
        "test_actual_policy_tail_reads_only_authorized_xray_group",
        "test_actual_independent_policy_role_provisions_reader_group_without_gid_drift",
        "test_sigkill_after_both_vhosts_removed_then_actual_unchanged_disable_recovers_listener",
    }


def test_make_test_unit_covers_both_suites_without_nested_make_noise(tmp_path):
    unit = tmp_path / "tests/unit"
    unit.mkdir(parents=True)
    (tmp_path / "tests/conftest.py").write_text(
        (ROOT / "tests/conftest.py").read_text()
    )
    (tmp_path / "json.mk").write_text("json:\n\t@printf '%s\\n' '{\"ok\":true}'\n")
    (unit / "test_json.py").write_text(
        "import json, subprocess\n"
        "def test_json():\n"
        "    result = subprocess.run(['make', '-f', 'json.mk'], capture_output=True, text=True, check=True)\n"
        "    assert json.loads(result.stdout) == {'ok': True}\n"
    )
    auxiliary = tmp_path / "scripts/tests"
    auxiliary.mkdir(parents=True)
    (auxiliary / "test_auxiliary.py").write_text(
        (unit / "test_json.py").read_text().replace("test_json", "test_auxiliary")
    )
    import os

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    # Simulate a recursive CI gate, including GNU Make's directory chatter.
    env.update(MAKELEVEL="2", MAKEFLAGS="w")
    result = subprocess.run(
        ["make", "-f", str(ROOT / "Makefile"), "test-unit"],
        cwd=tmp_path,
        check=False,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout, result.stdout
