#!/usr/bin/env python3
"""Configure exactly three backup files inside an owner-quiesced window."""
from __future__ import annotations

import argparse
import base64
import configparser
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import uuid

ROOT = Path("/")
OWNER_UID = 0
FILES = ("etc/rclone/rclone.conf", "usr/local/sbin/vpn-backup.sh",
         "usr/local/sbin/vpn-backup-restore-drill.sh")
MODES = (0o600, 0o750, 0o750)
UNITS = ("vpn-backup.service", "vpn-backup-restore-drill.service",
         "vpn-backup.timer", "vpn-backup-restore-drill.timer")
LOCK = "run/vpn-backup-configure.lock"
LIMIT = 1024 * 1024


class ConfigError(Exception):
    """Only categorical, non-secret diagnostics leave this helper."""


def path(relative):
    return ROOT / relative


def safe(target, *, private=False, missing=False):
    current = ROOT
    for part in target.relative_to(ROOT).parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing:
                return
            raise ConfigError("missing-required-path") from None
        if (stat.S_ISLNK(info.st_mode) or info.st_uid != OWNER_UID
                or info.st_mode & 0o022):
            raise ConfigError("unsafe-root-owned-path")
        if current != target and not stat.S_ISDIR(info.st_mode):
            raise ConfigError("unsafe-parent")
    if private and info.st_mode & 0o077:
        raise ConfigError("nonprivate-path")


def read(target, *, private=False, limit=LIMIT):
    safe(target, private=private)
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ConfigError("unsafe-or-oversized-file")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ConfigError("oversized-file")
        return data


def quiescent():
    result = subprocess.run(
        ["systemctl", "show", "--no-pager", "--property=Id,LoadState,ActiveState,SubState,Job,UnitFileState", *UNITS],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if result.returncode:
        raise ConfigError("unit-state-unavailable")
    states = {}
    for block in result.stdout.strip().split("\n\n"):
        fields = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        name = fields.get("Id")
        if name in states:
            raise ConfigError("ambiguous-unit-state")
        states[name] = fields
    if set(states) != set(UNITS):
        raise ConfigError("missing-unit-state")
    for name, fields in states.items():
        if (fields.get("LoadState") not in ("loaded", "masked")
                or fields.get("ActiveState") != "inactive"
                or fields.get("SubState") != "dead"
                or fields.get("Job") not in ("", "0")
                or (name.endswith(".timer") and fields.get("UnitFileState") != "disabled")):
            raise ConfigError("backup-not-quiescent")


def recovery_clear():
    base = path("var/lib/vpn-backup/configure-recovery")
    safe(base, missing=True)
    if not base.exists():
        return
    try:
        safe(base, private=True)
        with os.scandir(base) as entries:
            for count, entry in enumerate(entries):
                if count >= 1024 or not re.fullmatch(r"[0-9a-f]{32}", entry.name):
                    raise ConfigError("invalid-recovery-entry")
                recovery = base / entry.name
                safe(recovery, private=True)
                if read(recovery / "status", private=True) not in (b"complete", b"rolled-back"):
                    raise ConfigError("incomplete-recovery")
    except (ConfigError, OSError):
        raise ConfigError("recovery-incomplete-keep-timers-stopped") from None


def repository_decryptable():
    environment = {key: value for key, value in os.environ.items() if not key.startswith("RESTIC_")}
    try:
        result = subprocess.run(
            [str(path("usr/bin/restic")), "--no-cache", "--no-lock",
             "-r", str(path("var/backups/vpn-restic")),
             "--password-file", str(path("etc/restic/password")), "cat", "config"],
            env=environment, capture_output=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ConfigError("local-repository-unreadable") from None
    if result.returncode:
        raise ConfigError("local-repository-unreadable")


def prerequisites():
    if os.geteuid() != OWNER_UID:
        raise ConfigError("root-required")
    safe(path("var/backups/vpn-restic"), private=True)
    # Restic's encrypted config can be read-only/public-readable; its parent
    # repository is private, and the password must itself remain private.
    read(path("var/backups/vpn-restic/config"))
    read(path("etc/restic/password"), private=True)
    read(path("usr/bin/restic"), limit=128 * LIMIT)
    if not os.access(path("usr/bin/restic"), os.X_OK):
        raise ConfigError("restic-not-executable")
    for unit in UNITS:
        read(path(f"etc/systemd/system/{unit}"))
    safe(path("usr/local/sbin"))
    safe(path("run"))
    recovery_clear()
    quiescent()
    repository_decryptable()


def claim():
    prerequisites()
    lock = path(LOCK)
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise ConfigError("configuration-locked") from None
    token = uuid.uuid4().hex
    try:
        atomic_write(lock / "token", token.encode(), 0o600)
        (lock / "stage").mkdir(mode=0o700)
    except BaseException:
        shutil.rmtree(lock)
        raise
    return token


def owned(token):
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ConfigError("lock-not-owned")
    safe(path(LOCK), private=True)
    if not hmac.compare_digest(read(path(f"{LOCK}/token"), private=True), token.encode()):
        raise ConfigError("lock-not-owned")
    return path(f"{LOCK}/stage")


def validate(token):
    stage = owned(token)
    if not hmac.compare_digest(read(stage / "password", private=True),
                               read(path("etc/restic/password"), private=True)):
        raise ConfigError("restic-password-mismatch")
    settings = json.loads(read(stage / "settings.json", private=True))
    remote = settings.get("rclone_remote", "")
    destination = settings.get("rclone_path", "")
    if (settings.get("enabled") is not True
            or settings.get("restic_repo_dir") != "/var/backups/vpn-restic"
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", remote)
            or not re.fullmatch(r"[A-Za-z0-9/][A-Za-z0-9._/-]*", destination)
            or any(part in (".", "..", "") for part in destination.strip("/").split("/"))
            or type(settings.get("transfers")) is not int
            or not 1 <= settings["transfers"] <= 64
            or not re.fullmatch(r"off|[0-9]+(?:\.[0-9]+)?[kKmMgG]?", settings.get("bwlimit", ""))):
        raise ConfigError("unsafe-backup-settings")
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read_string(read(stage / FILES[0], private=True).decode())
        if not config.has_section(remote) or not config.get(remote, "type", fallback="").strip():
            raise ConfigError("missing-rclone-remote")
    except (configparser.Error, UnicodeError):
        raise ConfigError("invalid-rclone-config") from None
    for relative in FILES[1:]:
        read(stage / relative)
        result = subprocess.run(["bash", "-n", str(stage / relative)], capture_output=True, timeout=10)
        if result.returncode:
            raise ConfigError("invalid-backup-script")
    for relative in FILES:
        target = path(relative)
        safe(target, missing=True)
        if target.exists():
            read(target, private=relative == FILES[0])


def atomic_write(target, data, mode):
    safe(target.parent)
    safe(target, missing=True)
    fd, temporary = tempfile.mkstemp(prefix=".backup-configure-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def snapshot():
    previous = {}
    for relative in FILES:
        target = path(relative)
        previous[relative] = None if not target.exists() else {
            "data": base64.b64encode(read(target)).decode(),
            "mode": stat.S_IMODE(target.stat().st_mode),
        }
    return previous


def publish(token):
    validate(token)
    quiescent()
    stage = owned(token)
    previous = snapshot()
    candidate = {relative: {"data": base64.b64encode(read(stage / relative)).decode(), "mode": mode}
                 for relative, mode in zip(FILES, MODES)}
    if previous == candidate:
        quiescent()
        return False
    base = path("var/lib/vpn-backup/configure-recovery")
    safe(base, missing=True)
    base.mkdir(mode=0o700, exist_ok=True)
    safe(base, private=True)
    recovery = base / token
    recovery.mkdir(mode=0o700)
    atomic_write(recovery / "previous.json", json.dumps(previous).encode(), 0o600)
    atomic_write(path(f"{LOCK}/recovery"), str(recovery.relative_to(ROOT)).encode(), 0o600)
    atomic_write(recovery / "status", b"pending", 0o600)
    try:
        destination = path("etc/rclone")
        safe(destination, missing=True)
        destination.mkdir(mode=0o700, exist_ok=True)
        safe(destination, private=True)
        for relative, mode in zip(FILES, MODES):
            atomic_write(path(relative), read(stage / relative), mode)
        quiescent()
        if snapshot() != candidate:
            raise ConfigError("publication-verification-failed")
        atomic_write(recovery / "status", b"complete", 0o600)
        return True
    except BaseException:
        failed = False
        for relative, original in previous.items():
            try:
                target = path(relative)
                if original is None:
                    safe(target, missing=True)
                    target.unlink(missing_ok=True)
                else:
                    atomic_write(target, base64.b64decode(original["data"]), original["mode"])
            except BaseException:
                failed = True
        try:
            failed |= snapshot() != previous
            atomic_write(recovery / "status", b"rollback-incomplete" if failed else b"rolled-back", 0o600)
        except BaseException:
            failed = True
        if failed:
            raise ConfigError("rollback-incomplete-keep-timers-stopped") from None
        raise ConfigError("configuration-rolled-back") from None


def release(token):
    owned(token)
    marker = path(f"{LOCK}/recovery")
    if marker.exists():
        relative = read(marker, private=True).decode()
        if relative != f"var/lib/vpn-backup/configure-recovery/{token}":
            raise ConfigError("invalid-recovery-reference")
        status = read(path(relative) / "status", private=True)
        if status not in (b"complete", b"rolled-back"):
            raise ConfigError("rollback-incomplete-keep-timers-stopped")
    shutil.rmtree(path(LOCK))


def select_target(inventory, alias):
    import fleet_inspection
    if not alias or not fleet_inspection.SAFE_NAME.fullmatch(alias):
        raise ConfigError("exact-single-host-required")
    return fleet_inspection.select_hosts(Path(inventory), [alias])[0]


def execution_environment(root):
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE")
                   if key in os.environ}
    environment.update(ANSIBLE_CONFIG=str(root / "ansible/ansible.cfg"), ANSIBLE_DEBUG="false",
                       ANSIBLE_HOST_KEY_CHECKING="true", ANSIBLE_INVENTORY_ENABLED="ini",
                       ANSIBLE_VARS_ENABLED="", ANSIBLE_LOG_PATH=os.devnull,
                       ANSIBLE_STDOUT_CALLBACK="default", ANSIBLE_LOAD_CALLBACK_PLUGINS="false",
                       ANSIBLE_DISPLAY_ARGS_TO_STDOUT="false", ANSIBLE_COLLECTIONS_PATH=os.devnull,
                       ANSIBLE_COLLECTIONS_SCAN_SYS_PATH="false")
    for kind in ("VARS", "CALLBACK", "ACTION", "CONNECTION", "LOOKUP", "FILTER", "TEST",
                 "BECOME", "CACHE", "CLICONF", "DOC_FRAGMENT", "HTTPAPI", "INVENTORY",
                 "NETCONF", "STRATEGY", "TERMINAL"):
        environment[f"ANSIBLE_{kind}_PLUGINS"] = os.devnull
    return environment


def clean_source(root, environment):
    import fleet_inspection
    if fleet_inspection.bounded_command(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
            timeout=15, environment=environment).strip():
        raise ConfigError("clean-source-required")
    result = {}
    for name, flag, length in (("DEPLOY_SOURCE_REVISION", "--revision", 40),
                               ("DEPLOYABLE_SOURCE_DIGEST", "--digest", 64)):
        value = fleet_inspection.bounded_command(
            [str(root / "scripts/deploy-source-identity.sh"), flag], timeout=15,
            environment=environment).decode().strip()
        if not re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", value):
            raise ConfigError("source-identity-required")
        result[name] = value
    return result


def private_file(target, data):
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def prepare_inventory(inventory, alias, directory):
    import fleet_inspection
    with os.fdopen(fleet_inspection._open_local_file(inventory), "rb") as stream:
        data = stream.read(fleet_inspection.LIMIT + 1)
    if len(data) > fleet_inspection.LIMIT:
        raise ConfigError("inventory-limit")
    snapshot_file = directory / "inventory-source.ini"
    private_file(snapshot_file, data)
    host = select_target(snapshot_file, alias)
    # The strict selector above owns host validation. This pass retains only
    # membership metadata from the exact same immutable bytes, not host values.
    section, cohorts = "", set()
    for line in data.decode().splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif section.startswith("vpn-") and shlex.split(line, comments=True) == [alias]:
            cohorts.add(section)
    selected = directory / "inventory.ini"
    groups = ["vpn", *sorted(cohorts)]
    private_file(selected, "".join(f"[{group}]\n{alias}\n" for group in groups).encode())
    return host, sorted(cohorts), selected


def canonical_variables(root, cohorts):
    # Full-site static role imports expose this default even without running
    # the AWG role. The backup restore template requires its interface name.
    result = [str(root / "ansible/roles/amneziawg/defaults/main.yml")]
    for name in ("all", "vpn", *sorted(cohorts)):
        if not re.fullmatch(r"all|vpn|vpn-[a-z0-9][a-z0-9-]*", name):
            raise ConfigError("unsupported-cohort")
        candidate = root / "ansible/group_vars" / (name + ".yml")
        if not candidate.is_file() or candidate.is_symlink():
            raise ConfigError("unsupported-cohort")
        result.append(str(candidate))
    return result


def portable_ssh_arguments(command):
    options, result = iter(command[1:-2]), []
    for flag in options:
        value = next(options)
        if flag in {"-i", "-l", "-p"}:
            value = {"-i": "IdentityFile", "-l": "User", "-p": "Port"}[flag] + "=" + value
            flag = "-o"
        if flag not in {"-F", "-o"}:
            raise ConfigError("unsupported-ssh-option")
        if flag == "-o" and value.startswith(("IdentityFile=", "UserKnownHostsFile=")):
            name, value = value.split("=", 1)
            if any(char in value for char in "\r\n\x00"):
                raise ConfigError("unsafe-ssh-path")
            value = name + '="' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        result.extend((flag, value))
    return shlex.join(result)


def transport_variables(host, overrides, known_hosts):
    import fleet_inspection
    selected = {**host, "transport": overrides.get("ansible_host", host["transport"]),
                "port": overrides.get("ansible_port", host["port"])}
    arguments = portable_ssh_arguments(fleet_inspection.ssh_command(selected, known_hosts))
    return {"ansible_host": selected["transport"], "ansible_port": selected["port"],
            "ansible_user": selected["user"], "ansible_ssh_private_key_file": selected["key"],
            "ansible_ssh_args": arguments, "ansible_ssh_common_args": "", "ansible_ssh_extra_args": "",
            "ansible_ssh_executable": "/usr/bin/ssh", "ansible_scp_executable": "/usr/bin/scp",
            "ansible_sftp_executable": "/usr/bin/sftp", "ansible_connection": "ssh",
            "ansible_python_interpreter": "/usr/bin/python3", "ansible_become": True,
            "ansible_become_user": "root", "ansible_become_method": "sudo", "ansible_become_flags": "-n"}


def materialized_bytes(secrets):
    import fleet_inspection
    original = Path(secrets).expanduser().absolute()
    try:
        # macOS's canonical TMPDIR crosses root-owned /var -> /private/var.
        # Check the original aliases too, before resolving to the strict intake.
        for parent in reversed(original.parents):
            info = parent.lstat()
            sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            if (info.st_uid not in (0, os.geteuid()) or
                    (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022 and not sticky_root)):
                raise ConfigError("unsafe-secret-parent")
        fd = os.open(original, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            initial = os.fstat(stream.fileno())
            if (not stat.S_ISREG(initial.st_mode) or initial.st_uid != os.geteuid()
                    or stat.S_IMODE(initial.st_mode) != 0o600 or initial.st_nlink != 1 or initial.st_size > LIMIT):
                raise ConfigError("unsafe-materialized-secrets")
            canonical = fleet_inspection._open_local_file(original.resolve(strict=True), private=True)
            try:
                resolved = os.fstat(canonical)
                if (initial.st_dev, initial.st_ino) != (resolved.st_dev, resolved.st_ino):
                    raise ConfigError("materialized-secrets-replaced")
            finally:
                os.close(canonical)
            data = stream.read(LIMIT + 1)
            if len(data) > LIMIT:
                raise ConfigError("oversized-materialized-secrets")
            return data
    except (OSError, fleet_inspection.InspectionError):
        raise ConfigError("unsafe-materialized-secrets") from None


def controller(inventory, alias, secrets):
    from ansible.module_utils.parsing.convert_bool import boolean
    try:
        debug_enabled = boolean(os.environ.get("ANSIBLE_DEBUG", "false"), strict=True)
    except TypeError:
        raise ConfigError("ansible-debug-not-supported") from None
    if debug_enabled:
        raise ConfigError("ansible-debug-not-supported")
    import fleet_inspection
    if not alias or not fleet_inspection.SAFE_NAME.fullmatch(alias):
        raise ConfigError("exact-single-host-required")
    if any(os.environ.get(name) for name in (
            "SKIP_PRECHECK", "ANSIBLE_TAGS", "ANSIBLE_RUN_TAGS", "ANSIBLE_SKIP_TAGS")):
        raise ConfigError("safety-bypass-not-supported")
    root = Path(__file__).resolve().parents[1]
    environment = execution_environment(root)
    environment.update(clean_source(root, environment))
    with tempfile.TemporaryDirectory(prefix="vpn-backup-configure-") as directory:
        private = Path(directory).resolve()
        ansible_home = private / "ansible-home"
        ansible_home.mkdir(mode=0o700)
        environment["ANSIBLE_HOME"] = str(ansible_home)
        host, cohorts, selected = prepare_inventory(inventory, alias, private)
        snapshot_file = private / "secrets.yaml"
        private_file(snapshot_file, materialized_bytes(secrets))
        environment.update(VPN_SECRETS_FILE=str(snapshot_file), BACKUP_CONFIGURE_HOST=alias,
                           BACKUP_CONFIGURATION_VARS_FILES=json.dumps(canonical_variables(root, cohorts)))
        commands = ([sys.executable, str(root / "scripts/validate-secrets.py"), str(snapshot_file), "--strict"],
                    [sys.executable, str(root / "scripts/spot-check-secrets.py")],
                    [str(root / "scripts/check-certs.sh")])
        for command in commands:
            result = subprocess.run(command, env=environment, capture_output=True, timeout=120)
            if result.returncode:
                raise ConfigError("canonical-secrets-precheck-failed")
        command = ["ansible-playbook", str(root / "ansible/playbooks/backup-configure.yml"),
                   "-i", str(selected), "--limit", alias]
        extra_vars = os.environ.get("BACKUP_CONFIGURE_EXTRA_VARS_FILE", "")
        overrides = {}
        if extra_vars:
            extra_snapshot = snapshot_file.parent / "extra-vars.yaml"
            private_file(extra_snapshot, materialized_bytes(extra_vars))
            result = subprocess.run(
                [sys.executable, str(root / "scripts/validate-ansible-extra-vars.py"), str(extra_snapshot)],
                env=environment, capture_output=True, timeout=30,
            )
            if result.returncode:
                raise ConfigError("canonical-extra-vars-precheck-failed")
            import yaml
            overrides = yaml.safe_load(extra_snapshot.read_bytes())
            command += ["--extra-vars", "@" + str(extra_snapshot)]
        command += ["--extra-vars", json.dumps(transport_variables(host, overrides, Path.home() / ".ssh/known_hosts"))]
        result = subprocess.run(command, cwd=private, env=environment, capture_output=True, timeout=600, check=False)
        if result.returncode:
            raise ConfigError("configuration-playbook-failed-keep-timers-stopped")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("claim", "validate", "publish", "release", "controller"))
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args()
    def interrupted(_signum, _frame):
        raise ConfigError("configuration-interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.action == "controller" and not args.arguments:
            controller(os.environ.get("BACKUP_CONFIGURE_INVENTORY", ""),
                       os.environ.get("BACKUP_CONFIGURE_HOST", ""),
                       os.environ.get("BACKUP_CONFIGURE_SECRETS_FILE", ""))
            result = {"configuration_prechecks": "passed"}
        elif args.action == "claim" and not args.arguments:
            result = {"token": claim()}
        elif args.action in ("validate", "publish", "release") and len(args.arguments) == 1:
            value = {"validate": validate, "publish": publish, "release": release}[args.action](*args.arguments)
            result = {"changed": value is True, "configuration_only": True}
        else:
            raise ConfigError("invalid-invocation")
        print(json.dumps(result))
        return 0
    except Exception as exc:
        category = str(exc) if isinstance(exc, ConfigError) else "configuration-check-failed"
        print(json.dumps({"error": category, "keep_timers_stopped": True}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
