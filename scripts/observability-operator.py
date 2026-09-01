#!/usr/bin/env python3
"""Explicit, exact-host operator surface for centralized observability."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from typing import Any

import yaml

import fleet_inspection

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / "ansible"
COMPONENTS = {
    "agent": "observability_agent",
    "control-plane": "observability_control_plane",
    "deadman": "observability_deadman",
}
SECRET_COMMANDS = frozenset({"render", "validate", "rotate", "rollback"})
MUTATING_COMMANDS = frozenset({"drill", "rotate", "rollback", "remove"})
SAFE_GENERATION = re.compile(r"^[0-9a-f]{64}$")
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


class OperatorError(Exception):
    """A bounded failure category safe for operator output."""


def _private_file(path: Path | None, category: str) -> Path:
    if path is None:
        raise OperatorError(category)
    try:
        absolute = Path(fleet_inspection._local_file(path, private=True))
        metadata = absolute.stat(follow_symlinks=False)
    except (fleet_inspection.InspectionError, OSError):
        raise OperatorError(category) from None
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise OperatorError(category)
    return absolute


def _require_enabled_component(path: Path, component: str) -> None:
    descriptor = -1
    try:
        descriptor = fleet_inspection._open_local_file(path, private=True)
        raw = b""
        while len(raw) <= fleet_inspection.LIMIT:
            chunk = os.read(
                descriptor,
                min(65536, fleet_inspection.LIMIT + 1 - len(raw)),
            )
            if not chunk:
                break
            raw += chunk
        if len(raw) > fleet_inspection.LIMIT:
            raise OperatorError("private variables rejected")
        document = yaml.safe_load(raw.decode("utf-8"))
        value = document[COMPONENTS[component]]
        if not isinstance(value, dict) or value.get("enabled") is not True:
            raise OperatorError("enabled component variables required")
    except OperatorError:
        raise
    except (
        fleet_inspection.InspectionError,
        KeyError,
        OSError,
        UnicodeError,
        yaml.YAMLError,
    ):
        raise OperatorError("private variables rejected") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _debug_disabled() -> None:
    for name in ("ANSIBLE_DEBUG", "ANSIBLE_DIFF_ALWAYS"):
        if os.environ.get(name, "").strip().lower() in TRUE_VALUES:
            raise OperatorError("Ansible debug or diff is forbidden")


def _environment(secrets: Path | None = None) -> dict[str, str]:
    allowed = {
        key: os.environ[key]
        for key in (
            "HOME",
            "LANG",
            "LC_ALL",
            "LOGNAME",
            "PATH",
            "TMPDIR",
            "TZ",
            "USER",
        )
        if key in os.environ
    }
    allowed.update(
        {
            "ANSIBLE_CONFIG": str(ANSIBLE / "ansible.cfg"),
            "ANSIBLE_DEBUG": "false",
            "ANSIBLE_DIFF_ALWAYS": "false",
            "ANSIBLE_NOCOLOR": "true",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    if secrets is not None:
        allowed["VPN_SECRETS_FILE"] = str(secrets)
    return allowed


def _source_identity() -> tuple[str, str]:
    try:
        result = subprocess.run(
            [str(ROOT / "scripts" / "deploy-source-identity.sh"), "--identity"],
            cwd=ROOT,
            env=_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
            check=True,
        )
        revision, digest = result.stdout.strip().split()
    except (OSError, subprocess.SubprocessError, ValueError):
        raise OperatorError("source identity unavailable") from None
    if not re.fullmatch(r"[0-9a-f]{40,64}", revision) or not SAFE_GENERATION.fullmatch(
        digest
    ):
        raise OperatorError("source identity rejected")
    return revision, digest


def _selected_host(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return fleet_inspection.select_hosts(args.inventory, [args.host])[0]
    except (fleet_inspection.InspectionError, OSError):
        raise OperatorError("exact inventory host rejected") from None


def _require_inventory_scope(args: argparse.Namespace) -> None:
    descriptor = -1
    try:
        descriptor = fleet_inspection._open_local_file(args.inventory)
        raw = b""
        while len(raw) <= fleet_inspection.LIMIT:
            chunk = os.read(
                descriptor,
                min(65536, fleet_inspection.LIMIT + 1 - len(raw)),
            )
            if not chunk:
                break
            raw += chunk
        if len(raw) > fleet_inspection.LIMIT:
            raise OperatorError("inventory scope rejected")
        section = ""
        values: dict[str, str] | None = None
        for raw_line in raw.decode("utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                continue
            if section != "vpn":
                continue
            words = shlex.split(line, comments=True)
            if words and words[0] == args.host:
                values = {}
                for assignment in words[1:]:
                    key, separator, value = assignment.partition("=")
                    if separator:
                        values[key] = value
                break
        expected_class = {
            "agent": "vpn",
            "control-plane": "control-plane",
            "deadman": "deadman",
        }[args.component]
        if (
            values is None
            or values.get("env") != args.environment
            or values.get("observability_host_class") != expected_class
        ):
            raise OperatorError("inventory scope rejected")
    except OperatorError:
        raise
    except (fleet_inspection.InspectionError, OSError, UnicodeError, ValueError):
        raise OperatorError("inventory scope rejected") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _playbook(component: str, host: str, *, remove: bool = False) -> str:
    role = COMPONENTS[component]
    play: dict[str, Any] = {
        "name": f"Converge exact {component} observability component",
        "hosts": host,
        "serial": 1,
        "become": True,
        "gather_facts": True,
        "any_errors_fatal": True,
    }
    if remove:
        defaults = yaml.safe_load(
            (ANSIBLE / "roles" / role / "defaults" / "main.yml").read_text(
                encoding="utf-8"
            )
        )
        component_defaults = defaults.get(role)
        if not isinstance(component_defaults, dict):
            raise OperatorError("role defaults rejected")
        component_defaults = dict(component_defaults)
        component_defaults["enabled"] = False
        play["vars"] = {role: component_defaults}
    else:
        play["vars_files"] = ["{{ lookup('env', 'VPN_SECRETS_FILE') }}"]
    play["roles"] = [{"role": role}]
    return yaml.safe_dump([play], sort_keys=False)


def _run_playbook(
    args: argparse.Namespace,
    *,
    secrets: Path | None,
    check: bool = False,
    syntax: bool = False,
    remove: bool = False,
) -> None:
    payload = _playbook(args.component, args.host, remove=remove)
    revision, digest = _source_identity()
    with tempfile.TemporaryDirectory(prefix="observability-operator-") as directory:
        os.chmod(directory, 0o700)
        path = Path(directory) / "playbook.yml"
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.write(descriptor, payload.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        command = [
            "ansible-playbook",
            str(path),
            "-i",
            str(args.inventory),
            "--limit",
            args.host,
        ]
        if args.vars is not None and not remove:
            command.extend(["--extra-vars", f"@{args.vars}"])
        if check:
            command.append("--check")
        if syntax:
            command.append("--syntax-check")
        try:
            environment = _environment(secrets)
            environment["DEPLOY_SOURCE_REVISION"] = revision
            environment["DEPLOYABLE_SOURCE_DIGEST"] = digest
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            raise OperatorError("ansible unavailable") from None
        if result.returncode:
            raise OperatorError("ansible command failed")


def _status_program(component: str) -> bytes:
    units = {
        "agent": (
            "observability-agent.service",
            "observability-agent-adapter.timer",
            "observability-agent-health-adapter.timer",
        ),
        "control-plane": (
            "observability-prometheus.service",
            "observability-alertmanager.service",
            "observability-control-plane-adapter.timer",
        ),
        "deadman": (
            "observability-deadman.service",
            "observability-deadman-tick.timer",
        ),
    }[component]
    readiness = {
        "agent": ("http://127.0.0.1:19090/-/ready",),
        "control-plane": (
            "http://127.0.0.1:9090/-/ready",
            "http://127.0.0.1:9093/-/ready",
        ),
        "deadman": ("http://127.0.0.1:19094/v1/status",),
    }[component]
    source = f"""import json
import subprocess
import urllib.request

COMPONENT = {component!r}
UNITS = {units!r}
READINESS = {readiness!r}
states = {{}}
for unit in UNITS:
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "show", unit, "--property=ActiveState", "--value"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=5, check=False,
        )
        value = result.stdout.strip()
        states[unit] = value if result.returncode == 0 and value in {{"active", "inactive", "failed", "activating", "deactivating"}} else "unknown"
    except (OSError, subprocess.SubprocessError):
        states[unit] = "unknown"
ready = []
for url in READINESS:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            ready.append(response.status == 200)
    except Exception:
        ready.append(False)
healthy = all(value == "active" for value in states.values()) and all(ready)
print(json.dumps({{"schema_version": 1, "component": COMPONENT, "state": "healthy" if healthy else "degraded", "units": states}}, sort_keys=True))
"""
    return source.encode("utf-8")


def _drill_program() -> bytes:
    return b"""import datetime
import json
import urllib.request

now = datetime.datetime.now(datetime.timezone.utc)
labels = {"alertname": "ObservabilitySyntheticDrill", "component": "control-plane", "environment": "staging", "severity": "warning"}
base = {"labels": labels, "annotations": {"summary": "operator synthetic delivery drill", "runbook": "docs/OBSERVABILITY-OPERATIONS.md"}, "startsAt": now.isoformat()}
def send(alert):
    request = urllib.request.Request("http://127.0.0.1:9093/api/v2/alerts", data=json.dumps([alert]).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status not in (200, 202):
            raise RuntimeError("delivery rejected")
send(base)
resolved = dict(base)
resolved["endsAt"] = (now + datetime.timedelta(seconds=1)).isoformat()
send(resolved)
print(json.dumps({"schema_version": 1, "component": "control-plane", "state": "submitted"}, sort_keys=True))
"""


def _remote(
    args: argparse.Namespace,
    host: dict[str, Any],
    payload: bytes,
    *,
    operation: str,
) -> dict[str, Any]:
    try:
        command = fleet_inspection.ssh_command(host, args.known_hosts)
        raw = fleet_inspection.bounded_command(
            command,
            timeout=45,
            limit=16384,
            input_bytes=payload,
            environment=_environment(),
        )
        value = json.loads(raw.decode("utf-8"))
    except (
        fleet_inspection.InspectionError,
        json.JSONDecodeError,
        OSError,
        UnicodeError,
    ):
        raise OperatorError("remote command failed") from None
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("component") != args.component
    ):
        raise OperatorError("remote report rejected")
    if operation == "status":
        expected_units = {
            "agent": {
                "observability-agent.service",
                "observability-agent-adapter.timer",
                "observability-agent-health-adapter.timer",
            },
            "control-plane": {
                "observability-prometheus.service",
                "observability-alertmanager.service",
                "observability-control-plane-adapter.timer",
            },
            "deadman": {
                "observability-deadman.service",
                "observability-deadman-tick.timer",
            },
        }[args.component]
        units = value.get("units")
        if (
            set(value) != {"schema_version", "component", "state", "units"}
            or value.get("state") not in {"healthy", "degraded"}
            or not isinstance(units, dict)
            or set(units) != expected_units
            or any(
                state
                not in {
                    "active",
                    "inactive",
                    "failed",
                    "activating",
                    "deactivating",
                    "unknown",
                }
                for state in units.values()
            )
        ):
            raise OperatorError("remote report rejected")
    else:
        expected_state = "submitted"
        if (
            set(value) != {"schema_version", "component", "state"}
            or value.get("state") != expected_state
        ):
            raise OperatorError("remote report rejected")
    return value


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--inventory", type=Path, required=True)
    common.add_argument("--host", required=True)
    common.add_argument("--environment", choices=("staging", "prod"), required=True)
    common.add_argument("--component", choices=tuple(COMPONENTS), required=True)
    common.add_argument("--known-hosts", type=Path, required=True)
    common.add_argument("--secrets", type=Path)
    common.add_argument("--vars", type=Path)
    parser = argparse.ArgumentParser(prog="observability-operator.py")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("render", "validate", "status"):
        commands.add_parser(command, parents=[common])
    drill = commands.add_parser("drill", parents=[common])
    drill.add_argument("--confirm-notification", action="store_true")
    for command in ("rotate", "rollback", "remove"):
        mutation = commands.add_parser(command, parents=[common])
        mutation.add_argument("--confirm", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        _debug_disabled()
        if args.command == "drill":
            if not args.confirm_notification:
                raise OperatorError("--confirm-notification required")
            if args.environment != "staging":
                raise OperatorError("drills require staging")
            if args.component != "control-plane":
                raise OperatorError("drill component rejected")
        host = _selected_host(args)
        _require_inventory_scope(args)
        source_revision, deployable_source_digest = _source_identity()
        try:
            fleet_inspection._local_file(args.known_hosts)
        except fleet_inspection.InspectionError:
            raise OperatorError("known-hosts rejected") from None
        secrets = None
        if args.command in SECRET_COMMANDS:
            secrets = _private_file(args.secrets, "private secrets required")
            args.vars = _private_file(args.vars, "private variables required")
            _require_enabled_component(args.vars, args.component)
        if args.command == "drill":
            result = _remote(args, host, _drill_program(), operation="drill")
        elif args.command in MUTATING_COMMANDS and not getattr(args, "confirm", False):
            raise OperatorError("--confirm required")
        elif args.command == "render":
            _run_playbook(args, secrets=secrets, check=True)
            result = {
                "schema_version": 1,
                "component": args.component,
                "host": args.host,
                "state": "rendered-check",
            }
        elif args.command == "validate":
            _run_playbook(args, secrets=secrets, syntax=True)
            result = {
                "schema_version": 1,
                "component": args.component,
                "host": args.host,
                "state": "validated",
            }
        elif args.command == "status":
            result = _remote(
                args, host, _status_program(args.component), operation="status"
            )
        elif args.command == "rotate":
            _run_playbook(args, secrets=secrets)
            result = {
                "schema_version": 1,
                "component": args.component,
                "host": args.host,
                "state": "rotated",
            }
        elif args.command == "rollback":
            _run_playbook(args, secrets=secrets)
            result = {
                "schema_version": 1,
                "component": args.component,
                "host": args.host,
                "state": "rolled-back",
            }
        elif args.command == "remove":
            _run_playbook(args, secrets=None, remove=True)
            result = {
                "schema_version": 1,
                "component": args.component,
                "host": args.host,
                "state": "removed",
            }
        else:  # pragma: no cover
            raise OperatorError("command rejected")
        result = dict(result)
        result["host"] = args.host
        result["controller_source_revision"] = source_revision
        result["controller_deployable_digest"] = deployable_source_digest
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except OperatorError as exc:
        print(f"observability-operator: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
