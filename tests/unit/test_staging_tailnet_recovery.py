"""Staging recovery acceptance controller at its public execute seam."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/staging-tailnet-recovery.py"


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("staging_tailnet_recovery", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ForbiddenRuntime:
    def __getattr__(self, name):
        def forbidden(*_args, **_kwargs):
            pytest.fail(f"external boundary reached through {name}")
        return forbidden


def test_invalid_wrapper_refuses_before_ssh(controller, tmp_path):
    config = tmp_path / "recovery.json"
    config.write_text(json.dumps({"schema_version": 1, "bootstrap_config": "relative",
                                  "evidence": str(tmp_path / "evidence.json")}))
    config.chmod(0o600)

    with pytest.raises(controller.RecoveryError, match="recovery-inputs-refused"):
        controller.execute({
            "TAILNET_RECOVERY_CONFIG": str(config),
            "TAILNET_RECOVERY_SCENARIO": "controller-loss",
            "TAILNET_RECOVERY_TARGET": "node-one",
        }, runtime=ForbiddenRuntime())

    assert not (tmp_path / "evidence.json").exists()


class ScenarioRuntime:
    def __init__(self, scenario):
        self.scenario = scenario
        self.events = []
        self.recovery = (["expired", "rolling_back", "firewall_restored", "idle"]
                         if scenario == "controller-loss" else ["idle"])

    def prepare(self, inputs):
        self.events.append(("prepare", inputs.name))

    def recovery_baseline(self, inputs):
        self.events.append(("recovery-baseline", inputs.name))
        count = len([event for event in self.events if event[0] == "recovery-baseline"])
        return f"baseline-invocation-{count}"

    def boot_id(self, inputs):
        self.events.append(("boot-id", inputs.name))
        return "12345678-1234-4234-9234-123456789abc"

    def spawn_pending(self, inputs, auth_key):
        self.events.append(("spawn-pending", inputs.name, auth_key))
        return 42

    def kill_pending(self, child):
        self.events.append(("sigkill", child))

    def cleanup_pending(self, child):
        self.events.append(("cleanup-sigkill", child))

    def sleep(self, seconds):
        self.events.append(("sleep", seconds))

    def reboot(self, inputs):
        self.events.append(("reboot", inputs.name))

    def recovered_status(self, inputs):
        status = self.recovery.pop(0)
        self.events.append(("recovery", inputs.name, status))
        return status

    def reboot_recovery(self, inputs, previous_boot):
        self.events.append(("current-boot-units", inputs.name, previous_boot))
        return True

    def autonomous_recovery(self, inputs, baseline):
        self.events.append(("autonomous-recovery", inputs.name, baseline))
        return True

    def postconditions(self, inputs):
        self.events.append(("public-ssh-sftp-preinstall", inputs.name))

    def final_guard(self, inputs):
        self.events.append(("final-guard", inputs.name))

    def audit(self, environment, environment_name, provider, scenario, evidence):
        assert evidence.exists(), "audit must follow durable evidence publication"
        self.events.append(("audit", environment_name, provider, scenario))


class ExecuteRuntime(ScenarioRuntime):
    def __init__(self, scenario):
        super().__init__(scenario)
        self.bootstrap_output = "/private/tmp/tailnet-bootstrap-handoff.json"

    @contextmanager
    def open_inputs(self, environment, bootstrap_config, inventory_alias):
        self.events.append(("inputs", str(bootstrap_config), inventory_alias))
        number = len([event for event in self.events if event[0] == "inputs"])
        yield SimpleNamespace(
            name=f"generation-{number}",
            config={
                "environment": "ci-staging-fixture", "inventory_alias": inventory_alias,
                "provider": "upcloud", "output": self.bootstrap_output,
                "source_revision": "a" * 40, "deployable_digest": "b" * 64,
                "public_address": "192.0.2.10", "ssh_port": 2222,
                "public_sources": ["198.51.100.10"],
                "approved_sources": ["100.64.0.10", "fd7a:115c:a1e0::10"],
                "host_key_sha256": "c" * 64,
            },
        )


@pytest.mark.parametrize("scenario", ["controller-loss", "reboot"])
def test_pending_child_is_killed_then_fresh_recovery_proves_public_postconditions(
        controller, scenario):
    runtime = ScenarioRuntime(scenario)
    generations = iter([SimpleNamespace(name=f"fresh-{number}") for number in range(1, 5)])

    @contextmanager
    def fresh_inputs():
        yield next(generations)

    result = controller.run_scenario(
        scenario, SimpleNamespace(name="initial"), "tskey-auth-fixture_key",
        fresh_inputs=fresh_inputs, runtime=runtime,
    )

    assert result == {
        "schema_version": 1,
        "status": "passed",
        "scenario": scenario,
        "checks": {
            "durable_pending_killed": True,
            "idle": True,
            "public_ssh": True,
            "public_sftp": True,
            "preinstall": True,
            "boot_changed": scenario == "reboot",
            "recovery_units_current_boot": scenario == "reboot",
        },
    }
    encoded = json.dumps(result, sort_keys=True)
    assert all(value not in encoded for value in (
        "192.0.2.10", "100.64.0.1", "tskey-auth", "nonce", "capability", "state",
    ))
    assert runtime.events[0] == ("prepare", "initial")
    assert ("spawn-pending", "initial", "tskey-auth-fixture_key") in runtime.events
    assert ("sigkill", 42) in runtime.events
    assert runtime.events[-2][0] == "public-ssh-sftp-preinstall"
    assert runtime.events[-1][0] == "final-guard"
    if scenario == "controller-loss":
        assert ("autonomous-recovery", "fresh-4",
                ("baseline-invocation-1", "baseline-invocation-2")) in runtime.events
        assert [event[:2] for event in runtime.events if event[0] == "recovery-baseline"] == [
            ("recovery-baseline", "initial"), ("recovery-baseline", "initial"),
        ]


def test_execute_uses_external_scenario_and_publishes_only_redacted_evidence(
        controller, tmp_path):
    wrapper = tmp_path / "recovery.json"
    bootstrap_config = tmp_path / "bootstrap.json"
    bootstrap_config.write_text("private bootstrap fixture")
    wrapper.write_text(json.dumps({
        "schema_version": 1,
        "bootstrap_config": str(bootstrap_config),
        "evidence": str(tmp_path / "evidence.json"),
    }))
    wrapper.chmod(0o600)
    runtime = ExecuteRuntime("controller-loss")

    result = controller.execute({
        "TAILNET_RECOVERY_CONFIG": str(wrapper),
        "TAILNET_RECOVERY_SCENARIO": "controller-loss",
        "TAILNET_RECOVERY_TARGET": "node-one",
        "TAILSCALE_AUTH_KEY": "tskey-auth-fixture_key",
    }, runtime=runtime)

    evidence = tmp_path / "evidence.json"
    assert result["status"] == "passed"
    assert evidence.stat().st_mode & 0o777 == 0o600
    assert json.loads(evidence.read_text()) == result
    assert all(value not in evidence.read_text() for value in (
        "node-one", "bootstrap", "tskey-auth", "192.0.2.10", "100.64.0.1",
        "nonce", "capability", "state",
    ))
    assert len(result["input_sha256"]) == 64
    assert result["source_revision"] == "a" * 40
    assert result["deployable_digest"] == "b" * 64
    assert len(result["binding_sha256"]) == 64
    assert runtime.events[-1] == (
        "audit", "ci-staging-fixture", "upcloud", "controller-loss",
    )


def test_evidence_cannot_alias_bootstrap_output_before_destructive_action(
        controller, tmp_path):
    evidence = tmp_path / "evidence.json"
    bootstrap_config = tmp_path / "bootstrap.json"
    bootstrap_config.write_text("private bootstrap fixture")
    wrapper = tmp_path / "recovery.json"
    wrapper.write_text(json.dumps({
        "schema_version": 1, "bootstrap_config": str(bootstrap_config),
        "evidence": str(evidence),
    }))
    wrapper.chmod(0o600)
    runtime = ExecuteRuntime("controller-loss")
    runtime.bootstrap_output = str(evidence)

    with pytest.raises(controller.RecoveryError, match="recovery-evidence-collision"):
        controller.execute({
            "TAILNET_RECOVERY_CONFIG": str(wrapper),
            "TAILNET_RECOVERY_SCENARIO": "controller-loss",
            "TAILNET_RECOVERY_TARGET": "node-one",
            "TAILSCALE_AUTH_KEY": "tskey-auth-fixture_key",
        }, runtime=runtime)

    assert [event[0] for event in runtime.events] == ["inputs"]
    assert not evidence.exists()


def test_production_wrapper_refuses_before_fault_or_evidence(controller, tmp_path):
    class ProductionRuntime(ExecuteRuntime):
        @contextmanager
        def open_inputs(self, environment, bootstrap_config, inventory_alias):
            self.events.append(("inputs", str(bootstrap_config), inventory_alias))
            yield SimpleNamespace(name="production", config={
                "environment": "prod", "inventory_alias": inventory_alias,
            })

    bootstrap_config = tmp_path / "bootstrap.json"
    bootstrap_config.write_text("private bootstrap fixture")
    wrapper = tmp_path / "recovery.json"
    wrapper.write_text(json.dumps({
        "schema_version": 1, "bootstrap_config": str(bootstrap_config),
        "evidence": str(tmp_path / "evidence.json"),
    }))
    wrapper.chmod(0o600)
    runtime = ProductionRuntime("controller-loss")

    with pytest.raises(controller.RecoveryError, match="recovery-staging-only"):
        controller.execute({
            "TAILNET_RECOVERY_CONFIG": str(wrapper),
            "TAILNET_RECOVERY_SCENARIO": "controller-loss",
            "TAILNET_RECOVERY_TARGET": "node-one",
            "TAILSCALE_AUTH_KEY": "tskey-auth-fixture_key",
        }, runtime=runtime)

    assert [event[0] for event in runtime.events] == ["inputs"]
    assert not (tmp_path / "evidence.json").exists()


def test_reboot_refuses_unchanged_boot_before_public_postconditions(controller):
    runtime = ScenarioRuntime("reboot")
    runtime.reboot_recovery = lambda *_args: False

    @contextmanager
    def fresh_inputs():
        yield SimpleNamespace(name="fresh")

    with pytest.raises(controller.RecoveryError, match="recovery-current-boot-proof-failed"):
        controller.run_scenario(
            "reboot", SimpleNamespace(name="initial"), "tskey-auth-fixture_key",
            fresh_inputs=fresh_inputs, runtime=runtime,
        )

    assert not any(event[0] == "public-ssh-sftp-preinstall" for event in runtime.events)


def test_reboot_uses_bounded_first_boot_retry_after_public_ssh_goes_down(
        controller, monkeypatch):
    import bootstrap_readiness
    runtime = controller.Runtime()
    environment = {"PATH": "/usr/bin"}
    inputs = SimpleNamespace(
        ssh=["ssh", "-F", "pinned-config", "node-one"],
        environment=environment,
    )
    events = []
    replies = iter([(0, b""), (255, b"")])
    monkeypatch.setattr(runtime, "_guard", lambda *_args: None)

    def run_command(command, **kwargs):
        events.append(("command", command, kwargs["timeout"], kwargs["environment"]))
        return next(replies)

    def wait_for_bootstrap(ssh, *, environment, first_boot):
        events.append(("wait", ssh, environment, first_boot))

    monkeypatch.setattr(bootstrap_readiness, "run_command", run_command)
    monkeypatch.setattr(bootstrap_readiness, "wait_for_bootstrap", wait_for_bootstrap)

    runtime.reboot(inputs)

    assert events == [
        ("command", ["ssh", "-F", "pinned-config",
                     "sudo -n /usr/bin/systemctl reboot --no-wall"], 20, environment),
        ("command", ["ssh", "-F", "pinned-config", "true"], 5, environment),
        ("wait", ["ssh", "-F", "pinned-config"], environment, True),
    ]


def test_controller_loss_refuses_stale_recovery_invocation(controller):
    runtime = ScenarioRuntime("controller-loss")
    runtime.recovery = ["idle"]
    runtime.autonomous_recovery = lambda *_args: False

    @contextmanager
    def fresh_inputs():
        yield SimpleNamespace(name="fresh")

    with pytest.raises(controller.RecoveryError, match="recovery-autonomous-proof-failed"):
        controller.run_scenario(
            "controller-loss", SimpleNamespace(name="initial"), "tskey-auth-fixture_key",
            fresh_inputs=fresh_inputs, runtime=runtime,
        )

    assert not any(event[0] == "public-ssh-sftp-preinstall" for event in runtime.events)


@pytest.mark.parametrize("error_factory", [
    lambda controller: __import__("bootstrap_readiness").ReadinessError(
        "SSH session timeout"),
    lambda controller: controller.bootstrap.BootstrapError("bootstrap-remote-refused"),
])
def test_reboot_retries_transient_readiness_errors_before_recovery(
        controller, error_factory):
    class TransientStatusRuntime(ScenarioRuntime):
        def __init__(self):
            super().__init__("reboot")
            self.status_attempts = 0

        def recovered_status(self, inputs):
            self.status_attempts += 1
            self.events.append(("recovery", inputs.name, self.status_attempts))
            if self.status_attempts == 1:
                raise error_factory(controller)
            return "idle"

    runtime = TransientStatusRuntime()
    generations = iter([SimpleNamespace(name="first"), SimpleNamespace(name="second")])

    @contextmanager
    def fresh_inputs():
        yield next(generations)

    result = controller.run_scenario(
        "reboot", SimpleNamespace(name="initial"), "tskey-auth-fixture_key",
        fresh_inputs=fresh_inputs, runtime=runtime,
    )

    assert result["status"] == "passed"
    assert runtime.status_attempts == 2
    assert [event for event in runtime.events if event[0] == "sleep"] == [
        ("sleep", controller.RECOVERY_POLL_SECONDS),
    ]
    assert ("public-ssh-sftp-preinstall", "second") in runtime.events


def test_controller_loss_retries_transient_public_postconditions(controller):
    class TransientPostconditionsRuntime(ScenarioRuntime):
        def __init__(self):
            super().__init__("controller-loss")
            self.postcondition_attempts = 0

        def postconditions(self, inputs):
            self.postcondition_attempts += 1
            self.events.append(("public-ssh-sftp-preinstall", inputs.name))
            if self.postcondition_attempts == 1:
                raise controller.bootstrap.BootstrapError("bootstrap-remote-refused")

    runtime = TransientPostconditionsRuntime()
    runtime.recovery = ["idle", "idle"]
    generations = iter([SimpleNamespace(name="first"), SimpleNamespace(name="second")])

    @contextmanager
    def fresh_inputs():
        yield next(generations)

    result = controller.run_scenario(
        "controller-loss", SimpleNamespace(name="initial"), "tskey-auth-fixture_key",
        fresh_inputs=fresh_inputs, runtime=runtime,
    )

    assert result["status"] == "passed"
    assert runtime.postcondition_attempts == 2
    assert [event for event in runtime.events if event[0] == "sleep"][-1] == (
        "sleep", controller.RECOVERY_POLL_SECONDS,
    )
    assert [event for event in runtime.events if event[0] == "final-guard"] == [
        ("final-guard", "second"),
    ]


@pytest.mark.parametrize("error_factory", [
    lambda controller: __import__("bootstrap_readiness").ReadinessError(
        "bootstrap SSH transport failure"),
    lambda controller: controller.bootstrap.BootstrapError("bootstrap-remote-refused"),
])
def test_reboot_bounds_transient_readiness_retries(controller, error_factory):
    class UnavailableStatusRuntime(ScenarioRuntime):
        def __init__(self):
            super().__init__("reboot")
            self.status_attempts = 0

        def recovered_status(self, inputs):
            self.status_attempts += 1
            raise error_factory(controller)

    runtime = UnavailableStatusRuntime()
    generations = iter(SimpleNamespace(name=f"attempt-{number}")
                       for number in range(controller.RECOVERY_ATTEMPTS))

    @contextmanager
    def fresh_inputs():
        yield next(generations)

    with pytest.raises(controller.RecoveryError, match="recovery-postconditions-timeout"):
        controller.run_scenario(
            "reboot", SimpleNamespace(name="initial"), "tskey-auth-fixture_key",
            fresh_inputs=fresh_inputs, runtime=runtime,
        )

    assert runtime.status_attempts == controller.RECOVERY_ATTEMPTS
    assert [event for event in runtime.events if event[0] == "sleep"] == [
        ("sleep", controller.RECOVERY_POLL_SECONDS),
    ] * (controller.RECOVERY_ATTEMPTS - 1)


def test_reboot_does_not_retry_semantic_recovery_error(controller):
    class RefusingStatusRuntime(ScenarioRuntime):
        def __init__(self):
            super().__init__("reboot")
            self.status_attempts = 0

        def recovered_status(self, inputs):
            self.status_attempts += 1
            raise controller.RecoveryError("recovery-status-refused")

    runtime = RefusingStatusRuntime()
    opened = []

    @contextmanager
    def fresh_inputs():
        opened.append("attempt")
        yield SimpleNamespace(name="first")

    with pytest.raises(controller.RecoveryError, match="recovery-status-refused"):
        controller.run_scenario(
            "reboot", SimpleNamespace(name="initial"), "tskey-auth-fixture_key",
            fresh_inputs=fresh_inputs, runtime=runtime,
        )

    assert runtime.status_attempts == 1
    assert opened == ["attempt"]
    assert not any(event[0] == "sleep" for event in runtime.events)


@pytest.mark.parametrize("reason", [
    "cloud-init error",
    "bootstrap marker missing",
    "cloud-init status unavailable",
])
def test_reboot_does_not_retry_semantic_readiness_error(controller, reason):
    class RefusingStatusRuntime(ScenarioRuntime):
        def __init__(self):
            super().__init__("reboot")
            self.status_attempts = 0

        def recovered_status(self, inputs):
            self.status_attempts += 1
            raise __import__("bootstrap_readiness").ReadinessError(reason)

    runtime = RefusingStatusRuntime()

    @contextmanager
    def fresh_inputs():
        yield SimpleNamespace(name="first")

    with pytest.raises(__import__("bootstrap_readiness").ReadinessError, match=reason):
        controller.run_scenario(
            "reboot", SimpleNamespace(name="initial"), "tskey-auth-fixture_key",
            fresh_inputs=fresh_inputs, runtime=runtime,
        )

    assert runtime.status_attempts == 1
    assert not any(event[0] == "sleep" for event in runtime.events)


def test_reboot_accepts_only_changed_boot_with_both_current_boot_units(controller, monkeypatch):
    runtime = controller.Runtime()
    monkeypatch.setattr(runtime, "_guard", lambda *_args: None)
    previous = "12345678-1234-4234-9234-123456789abc"
    current = "87654321-4321-4321-9234-cba987654321"
    unit = {"InvocationID": "d" * 32, "Result": "success", "ExecMainCode": "1", "ExecMainStatus": "0",
            "ExecMainStartTimestampMonotonic": "1523"}
    unit_reply = {"units": {
        "vpn-tailnet-firewall-recover.service": dict(unit),
        "vpn-tailnet-recover.service": dict(unit),
    }}
    replies = iter([{"boot_id": current}, unit_reply])
    monkeypatch.setattr(controller.bootstrap, "_remote", lambda *_args, **_kwargs: next(replies))

    assert runtime.reboot_recovery(SimpleNamespace(host={}), previous) is True
    assert all("ExecMainStartTimestampMonotonic" in fields for fields in unit_reply["units"].values())
    replies = iter([{"boot_id": previous}, unit_reply])
    monkeypatch.setattr(controller.bootstrap, "_remote", lambda *_args, **_kwargs: next(replies))
    assert runtime.reboot_recovery(SimpleNamespace(host={}), previous) is False


@pytest.mark.parametrize("status", ["expired", "rolling_back", "firewall_restored"])
def test_recovered_status_polls_transitions_without_running_recovery(
        controller, monkeypatch, status):
    import bootstrap_readiness
    runtime = controller.Runtime()
    inputs = SimpleNamespace(ssh=["ssh", "host"], environment={}, host={})
    monkeypatch.setattr(runtime, "_guard", lambda *_args: None)
    monkeypatch.setattr(bootstrap_readiness, "wait_for_bootstrap", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(controller.deploy, "require_recovery_foundation", lambda *_args: None)
    monkeypatch.setattr(controller.bootstrap, "_installed", lambda *_args: "ready")
    monkeypatch.setattr(controller.bootstrap, "_binding", lambda *_args: {})
    monkeypatch.setattr(controller.bootstrap, "_rpc", lambda *_args, **_kwargs: {"status": status})
    monkeypatch.setattr(controller.bootstrap, "_remote",
                        lambda *_args, **_kwargs: pytest.fail("controller ran guest recovery"))

    assert runtime.recovered_status(inputs) == status


def test_spawn_cancellation_kills_and_reaps_blocked_child(controller, monkeypatch):
    runtime = controller.Runtime()
    closed = []
    killed = []
    waited = []
    pipes = iter([(10, 11), (12, 13)])
    monkeypatch.setattr(controller.os, "pipe", lambda: next(pipes))
    monkeypatch.setattr(controller.os, "fork", lambda: 321)
    monkeypatch.setattr(controller.os, "close", lambda fd: closed.append(fd))
    monkeypatch.setattr(controller.select, "select", lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(controller.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(controller.os, "waitpid", lambda pid, flags: waited.append((pid, flags)) or (pid, 9))

    with pytest.raises(KeyboardInterrupt):
        runtime.spawn_pending(SimpleNamespace(), "tskey-auth-fixture_key")

    assert killed == [(321, controller.signal.SIGKILL)]
    assert waited == [(321, 0)]
    assert sorted(closed) == [10, 11, 12, 13]


def test_spawn_select_poll_observes_recorded_signal_and_reaps_child(controller, monkeypatch):
    import bootstrap_readiness
    runtime = controller.Runtime()
    delays = []
    killed = []
    waited = []
    monkeypatch.setattr(bootstrap_readiness, "_cancelled", 0)
    pipes = iter([(10, 11), (12, 13)])
    monkeypatch.setattr(controller.os, "pipe", lambda: next(pipes))
    monkeypatch.setattr(controller.os, "fork", lambda: 321)
    monkeypatch.setattr(controller.os, "close", lambda _fd: None)

    def interrupted_select(_read, _write, _error, delay):
        delays.append(delay)
        bootstrap_readiness._cancelled = controller.signal.SIGTERM
        return [], [], []

    monkeypatch.setattr(controller.select, "select", interrupted_select)
    monkeypatch.setattr(controller.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(controller.os, "waitpid", lambda pid, flags: waited.append((pid, flags)) or (pid, 9))

    with pytest.raises(SystemExit, match=str(128 + controller.signal.SIGTERM)):
        runtime.spawn_pending(SimpleNamespace(), "tskey-auth-fixture_key")

    assert len(delays) == 1 and 0 < delays[0] <= 0.25
    assert killed == [(321, controller.signal.SIGKILL)]
    assert waited == [(321, 0)]


def test_normal_pending_marker_keeps_parent_control_until_verified_sigkill(
        controller, monkeypatch):
    runtime = controller.Runtime()
    pipes = iter([(10, 11), (12, 13)])
    closed = []
    killed = []
    waited = []
    monkeypatch.setattr(controller.os, "pipe", lambda: next(pipes))
    monkeypatch.setattr(controller.os, "fork", lambda: 321)
    monkeypatch.setattr(controller.os, "close", lambda fd: closed.append(fd))
    monkeypatch.setattr(controller.select, "select", lambda *_args: ([10], [], []))
    monkeypatch.setattr(controller.os, "read", lambda fd, limit: b"P")
    monkeypatch.setattr(controller.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(controller.os, "waitpid",
                        lambda pid, flags: waited.append((pid, flags)) or (pid, 9))
    monkeypatch.setattr(controller.os, "WIFSIGNALED", lambda status: status == 9)
    monkeypatch.setattr(controller.os, "WTERMSIG", lambda status: controller.signal.SIGKILL)

    child = runtime.spawn_pending(SimpleNamespace(), "tskey-auth-fixture_key")

    assert child == 321
    assert runtime._control_fds == {321: 13}
    assert sorted(closed) == [10, 11, 12]
    runtime.kill_pending(child)
    assert killed == [(321, controller.signal.SIGKILL)]
    assert waited == [(321, 0)]
    assert runtime._control_fds == {}
    assert sorted(closed) == [10, 11, 12, 13]


def test_cleanup_closes_parent_control_before_reap_when_sigkill_is_unavailable(
        controller, monkeypatch):
    runtime = controller.Runtime()
    runtime._control_fds[321] = 13
    events = []
    monkeypatch.setattr(controller.os, "kill",
                        lambda *_args: (_ for _ in ()).throw(InterruptedError()))
    monkeypatch.setattr(controller.os, "close", lambda fd: events.append(("close", fd)))

    def reap(pid, flags):
        assert events == [("close", 13)]
        events.append(("reap", pid, flags))
        return pid, 0

    monkeypatch.setattr(controller.os, "waitpid", reap)

    runtime.cleanup_pending(321)

    assert events == [("close", 13), ("reap", 321, 0)]
    assert runtime._control_fds == {}


def test_pending_barrier_exits_before_marker_when_parent_is_already_gone(
        controller, monkeypatch):
    class ChildExit(Exception):
        """Sentinel replacing os._exit inside the unit-test process."""

    polls = []
    exits = []
    monkeypatch.setattr(
        controller.select, "select",
        lambda read, write, error, delay: polls.append((read, delay)) or ([77], [], []),
    )
    monkeypatch.setattr(controller.os, "read", lambda fd, limit: b"")
    monkeypatch.setattr(
        controller.os, "write",
        lambda *_args: pytest.fail("dead parent must be detected before marker publication"),
    )

    def child_exit(code):
        exits.append(code)
        raise ChildExit

    monkeypatch.setattr(controller.os, "_exit", child_exit)

    with pytest.raises(ChildExit):
        controller.Runtime._pending_barrier(55, 77)

    assert polls == [([77], 0)]
    assert exits == [73]


def test_pending_barrier_treats_broken_marker_pipe_as_parent_loss(
        controller, monkeypatch):
    class ChildExit(Exception):
        """Sentinel replacing os._exit inside the unit-test process."""

    exits = []
    monkeypatch.setattr(controller.select, "select", lambda *_args: ([], [], []))
    monkeypatch.setattr(
        controller.os, "write",
        lambda *_args: (_ for _ in ()).throw(BrokenPipeError()),
    )

    def child_exit(code):
        exits.append(code)
        raise ChildExit

    monkeypatch.setattr(controller.os, "_exit", child_exit)

    with pytest.raises(ChildExit):
        controller.Runtime._pending_barrier(55, 77)

    assert exits == [73]


def test_pending_barrier_exits_on_parent_control_pipe_eof(controller, monkeypatch):
    class ChildExit(Exception):
        """Sentinel replacing os._exit inside the unit-test process."""

    writes = []
    polls = []
    exits = []
    replies = iter([([], [], []), ([77], [], [])])
    monkeypatch.setattr(controller.os, "write", lambda fd, data: writes.append((fd, data)) or len(data))
    monkeypatch.setattr(controller.select, "select",
                        lambda read, write, error, delay: polls.append((read, delay)) or next(replies))
    monkeypatch.setattr(controller.os, "read", lambda fd, limit: b"")

    def child_exit(code):
        exits.append(code)
        raise ChildExit

    monkeypatch.setattr(controller.os, "_exit", child_exit)

    with pytest.raises(ChildExit):
        controller.Runtime._pending_barrier(55, 77)

    assert writes == [(55, b"P")]
    assert polls == [([77], 0), ([77], 0.2)]
    assert exits == [73]


def test_audit_uses_canonical_redacted_best_effort_record(controller, monkeypatch, tmp_path):
    import bootstrap_readiness
    observed = []
    monkeypatch.setattr(bootstrap_readiness, "run_command",
                        lambda command, **kwargs: observed.append((command, kwargs)) or (0, b""))
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}")

    controller.Runtime().audit({
        "PATH": "/usr/bin", "HOME": str(tmp_path),
        "TAILSCALE_AUTH_KEY": "tskey-auth-secret", "PRIVATE_ADDRESS": "192.0.2.10",
    }, "ci-staging-fixture", "upcloud", "reboot", evidence)

    assert observed[0][0] == [
        str(ROOT / "scripts/audit-log.sh"), "append-best-effort",
        "--action", "staging-tailnet-recovery", "--env", "ci-staging-fixture",
        "--provider", "upcloud", "--note", "scenario=reboot result=passed",
    ]
    assert observed[0][1]["cwd"] == ROOT
    assert observed[0][1]["timeout"] == 30
    assert observed[0][1]["defer_cancellation"] is True
    assert set(observed[0][1]["environment"]) == {"PATH", "HOME"}
    encoded = json.dumps(observed, default=str)
    assert "tskey-auth-secret" not in encoded and "192.0.2.10" not in encoded


def test_audit_propagates_cancellation_only_after_append_finishes(
        controller, monkeypatch, tmp_path):
    import bootstrap_readiness
    events = []

    def append_audit(_command, **kwargs):
        events.append(("append-finished", kwargs["defer_cancellation"]))
        return 0, b""

    def propagate_cancellation():
        events.append(("cancellation-propagated",))
        raise SystemExit(143)

    monkeypatch.setattr(bootstrap_readiness, "run_command", append_audit)
    monkeypatch.setattr(bootstrap_readiness, "check_cancelled", propagate_cancellation)
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}")

    with pytest.raises(SystemExit, match="143"):
        controller.Runtime().audit(
            {"PATH": "/usr/bin", "HOME": str(tmp_path)},
            "ci-staging-fixture", "upcloud", "controller-loss", evidence,
        )

    assert events == [
        ("append-finished", True),
        ("cancellation-propagated",),
    ]


def test_cancellation_after_spawn_still_kills_blocked_child(controller):
    runtime = ScenarioRuntime("controller-loss")
    runtime.kill_pending = lambda _child: (_ for _ in ()).throw(KeyboardInterrupt())

    @contextmanager
    def fresh_inputs():
        pytest.fail("recovery must not begin after cancellation")
        yield

    with pytest.raises(KeyboardInterrupt):
        controller.run_scenario(
            "controller-loss", SimpleNamespace(name="initial"), "tskey-auth-fixture_key",
            fresh_inputs=fresh_inputs, runtime=runtime,
        )

    assert ("cleanup-sigkill", 42) in runtime.events


def test_lease_wait_observes_cancellation_between_short_sleeps(controller, monkeypatch):
    import bootstrap_readiness
    runtime = controller.Runtime()
    delays = []
    monkeypatch.setattr(bootstrap_readiness, "_cancelled", 0)

    def interrupt(delay):
        delays.append(delay)
        bootstrap_readiness._cancelled = controller.signal.SIGTERM

    monkeypatch.setattr(controller.time, "sleep", interrupt)

    with pytest.raises(SystemExit, match=str(128 + controller.signal.SIGTERM)):
        runtime.sleep(controller.tailnet.LEASE_SECONDS + 1)

    assert len(delays) == 1
    assert 0 < delays[0] <= 0.25


def test_bootstrap_pending_notification_precedes_external_proofs(controller, monkeypatch):
    import bootstrap_readiness

    config = {
        "inventory_alias": "node-one", "public_address": "192.0.2.10", "ssh_port": 2222,
        "public_sources": ["198.51.100.10"],
        "approved_sources": ["100.64.0.10", "fd7a:115c:a1e0::10"],
        "host_key_sha256": "a" * 64, "source_revision": "b" * 40,
        "deployable_digest": "c" * 64, "environment": "prod", "cleanup_manifest": None,
    }
    inputs = SimpleNamespace(
        config=config, host={"name": "node-one"}, ssh=["ssh", "host"], environment={},
        fences=[], output_parent_identity=(1, 2),
    )
    binding = controller.bootstrap._binding(inputs)
    nonce = "d" * 32
    pending = {
        "status": "pending", "changed": True, "nonce": nonce,
        "generation": controller.tailnet.RECOVERY_GENERATION,
        "binding_sha256": __import__("hashlib").sha256(
            controller.tailnet._canonical_bytes(binding)).hexdigest(),
        "lease": {"boot_id": "12345678-1234-4234-9234-123456789abc",
                  "started_ms": 1, "deadline_ms": 300001},
        "node": {"id": "node-id", "hostname": "vpn-enroll-" + nonce,
                 "ipv4": "100.64.1.9", "ipv6": "fd7a:115c:a1e0::9"},
    }
    events = []
    monkeypatch.setattr(bootstrap_readiness, "wait_for_bootstrap", lambda *_a, **_kw: None)
    monkeypatch.setattr(controller.bootstrap.deploy, "require_recovery_foundation",
                        lambda *_a, **_kw: None)
    monkeypatch.setattr(controller.bootstrap.deploy, "source_identity", lambda *_a, **_kw: {
        "DEPLOY_SOURCE_REVISION": "b" * 40, "DEPLOYABLE_SOURCE_DIGEST": "c" * 64,
    })
    monkeypatch.setattr(controller.bootstrap, "_installed", lambda *_a: "ready")
    monkeypatch.setattr(controller.bootstrap, "_probe", lambda *_a, **_kw: {})
    actions = iter([{"status": "idle"}, pending,
                    {**pending, "status": "configured", "changed": False}])
    monkeypatch.setattr(controller.bootstrap, "_rpc", lambda *_a, **_kw: next(actions))
    monkeypatch.setattr(controller.bootstrap, "_proofs",
                        lambda *_a: events.append("proofs") or [])
    monkeypatch.setattr(controller.bootstrap, "_publish", lambda *_a: None)

    result = controller.bootstrap.run(
        inputs, "tskey-auth-fixture_key", pending_hook=lambda: events.append("pending"),
    )

    assert result["status"] == "configured"
    assert events == ["pending", "proofs"]
