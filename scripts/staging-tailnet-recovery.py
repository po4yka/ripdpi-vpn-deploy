#!/usr/bin/env python3
"""Exercise destructive Tailnet recovery only on an owned disposable node."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import select
import signal
import stat
import tempfile
import time
from contextlib import contextmanager
from typing import NamedTuple
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
CONFIG_FIELDS = {"schema_version", "bootstrap_config", "evidence"}
SCENARIOS = {"controller-loss", "reboot"}


def _module(name: str):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), ROOT / "scripts" / f"{name}.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


bootstrap = _module("bootstrap-tailnet")
deploy = bootstrap.deploy
tailnet = bootstrap.tailnet

RECOVERY_POLL_SECONDS = 5
RECOVERY_ATTEMPTS = 12
PENDING_TIMEOUT_SECONDS = 960


class RecoveryError(ValueError):
    """Categorical refusal; never include private inputs in diagnostics."""


class Wrapper(NamedTuple):
    scenario: str
    inventory_alias: str
    bootstrap_config: Path
    evidence: Path
    fence: object
    parent_identity: tuple[int, int]
    input_sha256: str


class Runtime:
    """Real process, clock and pinned-SSH boundaries for staging acceptance."""

    def __init__(self):
        self._control_fds = {}

    @staticmethod
    def _guard(inputs):
        bootstrap._verify_inputs(inputs)
        bootstrap._require_source(inputs)

    @contextmanager
    def open_inputs(self, environment, bootstrap_config, inventory_alias):
        with tempfile.TemporaryDirectory(prefix="vpn-tailnet-recovery-") as temporary:
            child_environment = dict(environment)
            child_environment["TAILNET_BOOTSTRAP_CONFIG"] = str(bootstrap_config)
            child_environment["BOOTSTRAP_TARGET"] = inventory_alias
            yield bootstrap.load_inputs(child_environment, Path(temporary).resolve())

    def boot_id(self, inputs):
        self._guard(inputs)
        result = bootstrap._remote(
            inputs, inputs.host, "sudo -n /usr/bin/python3 -I -B -S -",
            b"import json,pathlib\nprint(json.dumps({'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))\n",
        )
        try:
            if set(result) != {"boot_id"} or str(UUID(result["boot_id"])) != result["boot_id"]:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise RecoveryError("recovery-boot-proof-failed") from None
        return result["boot_id"]

    def prepare(self, inputs):
        """Install recovery through bootstrap helpers without starting enrollment."""
        from bootstrap_readiness import wait_for_bootstrap
        from sshd_bundle_source import bundle_manifest
        self._guard(inputs)
        wait_for_bootstrap(inputs.ssh[:-1], environment=inputs.environment)
        generation, _manifest = bundle_manifest()
        deploy.require_recovery_foundation(inputs.ssh, generation, inputs.environment)
        installed = bootstrap._installed(inputs)
        if installed not in {"absent", "ready"}:
            raise RecoveryError("recovery-installation-refused")
        if installed == "absent":
            bootstrap._probe(inputs, inputs.host, preinstall=True)
            self._guard(inputs)
            bootstrap._install(inputs)
        self._guard(inputs)
        deploy.require_recovery_foundation(inputs.ssh, generation, inputs.environment)
        if bootstrap._rpc(inputs, "status", binding=bootstrap._binding(inputs)) != {"status": "idle"}:
            raise RecoveryError("recovery-initial-state-refused")

    def _unit_status(self, inputs, units):
        request = json.dumps(units).encode()
        script = b'''import json,subprocess
requested=json.loads(''' + repr(request).encode() + b''')
fields={'InvocationID','Result','ExecMainCode','ExecMainStatus','ExecMainStartTimestampMonotonic'}
units={}
for unit in requested:
 result=subprocess.run(['/usr/bin/systemctl','show',unit,'--property='+','.join(sorted(fields)),'--no-pager'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True)
 values={}
 for line in result.stdout.decode().splitlines():
  key,separator,value=line.partition('=')
  assert separator and key not in values
  values[key]=value
 assert set(values)==fields
 units[unit]=values
print(json.dumps({'units':units},sort_keys=True))
'''
        value = bootstrap._remote(
            inputs, inputs.host, "sudo -n /usr/bin/python3 -I -B -S -", script,
        )
        try:
            if set(value) != {"units"} or set(value["units"]) != set(units):
                raise ValueError
            result = {}
            expected = {"Result": "success", "ExecMainCode": "1", "ExecMainStatus": "0"}
            for unit, fields in value["units"].items():
                if not isinstance(fields, dict):
                    raise ValueError
                invocation = fields.get("InvocationID")
                started = fields.get("ExecMainStartTimestampMonotonic")
                observed = {key: fields.get(key) for key in expected}
                if (set(fields) != {*expected, "InvocationID", "ExecMainStartTimestampMonotonic"}
                        or not isinstance(invocation, str)
                        or re.fullmatch(r"[0-9a-f]{32}", invocation) is None
                        or observed != expected or not isinstance(started, str)
                        or not started.isdigit() or int(started) <= 0):
                    raise ValueError
                result[unit] = hashlib.sha256(invocation.encode()).hexdigest()
            return result
        except (KeyError, TypeError, ValueError, AttributeError):
            raise RecoveryError("recovery-service-proof-failed") from None

    def recovery_baseline(self, inputs):
        self._guard(inputs)
        return self._unit_status(inputs, ["vpn-tailnet-recover.service"])[
            "vpn-tailnet-recover.service"
        ]

    def autonomous_recovery(self, inputs, baseline):
        self._guard(inputs)
        current = self._unit_status(inputs, ["vpn-tailnet-recover.service"])[
            "vpn-tailnet-recover.service"
        ]
        return current not in baseline

    @staticmethod
    def _pending_barrier(marker_fd, control_fd):
        """Publish pending once, then die if the owning parent disappears."""
        if os.write(marker_fd, b"P") != 1:
            os._exit(74)
        while True:
            readable, _, _ = select.select([control_fd], [], [], 0.2)
            if readable:
                # The parent never writes. EOF proves every parent copy of the
                # write end closed, including an unhandled crash on macOS.
                if os.read(control_fd, 1) == b"":
                    os._exit(73)
                os._exit(74)

    def spawn_pending(self, inputs, auth_key):
        read_fd, write_fd = os.pipe()
        control_read_fd, control_write_fd = os.pipe()
        try:
            pid = os.fork()
        except OSError:
            for descriptor in (read_fd, write_fd, control_read_fd, control_write_fd):
                os.close(descriptor)
            raise
        if pid == 0:
            os.close(read_fd)
            os.close(control_write_fd)
            try:
                bootstrap.run(
                    inputs, auth_key,
                    pending_hook=lambda: self._pending_barrier(write_fd, control_read_fd),
                )
            except (Exception, KeyboardInterrupt, SystemExit):
                # Child diagnostics are intentionally categorical and private.
                os._exit(71)
            os._exit(72)  # Acceptance must kill the child before confirmation.
        os.close(write_fd)
        os.close(control_read_fd)
        self._control_fds[pid] = control_write_fd
        try:
            from bootstrap_readiness import check_cancelled
            deadline = time.monotonic() + PENDING_TIMEOUT_SECONDS
            marker = None
            while marker is None:
                check_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RecoveryError("recovery-pending-not-reached")
                readable, _, _ = select.select([read_fd], [], [], min(0.2, remaining))
                check_cancelled()
                if readable:
                    marker = os.read(read_fd, 2)
            if marker != b"P":
                raise RecoveryError("recovery-pending-not-reached")
            return pid
        except (Exception, KeyboardInterrupt, SystemExit):
            self.cleanup_pending(pid)
            raise
        finally:
            os.close(read_fd)

    def _close_control(self, child):
        descriptor = self._control_fds.pop(child, None)
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                # Cleanup remains best effort after the child has terminated.
                return

    def kill_pending(self, child):
        try:
            os.kill(child, signal.SIGKILL)
            _pid, status = os.waitpid(child, 0)
        except (ChildProcessError, OSError):
            raise RecoveryError("recovery-controller-loss-unproven") from None
        finally:
            self._close_control(child)
        if not os.WIFSIGNALED(status) or os.WTERMSIG(status) != signal.SIGKILL:
            raise RecoveryError("recovery-controller-loss-unproven")

    def cleanup_pending(self, child):
        """Best-effort cancellation cleanup; never claim this as death proof."""
        try:
            os.kill(child, signal.SIGKILL)
        except OSError:
            # A dead child still needs a best-effort reap below.
            kill_was_already_unavailable = True
        else:
            kill_was_already_unavailable = False
        # Closing the ownership pipe is a second termination path if SIGKILL
        # itself was interrupted: the blocked child observes EOF and exits.
        self._close_control(child)
        try:
            os.waitpid(child, 0)
        except (ChildProcessError, OSError):
            # It may already have been reaped by the verified kill path.
            reap_was_already_complete = True
        else:
            reap_was_already_complete = False
        # Named outcomes keep this intentionally lossy cleanup visible to
        # static analysis without changing the original exception path.
        _cleanup_outcome = (kill_was_already_unavailable, reap_was_already_complete)

    def sleep(self, seconds):
        from bootstrap_readiness import check_cancelled
        deadline = time.monotonic() + seconds
        while True:
            check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.2, remaining))

    def reboot(self, inputs):
        from bootstrap_readiness import ReadinessError, run_command, wait_for_bootstrap
        self._guard(inputs)
        command = [*inputs.ssh[:-1], "sudo -n /usr/bin/systemctl reboot --no-wall"]
        try:
            status, _ = run_command(command, timeout=20, environment=inputs.environment)
        except ReadinessError:
            status = 255
        if status not in {0, 255}:
            raise RecoveryError("recovery-reboot-refused")
        # A successful command is not reboot evidence. Observe the pinned public
        # endpoint go away before accepting readiness in the next boot.
        down = False
        for _attempt in range(12):
            try:
                probe_status, _ = run_command(
                    [*inputs.ssh[:-1], "true"], timeout=5, environment=inputs.environment,
                )
            except ReadinessError:
                probe_status = 255
            if probe_status:
                down = True
                break
            self.sleep(2)
        if not down:
            raise RecoveryError("recovery-reboot-unobserved")
        wait_for_bootstrap(inputs.ssh[:-1], environment=inputs.environment)

    def recovered_status(self, inputs):
        from bootstrap_readiness import wait_for_bootstrap
        from sshd_bundle_source import bundle_manifest
        self._guard(inputs)
        wait_for_bootstrap(inputs.ssh[:-1], environment=inputs.environment)
        generation, _manifest = bundle_manifest()
        deploy.require_recovery_foundation(inputs.ssh, generation, inputs.environment)
        if bootstrap._installed(inputs) != "ready":
            raise RecoveryError("recovery-installation-missing")
        result = bootstrap._rpc(inputs, "status", binding=bootstrap._binding(inputs))
        if result == {"status": "idle"}:
            return "idle"
        if isinstance(result, dict) and result.get("status") == "pending":
            bootstrap._capability(inputs, result)
            return "pending"
        if result in ({"status": "expired"}, {"status": "rolling_back"},
                      {"status": "firewall_restored"}):
            return result["status"]
        raise RecoveryError("recovery-status-refused")

    def reboot_recovery(self, inputs, previous_boot):
        self._guard(inputs)
        try:
            boot_id = self.boot_id(inputs)
            self._unit_status(inputs, [
                "vpn-tailnet-firewall-recover.service", "vpn-tailnet-recover.service",
            ])
            return boot_id != previous_boot
        except RecoveryError:
            return False

    def postconditions(self, inputs):
        self._guard(inputs)
        result = bootstrap._rpc(inputs, "status", binding=bootstrap._binding(inputs))
        if result != {"status": "idle"}:
            raise RecoveryError("recovery-idle-unproven")
        bootstrap._probe(inputs, inputs.host, preinstall=True)
        bootstrap._sftp(inputs, inputs.host)

    def final_guard(self, inputs):
        self._guard(inputs)

    def audit(self, environment, environment_name, provider, scenario, evidence):
        """Append one categorical best-effort record after evidence is durable."""
        import sys
        from bootstrap_readiness import ReadinessError, run_command
        audit_environment = {
            key: environment[key]
            for key in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE",
                        "AGE_KEY", "AUDIT_LOG_FILE", "AUDIT_ACTOR")
            if key in environment
        }
        command = [
            str(ROOT / "scripts/audit-log.sh"), "append-best-effort",
            "--action", "staging-tailnet-recovery",
            "--env", environment_name,
            "--provider", provider,
            "--note", f"scenario={scenario} result=passed",
        ]
        try:
            status, _output = run_command(
                command, environment=audit_environment, cwd=ROOT, timeout=30,
            )
        except ReadinessError:
            status = 1
        if status:
            print("warning: staging Tailnet recovery audit unavailable", file=sys.stderr)


def _absolute(value, reason):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise RecoveryError(reason)
    path = Path(value)
    if any(part in (".", "..") for part in path.parts):
        raise RecoveryError(reason)
    return path


def _load_wrapper(environment):
    try:
        scenario = environment["TAILNET_RECOVERY_SCENARIO"]
        if scenario not in SCENARIOS:
            raise RecoveryError("recovery-scenario-invalid")
        path = _absolute(environment["TAILNET_RECOVERY_CONFIG"], "recovery-config-invalid")
        raw, fence = deploy.read_fenced_input(path, private=True, exact_mode=0o600)
        value = json.loads(raw, object_pairs_hook=deploy.unique_object)
        if (not isinstance(value, dict) or set(value) != CONFIG_FIELDS
                or type(value["schema_version"]) is not int or value["schema_version"] != 1):
            raise RecoveryError("recovery-config-invalid")
        inventory_alias = environment["TAILNET_RECOVERY_TARGET"]
        if (not isinstance(inventory_alias, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", inventory_alias) is None
                or inventory_alias in {"all", "vpn", "ungrouped"}):
            raise RecoveryError("recovery-config-invalid")
        bootstrap_config = _absolute(value["bootstrap_config"], "recovery-config-invalid")
        evidence = bootstrap._output_path(value["evidence"])
        parent = evidence.parent
        info = parent.stat()
        return Wrapper(scenario, inventory_alias, bootstrap_config, evidence, fence,
                       (info.st_dev, info.st_ino), hashlib.sha256(raw).hexdigest())
    except (KeyError, TypeError, ValueError, OSError):
        raise RecoveryError("recovery-inputs-refused") from None


def run_scenario(scenario, inputs, auth_key, *, fresh_inputs, runtime):
    """Kill one armed enrollment and prove recovery from a fresh invocation."""
    if scenario not in SCENARIOS:
        raise RecoveryError("recovery-scenario-invalid")
    if auth_key is None:
        raise RecoveryError("recovery-enrollment-key-required")
    try:
        tailnet._validate_auth_key(auth_key)
    except (tailnet.Refusal, TypeError, ValueError):
        raise RecoveryError("recovery-enrollment-key-invalid") from None

    runtime.prepare(inputs)
    recovery_baseline = (runtime.recovery_baseline(inputs)
                         if scenario == "controller-loss" else None)
    child = None
    pending_recovery = None
    previous_boot = None
    try:
        child = runtime.spawn_pending(inputs, auth_key)
        if scenario == "controller-loss":
            # Enrollment itself verifies the service once. Remember that exact
            # post-pending invocation too, so it cannot masquerade as the later
            # autonomous timer recovery compared with the pre-enroll baseline.
            pending_recovery = runtime.recovery_baseline(inputs)
        runtime.kill_pending(child)
    except (Exception, KeyboardInterrupt, SystemExit):
        if child is not None:
            runtime.cleanup_pending(child)
        raise
    if scenario == "controller-loss":
        # The notification follows the guest's fsynced pending reply. Waiting a
        # complete lease from that later instant cannot shorten guest recovery.
        runtime.sleep(tailnet.LEASE_SECONDS + 1)
    else:
        previous_boot = runtime.boot_id(inputs)
        runtime.reboot(inputs)

    recovered = None
    for attempt in range(RECOVERY_ATTEMPTS):
        with fresh_inputs() as candidate:
            status = runtime.recovered_status(candidate)
            if status == "idle":
                if (scenario == "controller-loss"
                        and not runtime.autonomous_recovery(
                            candidate, (recovery_baseline, pending_recovery))):
                    raise RecoveryError("recovery-autonomous-proof-failed")
                if scenario == "reboot":
                    if previous_boot is None:
                        raise RecoveryError("recovery-previous-boot-missing")
                    if not runtime.reboot_recovery(candidate, previous_boot):
                        raise RecoveryError("recovery-current-boot-proof-failed")
                runtime.postconditions(candidate)
                runtime.final_guard(candidate)
                recovered = candidate
                break
            if status not in {"pending", "expired", "rolling_back", "firewall_restored"}:
                raise RecoveryError("recovery-status-refused")
        if attempt + 1 < RECOVERY_ATTEMPTS:
            runtime.sleep(RECOVERY_POLL_SECONDS)
    if recovered is None:
        raise RecoveryError("recovery-timeout")

    return {
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


def _publish(wrapper, result):
    payload = tailnet._canonical_bytes(result)
    parent_fd = os.open(wrapper.evidence.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".tailnet-recovery-" + secrets.token_hex(16)
    created = False
    try:
        info = os.fstat(parent_fd)
        if ((info.st_dev, info.st_ino) != wrapper.parent_identity
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
            raise RecoveryError("recovery-evidence-parent-changed")
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent_fd)
        created = True
        try:
            os.fchmod(handle, 0o600)
            tailnet._write_all(handle, payload)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temporary, wrapper.evidence.name, src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd, follow_symlinks=False)
        os.unlink(temporary, dir_fd=parent_fd)
        created = False
        os.fsync(parent_fd)
    finally:
        if created:
            os.unlink(temporary, dir_fd=parent_fd)
            os.fsync(parent_fd)
        os.close(parent_fd)


def execute(environment, runtime=None):
    """Run one staging recovery scenario through validated, private inputs."""
    wrapper = _load_wrapper(environment)
    if runtime is None:
        runtime = Runtime()
    deploy.verify_input_fence(wrapper.fence)

    def fresh_inputs():
        deploy.verify_input_fence(wrapper.fence)
        return runtime.open_inputs(environment, wrapper.bootstrap_config, wrapper.inventory_alias)

    with fresh_inputs() as inputs:
        if (not isinstance(inputs.config, dict)
                or inputs.config.get("inventory_alias") != wrapper.inventory_alias
                or not isinstance(inputs.config.get("environment"), str)
                or re.fullmatch(r"ci-staging-[A-Za-z0-9][A-Za-z0-9-]{0,47}",
                                inputs.config["environment"]) is None):
            raise RecoveryError("recovery-staging-only")
        if Path(inputs.config["output"]) == wrapper.evidence:
            raise RecoveryError("recovery-evidence-collision")
        result = run_scenario(
            wrapper.scenario, inputs, environment.get("TAILSCALE_AUTH_KEY"),
            fresh_inputs=fresh_inputs, runtime=runtime,
        )
        runtime.final_guard(inputs)
        result = {
            **result,
            "source_revision": inputs.config["source_revision"],
            "deployable_digest": inputs.config["deployable_digest"],
            "binding_sha256": hashlib.sha256(
                tailnet._canonical_bytes(bootstrap._binding(inputs))
            ).hexdigest(),
        }
        audit_environment_name = inputs.config["environment"]
        audit_provider = inputs.config["provider"]
    deploy.verify_input_fence(wrapper.fence)
    result = {**result, "input_sha256": wrapper.input_sha256}
    _publish(wrapper, result)
    runtime.audit(
        environment, audit_environment_name, audit_provider, wrapper.scenario,
        wrapper.evidence,
    )
    return result


def main():
    import sys
    from bootstrap_readiness import ReadinessError, cancellation
    try:
        with cancellation():
            result = execute(dict(os.environ))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (RecoveryError, bootstrap.BootstrapError, tailnet.Refusal,
            ReadinessError, deploy.DeployError, OSError, ValueError, TypeError, KeyError):
        print(json.dumps({
            "status": "error",
            "reason": "staging-tailnet-recovery-failed",
            "action": "inspect-private-staging-state",
        }, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
