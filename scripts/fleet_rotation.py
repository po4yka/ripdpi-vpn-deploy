"""Rotate an explicit fleet plan with authenticated survivors and durable progress."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from bootstrap_readiness import ReadinessError, run_command
from fleet_rotation_liveness import (
    RotationError,
    UniqueLoader,
    healthy_survivors,
    read_regular,
)

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
PAIR = re.compile(r"(upcloud|hetzner|vultr|scaleway):([a-z0-9][a-z0-9-]{0,63})\Z")



def keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise RotationError("invalid-plan")


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def load_plan(path):
    path = Path(path).absolute()
    try:
        plan = yaml.load(read_regular(path), Loader=UniqueLoader)
        keys(plan, ("schema_version", "id", "min_active", "health", "rotations"))
        if (type(plan["schema_version"]) is not int or plan["schema_version"] != 1
                or not matches(NAME, plan["id"]) or type(plan["min_active"]) is not int
                or not 1 <= plan["min_active"] <= 100):
            raise RotationError("invalid-plan")
        health = plan["health"]
        keys(health, ("config", "nodes"))
        config = health["config"]
        if not isinstance(config, str) or not config or len(config) > 4096 or any(ord(c) < 32 for c in config):
            raise RotationError("invalid-plan")
        # Lexical absolute identity: dry-run never follows or opens health inputs.
        health["config"] = os.path.abspath(os.path.join(path.parent, config))
        nodes, rotations = health["nodes"], plan["rotations"]
        if (not isinstance(nodes, list) or not 1 <= len(nodes) <= 100
                or not isinstance(rotations, list) or not 1 <= len(rotations) <= 100):
            raise RotationError("invalid-plan")
        pairs, aliases = set(), set()
        for node in nodes:
            keys(node, ("current", "inventory_alias"))
            if (not matches(PAIR, node["current"]) or node["current"].endswith(":default")
                    or not matches(ALIAS, node["inventory_alias"])
                    or node["current"] in pairs or node["inventory_alias"] in aliases):
                raise RotationError("invalid-plan")
            pairs.add(node["current"])
            aliases.add(node["inventory_alias"])
        sources, destinations = set(), set()
        for entry in rotations:
            keys(entry, ("current", "new_env"), ("new_zone",))
            if (not isinstance(entry["current"], str) or entry["current"] not in pairs
                    or entry["current"] in sources or not matches(NAME, entry["new_env"])
                    or entry["new_env"] == "default"
                    or ("new_zone" in entry and not matches(ALIAS, entry["new_zone"]))):
                raise RotationError("invalid-plan")
            destination = entry["current"].split(":", 1)[0] + ":" + entry["new_env"]
            if destination in pairs or destination in destinations:
                raise RotationError("invalid-plan")
            destinations.add(destination)
            sources.add(entry["current"])
        return plan
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError, TypeError, ValueError):
        raise RotationError("invalid-plan") from None


def plan_digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Journal:
    def __init__(self, root, plan_id):
        self.directory = Path(root) / ".omc" / "state"
        self.path = self.directory / f"fleet-rotate-{plan_id}.json"
        self.lock_path = self.path.with_suffix(".lock")
        self.pending_path = self.path.with_suffix(".pending")
        self.lock = None

    def __enter__(self):
        try:
            for directory in (self.directory.parent, self.directory):
                directory.mkdir(mode=0o700, exist_ok=True)
                info = directory.lstat()
                if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                        or info.st_mode & 0o077):
                    raise RotationError("unsafe-state-directory")
            self.lock = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            info = os.fstat(self.lock)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                raise RotationError("unsafe-lock")
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            named = self.lock_path.lstat()
            if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
                raise RotationError("unsafe-lock")
            if self.pending_path.exists() or self.pending_path.is_symlink():
                raise RotationError("journal-publication-uncertain")
            return self
        except OSError:
            self.__exit__(None, None, None)
            raise RotationError("state-lock-unavailable") from None
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None

    def read(self):
        try:
            return json.loads(read_regular(self.path, private=True), object_pairs_hook=self.unique_json)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, UnicodeError, RecursionError):
            raise RotationError("invalid-journal") from None

    @staticmethod
    def unique_json(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RotationError("invalid-journal")
            result[key] = value
        return result

    def write(self, value):
        # Re-admit any prior authority before replacing its name.
        previous = b"null\n"
        if self.path.exists() or self.path.is_symlink():
            previous = read_regular(self.path, private=True)
        # Retain the last complete journal until the replacement is durable.
        # A crash or sync failure leaves this private marker as a replay fence.
        pending = os.open(self.pending_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(pending, "wb") as handle:
            handle.write(previous)
            handle.flush()
            os.fsync(handle.fileno())
        self.sync_directory()
        descriptor, name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.directory)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.path)
            self.sync_directory()
            os.unlink(self.pending_path)
            self.sync_directory()
        except BaseException:
            # If final directory synchronization failed after unlink, retain a
            # visible refusal marker as well as the durable prior publication.
            if not self.pending_path.exists():
                try:
                    descriptor = os.open(self.pending_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(previous)
                        handle.flush()
                        os.fsync(handle.fileno())
                    self.sync_directory()
                except OSError:
                    pass  # The original error still refuses the invocation.
            raise
        finally:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass

    def sync_directory(self):
        directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def initial_state(plan):
    return {"schema_version": 1, "id": plan["id"], "plan_sha256": plan_digest(plan),
            "next_idx": 0, "completed": [], "in_flight": None}


def validate_state(state, plan):
    expected = initial_state(plan)
    if not isinstance(state, dict) or state.keys() != expected.keys():
        raise RotationError("invalid-journal")
    if state["schema_version"] != 1 or type(state["schema_version"]) is not int:
        raise RotationError("invalid-journal")
    if state["id"] != expected["id"] or state["plan_sha256"] != expected["plan_sha256"]:
        raise RotationError("plan-mismatch")
    index = state["next_idx"]
    if (type(index) is not int or not 0 <= index <= len(plan["rotations"])
            or state["completed"] != plan["rotations"][:index]
            or (state["in_flight"] is not None
                and (type(state["in_flight"]) is not int or state["in_flight"] != index
                     or index >= len(plan["rotations"])))):
        raise RotationError("invalid-journal")
    if state["in_flight"] is not None:
        raise RotationError("in-flight-outcome-requires-operator-reconciliation")


def execute_rotation(entry, root, lock):
    provider, environment = entry["current"].split(":", 1)
    child_env = dict(os.environ)
    child_env.update(PROVIDER=provider, ENV=environment, BLUE_ENV=environment,
                     GREEN_ENV=entry["new_env"], GREEN_ZONE=entry.get("new_zone", ""), DRY_RUN="0")
    # The existing script keeps every interactive provider/deploy/pivot gate.
    child = subprocess.Popen([str(Path(root) / "scripts/blue-green.sh")], env=child_env,
                             start_new_session=True, pass_fds=(lock,))
    try:
        if child.wait() != 0:
            raise RotationError("rotation-failed-in-flight-retained")
    except BaseException:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
        raise


def audit(root, action, plan, entry=None):
    environment = dict(os.environ)
    if entry is not None:
        environment["PROVIDER"], environment["ENV"] = entry["current"].split(":", 1)
    command = [str(Path(root) / "scripts/audit-log.sh"), "append-best-effort", "--action", action,
               "--note", f"plan={plan['id']} rotations={len(plan['rotations'])}"]
    if entry is None:
        command.extend(("--provider", "fleet"))
    try:
        status, _ = run_command(command, timeout=15, environment=environment)
        if status:
            print("fleet-rotate: audit append unavailable", file=sys.stderr)
    except ReadinessError:
        print("fleet-rotate: audit append unavailable", file=sys.stderr)


def operator_confirm(prompt):
    # Do not buffer later answers that belong to blue-green's inherited stdin.
    print(prompt + " [yes/NO]: ", end="", flush=True)
    answer = bytearray()
    while len(answer) <= 32:
        value = os.read(sys.stdin.fileno(), 1)
        if not value:
            return False
        if value == b"\n":
            return answer == b"yes"
        answer.extend(value)
    return False


def require_health(path, plan, nodes, current_alias):
    identity = plan_digest(plan)
    if plan_digest(load_plan(path)) != identity:
        raise RotationError("plan-mismatch")
    healthy = healthy_survivors(Path(plan["health"]["config"]), nodes, excluded=(current_alias,))
    admitted = {node["inventory_alias"] for node in nodes} - {current_alias}
    if not isinstance(healthy, set) or not healthy <= admitted or len(healthy) < plan["min_active"]:
        raise RotationError("authenticated-survivor-floor-not-met")
    if plan_digest(load_plan(path)) != identity:
        raise RotationError("plan-mismatch")


def run_plan(path, *, root=ROOT, resume=False, dry_run=False, confirm=operator_confirm):
    plan = load_plan(path)
    print(f"plan id={plan['id']} rotations={len(plan['rotations'])} min_active={plan['min_active']}", flush=True)
    if dry_run:
        for entry in plan["rotations"]:
            print(f"  {entry['current']} -> ENV={entry['new_env']} zone={entry.get('new_zone', '(same)')}")
        return 0
    with Journal(root, plan["id"]) as journal:
        state = journal.read()
        if state is None:
            if resume:
                raise RotationError("resume-journal-missing")
            state = initial_state(plan)
            journal.write(state)
        elif not resume:
            raise RotationError("journal-already-exists-use-resume")
        validate_state(state, plan)
        for index in range(state["next_idx"], len(plan["rotations"])):
            entry = plan["rotations"][index]
            excluded = {item["current"] for item in plan["rotations"][:index]}
            nodes = [node for node in plan["health"]["nodes"] if node["current"] not in excluded]
            current_alias = next(node["inventory_alias"] for node in nodes if node["current"] == entry["current"])
            require_health(path, plan, nodes, current_alias)
            if not confirm(f"Proceed with rotating {entry['current']}?"):
                print("rotation stopped at completed boundary; use --resume", flush=True)
                return 1
            require_health(path, plan, nodes, current_alias)
            state = {**state, "in_flight": index}
            journal.write(state)
            execute_rotation(entry, root, journal.lock)
            state = {**state, "next_idx": index + 1,
                     "completed": plan["rotations"][:index + 1], "in_flight": None}
            journal.write(state)
            audit(root, "fleet-rotate-step", plan, entry)
        print("fleet rotation complete", flush=True)
        audit(root, "fleet-rotate-complete", plan)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
        signal.signal(signum, interrupted)
    try:
        return run_plan(args.plan, root=ROOT, resume=args.resume, dry_run=args.dry_run)
    except (RotationError, OSError) as error:
        category = str(error) if isinstance(error, RotationError) else "local-operation-failed"
        print(f"fleet-rotate: {category}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
