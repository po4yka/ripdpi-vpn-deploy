"""Execute skip-policy regressions and guard mandatory native/Go lane wiring."""

from pathlib import Path
import shlex
import subprocess
import sys

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
    setup = yaml.safe_load(
        (ROOT / ".github/actions/setup-disposable-ci/action.yml").read_text()
    )
    terraform = next(
        s for s in setup["runs"]["steps"] if "setup-terraform@" in s.get("uses", "")
    )
    assert terraform["with"]["terraform_wrapper"] is False
    ech_step = next(step["run"] for step in native if "make test-hysteria-ech-runtime" in step.get("run", ""))
    assert "PATH=$PATH" in shlex.split(ech_step.replace("\\\n", ""))
    command = shlex.split(native[-1]["run"].replace("\\\n", ""))
    assert command[:2] == ["sudo", "env"]
    assert command[-5:] == ["make", "test-native-runtime", "test-xhttp-delivery-matrix", "test-awg-device-binding-runtime", "test-awg-dualstack-runtime"]
    environment = {}
    for assignment in command[2:-5]:
        name, value = assignment.split("=", 1)
        assert name not in environment, f"duplicate native environment override: {name}"
        environment[name] = value
    assert environment["PATH"] == (
        "$GITHUB_WORKSPACE/.cache/native-transport-semantics/bin:$PATH"
    )
    assert environment["ALERTMANAGER_BIN"] == (
        "$RUNNER_TEMP/alertmanager-0.28.1.linux-amd64/alertmanager"
    )
    assert environment["NAIVE_NATIVE_BINARY"] == (
        "$GITHUB_WORKSPACE/.cache/p2-native-caddy/caddy"
    )
    pins = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    for variable, source, pin in (
        ("AWG_NATIVE_GO_SOURCE", "amneziawg-go", "amneziawg_go_commit"),
        ("AWG_NATIVE_TOOLS_SOURCE", "amneziawg-tools", "amneziawg_tools_commit"),
    ):
        assert environment[variable] == (
            f"$GITHUB_WORKSPACE/.cache/native-transport-semantics/{source}-{pins[pin]}"
        )


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
         '--ignore=tests/unit/test_validate_reality_target_native.py'],
        ['tests/unit/test_transport_runtime_acceptance_native.py'],
        ['tests/unit/test_xhttp_endpoint_contract_native.py'],
        ['tests/unit/test_awg_device_binding_native.py'],
        ['tests/unit/test_hysteria_ech_native.py'],
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
    all_native, existing, transactions, endpoint_cases, awg_cases, ech_cases, reality_cases = selected[:7]
    first, second = selected[7:]
    assert transactions == first | second and not first & second
    assert all(sum('test_native_ingress_egress_commit_sigkill' in item for item in group) == 3
               for group in (first, second))
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["transport-runtime-acceptance"]
    assert workflow["strategy"]["matrix"]["group"] == [1, 2]
    assert workflow["strategy"]["fail-fast"] is False
    assert any("--splits 2 --group $PYTEST_NATIVE_GROUP --splitting-algorithm least_duration" in s.get("run", "") for s in workflow["steps"])
    assert all_native == existing | transactions | endpoint_cases | awg_cases | ech_cases | reality_cases
    groups = [existing, transactions, endpoint_cases, awg_cases, ech_cases, reality_cases]
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
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout, result.stdout
