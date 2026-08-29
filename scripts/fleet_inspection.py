"""Bounded passive collection. Executed over SSH stdin, never installed remotely."""
from __future__ import annotations

import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import stat
import subprocess
import time

LIMIT = 65536
SERVICES = (
    "ssh.service", "xray.service", "nginx.service", "hysteria-server.service",
    "awg-quick.target", "tailscaled.service",
    "vpn-backup.service", "vpn-backup.timer", "vpn-watchdog.service", "vpn-watchdog.timer",
)
PROPERTIES = ("LoadState", "ActiveState", "SubState", "Result", "ExecMainStatus", "ExecMainExitTimestamp")
SAFE_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,252}\Z")
AWG_UNIT = re.compile(r"awg-quick@[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,14}\.service\Z")
MANIFEST = "/var/lib/ripdpi-vpn-deploy/manifest.json"
RESTORE = "/var/lib/vpn-backup/restore-drill-last-success.json"


class InspectionError(Exception):
    """Only categorical messages from this class may reach operator output."""


def bounded_command(command, *, timeout=5, limit=LIMIT, input_bytes=b"", environment=None):
    """Bound stdin, both output streams, and our fixed command's lifetime."""
    if len(input_bytes) > LIMIT * 2:
        raise InspectionError("input-limit")
    env = environment if environment is not None else {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=env, start_new_session=True)
    except OSError:
        raise InspectionError("command-unavailable") from None
    output = bytearray()
    total = 0
    position = 0
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            if input_bytes:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise InspectionError("timeout")
                for key, events in selector.select(remaining):
                    if events & selectors.EVENT_WRITE:
                        try:
                            position += os.write(key.fd, input_bytes[position:position + 4096])
                        except BrokenPipeError:
                            raise InspectionError("command-failed") from None
                        if position == len(input_bytes):
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                    else:
                        chunk = os.read(key.fd, 4096)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(chunk)
                        if total > limit:
                            raise InspectionError("output-limit")
                        if key.fileobj is process.stdout:
                            output.extend(chunk)
            try:
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise InspectionError("timeout") from None
            if code:
                raise InspectionError("command-failed")
            return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def _check_node(fd, owner, directory=False):
    info = os.fstat(fd)
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if info.st_uid != owner or info.st_mode & 0o022 or not expected(info.st_mode):
        raise InspectionError("unsafe-file")
    if not directory and info.st_size > LIMIT:
        raise InspectionError("file-limit")


def read_beneath(root_fd, relative_path, *, owner=0):
    """Walk trusted descriptors without following links or blocking on a FIFO."""
    parts = relative_path.split("/")
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise InspectionError("unsafe-path")
    fd = os.dup(root_fd)
    try:
        _check_node(fd, owner, directory=True)
        for index, part in enumerate(parts):
            directory = index < len(parts) - 1
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            _check_node(fd, owner, directory=directory)
        chunks = bytearray()
        while True:
            chunk = os.read(fd, min(4096, LIMIT + 1 - len(chunks)))
            if not chunk:
                return bytes(chunks)
            chunks.extend(chunk)
            if len(chunks) > LIMIT:
                raise InspectionError("file-limit")
    except OSError:
        raise InspectionError("unreadable-file") from None
    finally:
        os.close(fd)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InspectionError("duplicate-field")
        result[key] = value
    return result


def decode_json(raw):
    try:
        result = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError):
        raise InspectionError("malformed-json") from None
    if not isinstance(result, dict):
        raise InspectionError("malformed-json")
    return result


def read_host_json(path):
    if path not in (MANIFEST, RESTORE):
        raise InspectionError("unsupported-path")
    root_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        return decode_json(read_beneath(root_fd, path[1:]))
    finally:
        os.close(root_fd)


def parse_time(value):
    if not isinstance(value, str) or len(value) > 40:
        raise InspectionError("invalid-time")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(dt.timezone.utc)
    except (ValueError, OverflowError):
        raise InspectionError("invalid-time") from None


def timestamp(value):
    return value.isoformat().replace("+00:00", "Z")


def manifest_evidence(raw):
    if (not isinstance(raw, dict) or type(raw.get("schema_version")) is not int
            or raw["schema_version"] != 2
            or not isinstance(raw.get("source_revision"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", raw["source_revision"])
            or not isinstance(raw.get("deployable_digest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", raw["deployable_digest"])):
        return {"status": "unknown"}
    return {"status": "observed", **{k: raw[k] for k in ("schema_version", "source_revision", "deployable_digest")}}


def restore_evidence(raw, now):
    try:
        if (not isinstance(raw, dict) or type(raw.get("version")) is not int or raw["version"] != 1
                or raw.get("repository_source") not in ("local", "remote")):
            raise InspectionError("invalid-restore")
        snapshot = parse_time(raw.get("snapshot_time"))
        verified = parse_time(raw.get("verified_at"))
        if max(snapshot, verified) > now or snapshot > verified:
            raise InspectionError("invalid-time")
        return {"status": "stale" if now - verified > dt.timedelta(days=35) else "observed",
                "version": 1, "repository_source": raw["repository_source"],
                "snapshot_time": timestamp(snapshot), "verified_at": timestamp(verified),
                "snapshot_freshness": "stale" if now - snapshot > dt.timedelta(hours=36) else "observed"}
    except InspectionError:
        return {"status": "unknown"}


def _address(value):
    if value == "*":
        return value
    try:
        # Interface scopes are not needed for this report and are not emitted.
        return str(ipaddress.ip_address(value.split("%", 1)[0]))
    except ValueError:
        raise InspectionError("invalid-address") from None


def parse_listeners(raw):
    result = []
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) != 6 or fields[0] not in ("tcp", "udp"):
            raise InspectionError("malformed-listeners")
        try:
            address, port_text = fields[4].rsplit(":", 1)
            port = int(port_text)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            raise InspectionError("malformed-listeners") from None
        result.append({"protocol": fields[0], "address": _address(address.strip("[]")), "port": port})
    return result


def service_evidence(raw):
    values = {}
    for line in raw.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in PROPERTIES or key in values:
            raise InspectionError("malformed-service")
        values[key] = value
    if not {"LoadState", "ActiveState", "SubState"} <= values.keys():
        raise InspectionError("malformed-service")
    for optional in ("Result", "ExecMainStatus", "ExecMainExitTimestamp"):
        values.setdefault(optional, "")
    enums = {
        "LoadState": {"loaded", "not-found", "masked", "error", "bad-setting", "merged", "stub"},
        "ActiveState": {"active", "inactive", "failed", "activating", "deactivating", "reloading", "maintenance", "refreshing"},
        "SubState": {"running", "dead", "failed", "exited", "waiting", "elapsed", "listening", "start", "start-pre", "start-post", "stop", "stop-sigterm", "stop-sigkill", "stop-post", "auto-restart", "auto-restart-queued", "reload", "cleaning", "final-sigterm", "final-sigkill", "condition"},
        "Result": {"", "success", "exit-code", "signal", "core-dump", "timeout", "watchdog", "start-limit-hit", "resources", "protocol", "oom-kill", "exec-condition", "assert", "dependency"},
    }
    result = {"status": "observed"}
    for source, dest in (("LoadState", "load_state"), ("ActiveState", "active_state"), ("SubState", "sub_state"), ("Result", "result")):
        result[dest] = values[source] if values[source] in enums[source] else "unknown"
    if any(result[field] == "unknown" for field in ("load_state", "active_state", "sub_state", "result")):
        return {"status": "unknown"}
    try:
        code = int(values["ExecMainStatus"])
        if not 0 <= code <= 255:
            raise ValueError
        result["exec_main_status"] = code
    except ValueError:
        result["exec_main_status"] = None
    # systemd's human timestamp is parsed, never copied as free-form output.
    try:
        parsed = dt.datetime.strptime(values["ExecMainExitTimestamp"], "%a %Y-%m-%d %H:%M:%S UTC")
        result["exec_main_exit_timestamp"] = timestamp(parsed.replace(tzinfo=dt.timezone.utc))
    except ValueError:
        result["exec_main_exit_timestamp"] = None
    return result


def collect():
    now = dt.datetime.now(dt.timezone.utc)
    result = {"schema_version": 1, "observed_at": timestamp(now), "services": {},
              "manifest": {"status": "unknown"}, "listeners": {"status": "unknown"},
              "backup": {"latest_snapshot": {"status": "unknown"}, "restore": {"status": "unknown"}}}
    instances = []
    discovery_failed = False
    try:
        raw = bounded_command(["/usr/bin/systemctl", "show", "--no-pager", "--property=Wants", "awg-quick.target"], timeout=1).decode("utf-8").strip()
        if not raw.startswith("Wants="):
            raise InspectionError("malformed-awg-target")
        instances = raw[6:].split()
        if len(instances) > 16 or len(instances) != len(set(instances)) or any(not AWG_UNIT.fullmatch(u) for u in instances):
            raise InspectionError("malformed-awg-target")
    except (InspectionError, UnicodeError):
        discovery_failed = True
        instances = []
    for unit in (*SERVICES, *sorted(instances)):
        try:
            raw = bounded_command(["/usr/bin/systemctl", "show", "--no-pager", "--property=" + ",".join(PROPERTIES), unit], timeout=1)
            result["services"][unit] = service_evidence(raw.decode("utf-8"))
        except (InspectionError, UnicodeError):
            result["services"][unit] = {"status": "unknown"}
    if discovery_failed:
        result["services"]["awg-quick.target"] = {"status": "unknown"}
    try:
        raw = bounded_command(["/usr/bin/ss", "-H", "-lntu"], timeout=2)
        result["listeners"] = {"status": "observed", "items": parse_listeners(raw.decode("utf-8"))}
    except (InspectionError, UnicodeError):
        result["listeners"] = {"status": "unknown"}
    try:
        result["manifest"] = manifest_evidence(read_host_json(MANIFEST))
    except InspectionError:
        result["manifest"] = {"status": "unknown"}
    try:
        result["backup"]["restore"] = restore_evidence(read_host_json(RESTORE), now)
    except InspectionError:
        result["backup"]["restore"] = {"status": "unknown"}
    return result


def _connection_name(value):
    if not isinstance(value, str) or not value or value.startswith("-"):
        raise InspectionError("invalid-host")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        if not SAFE_NAME.fullmatch(value):
            raise InspectionError("invalid-host") from None
        return value


def _open_local_file(path, private=False):
    candidate = Path(path).expanduser().absolute()
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for index, part in enumerate(candidate.parts[1:]):
            if part in (".", ".."):
                raise InspectionError("unsafe-local-path")
            directory = index < len(candidate.parts) - 2
            child = os.open(part, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_DIRECTORY if directory else 0), dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if directory:
                sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
                if info.st_uid not in (0, os.getuid()) or (info.st_mode & 0o022 and not sticky_root):
                    raise InspectionError("unsafe-local-parent")
            elif (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                  or info.st_mode & (0o077 if private else 0o022)):
                raise InspectionError("unsafe-local-file")
        return fd
    except (InspectionError, OSError) as exc:
        os.close(fd)
        raise InspectionError(str(exc) if isinstance(exc, InspectionError) else "unreadable-local-file") from None


def _local_file(path, private=False):
    if any(char.isspace() or char in "%\"'\\" for char in str(path)):
        raise InspectionError("unsafe-ssh-path")
    fd = _open_local_file(path, private)
    os.close(fd)
    return str(Path(path).expanduser().absolute())


def select_hosts(inventory_path, selected):
    if not selected or len(selected) != len(set(selected)) or any(not SAFE_NAME.fullmatch(s) or s == "all" for s in selected):
        raise InspectionError("explicit-host-subset-required")
    try:
        with os.fdopen(_open_local_file(inventory_path), "rb") as stream:
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise InspectionError("inventory-limit")
        lines = raw.decode("utf-8").splitlines()
    except (OSError, UnicodeError):
        raise InspectionError("unreadable-inventory") from None
    hosts, global_vars = {}, {}
    section = ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if section != "vpn:vars" and not SAFE_NAME.fullmatch(section):
                raise InspectionError("unsupported-inventory-section")
            continue
        try:
            words = shlex.split(line, comments=True)
        except ValueError:
            raise InspectionError("malformed-inventory") from None
        if section == "vpn:vars":
            target, assignments = global_vars, words
        elif section == "vpn":
            if not words or not SAFE_NAME.fullmatch(words[0]) or words[0] in hosts:
                raise InspectionError("duplicate-or-invalid-host")
            target = hosts.setdefault(words[0], {})
            assignments = words[1:]
        elif section.startswith("vpn-") and len(words) == 1 and words[0] in hosts:
            continue
        else:
            raise InspectionError("unsupported-inventory")
        for assignment in assignments:
            key, separator, value = assignment.partition("=")
            if not separator or not value or key in target or not re.fullmatch(r"[a-z_][a-z_0-9]*", key):
                raise InspectionError("ambiguous-inventory-variable")
            if key.startswith("ansible_") and key not in ("ansible_host", "ansible_user", "ansible_port", "ansible_ssh_private_key_file", "ansible_python_interpreter"):
                raise InspectionError("unsupported-connection-option")
            target[key] = value
    result = []
    for name in selected:
        if name not in hosts:
            raise InspectionError("host-not-found")
        if global_vars.keys() & hosts[name].keys():
            raise InspectionError("ambiguous-inventory-variable")
        values = {**global_vars, **hosts[name]}
        try:
            address = _connection_name(values["ansible_host"])
            user = values["ansible_user"]
            port = int(values["ansible_port"])
            if not re.fullmatch(r"[a-z_][a-z_0-9-]{0,31}", user) or not 1 <= port <= 65535:
                raise InspectionError("invalid-connection")
            key = _local_file(values["ansible_ssh_private_key_file"], private=True)
        except (KeyError, ValueError):
            raise InspectionError("missing-or-invalid-connection") from None
        override = "inspection_transport_host" in values
        if override != ("inspection_host_key_alias" in values):
            raise InspectionError("paired-transport-identity-required")
        result.append({"name": name, "address": address, "port": port, "user": user, "key": key,
                       "transport": _connection_name(values.get("inspection_transport_host", address)),
                       "alias": _connection_name(values.get("inspection_host_key_alias", address))})
    for key in ("alias", "transport"):
        identities = {(host[key].lower(), host["port"]) for host in result}
        if len(identities) != len(result):
            raise InspectionError("duplicate-host-identity")
    return result


def _strict_connection_options(host, known_hosts_path):
    known_hosts = _local_file(known_hosts_path)
    alias = host["alias"] if host["port"] == 22 else "[" + host["alias"] + "]:" + str(host["port"])
    return ["BatchMode=yes", "StrictHostKeyChecking=yes", "UpdateHostKeys=no", "IdentitiesOnly=yes",
               "ControlPath=none", "ControlMaster=no", "ControlPersist=no", "ProxyCommand=none", "ProxyJump=none",
               "ClearAllForwardings=yes", "PermitLocalCommand=no", "RemoteCommand=none", "IdentityAgent=none",
               "ForwardAgent=no", "ForwardX11=no", "GlobalKnownHostsFile=/dev/null", "VerifyHostKeyDNS=no",
               "RequestTTY=no", "ConnectTimeout=10", "ConnectionAttempts=1", "LogLevel=ERROR",
               "PasswordAuthentication=no", "KbdInteractiveAuthentication=no", "GSSAPIAuthentication=no",
               "PreferredAuthentications=publickey",
               "UserKnownHostsFile=" + known_hosts, "HostKeyAlias=" + alias]


def _with_options(program, options):
    command = [program, "-F", "/dev/null"]
    for option in options:
        command.extend(["-o", option])
    return command


def ssh_command(host, known_hosts_path):
    options = _strict_connection_options(host, known_hosts_path)
    command = _with_options("ssh", options)
    return command + ["-i", host["key"], "-l", host["user"], "-p", str(host["port"]),
                      host["transport"], "sudo -n /usr/bin/python3 -I -B -S -"]


def sftp_command(host, known_hosts_path):
    options = [*_strict_connection_options(host, known_hosts_path), "User=" + host["user"]]
    return _with_options("sftp", options) + ["-b", "-", "-i", host["key"], "-P", str(host["port"]),
                                              host["transport"]]


def _keys(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise InspectionError("malformed-report")


def validate_report(raw, now):
    """Validate every remote field before it crosses the controller's output boundary."""
    try:
        _keys(raw, ("schema_version", "observed_at", "services", "manifest", "listeners", "backup"))
        if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise InspectionError("unsupported-report")
        observed = parse_time(raw["observed_at"])
        if observed > now or timestamp(observed) != raw["observed_at"]:
            raise InspectionError("invalid-time")
        if not isinstance(raw["services"], dict) or not set(SERVICES) <= raw["services"].keys() or len(raw["services"]) > len(SERVICES) + 16:
            raise InspectionError("malformed-services")
        for unit, evidence in raw["services"].items():
            if unit not in SERVICES and not AWG_UNIT.fullmatch(unit):
                raise InspectionError("unsupported-service")
            if evidence == {"status": "unknown"}:
                continue
            _keys(evidence, ("status", "load_state", "active_state", "sub_state", "result", "exec_main_status", "exec_main_exit_timestamp"))
            if evidence["status"] != "observed":
                raise InspectionError("malformed-service")
            fields = []
            for source, dest in (("LoadState", "load_state"), ("ActiveState", "active_state"), ("SubState", "sub_state"), ("Result", "result")):
                value = evidence[dest]
                if not isinstance(value, str) or len(value) > 32 or "\n" in value:
                    raise InspectionError("malformed-service")
                fields.append(source + "=" + value)
            code = evidence["exec_main_status"]
            if code is not None and (type(code) is not int or not 0 <= code <= 255):
                raise InspectionError("malformed-service")
            fields.append("ExecMainStatus=" + (str(code) if code is not None else ""))
            expected = service_evidence("\n".join(fields))
            exit_time = evidence["exec_main_exit_timestamp"]
            if exit_time is not None:
                if parse_time(exit_time) > observed:
                    raise InspectionError("invalid-time")
                expected["exec_main_exit_timestamp"] = timestamp(parse_time(exit_time))
            if expected != evidence:
                raise InspectionError("malformed-service")
        if manifest_evidence(raw["manifest"]) != raw["manifest"]:
            raise InspectionError("malformed-manifest")
        _keys(raw["backup"], ("latest_snapshot", "restore"))
        if raw["backup"]["latest_snapshot"] != {"status": "unknown"}:
            raise InspectionError("unsupported-backup-evidence")
        restore = raw["backup"]["restore"]
        if restore_evidence(restore, observed) != restore:
            raise InspectionError("malformed-restore")
        listeners = raw["listeners"]
        if listeners != {"status": "unknown"}:
            _keys(listeners, ("status", "items"))
            if listeners["status"] != "observed" or not isinstance(listeners["items"], list) or len(listeners["items"]) > 512:
                raise InspectionError("malformed-listeners")
            for item in listeners["items"]:
                _keys(item, ("protocol", "address", "port"))
                if (item["protocol"] not in ("tcp", "udp") or type(item["port"]) is not int
                        or not 1 <= item["port"] <= 65535 or _address(item["address"]) != item["address"]):
                    raise InspectionError("malformed-listeners")
        return raw
    except (TypeError, ValueError, KeyError, AttributeError):
        raise InspectionError("malformed-report") from None


def observation_status(report, now):
    """Observation completeness, never a client/protocol health verdict."""
    if any(s.get("active_state") == "failed" for s in report["services"].values()):
        return "error"
    evidence = [*report["services"].values(), report["manifest"], report["listeners"], report["backup"]["restore"]]
    if any(item["status"] == "unknown" for item in evidence):
        return "unknown"
    if (now - parse_time(report["observed_at"]) > dt.timedelta(minutes=5)
            or any(item["status"] == "stale" for item in evidence)
            or report["backup"]["restore"].get("snapshot_freshness") == "stale"):
        return "stale"
    return "observed"


if __name__ == "__main__":
    print(json.dumps(collect(), sort_keys=True))
