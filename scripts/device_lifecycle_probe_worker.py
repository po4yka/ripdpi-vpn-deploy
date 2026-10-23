#!/usr/bin/env python3
"""Bounded stdin-only native credential probes on the exact managed Linux node.

The controller sends this source through its pinned management channel. Nothing
is installed. Only categorical witnesses leave this worker; private profiles and
native diagnostics live in a mode-0700 temporary directory and are removed.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import ipaddress
import json
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

MAX_REQUEST = 2 * 1024 * 1024
MAX_BODY = 1024 * 1024
MAX_RUNTIME_SECONDS = 180
ENGINES = {"xray", "hysteria", "snell", "awg", "naive"}
BINARIES = {"xray": "/usr/local/bin/xray", "hysteria": "/usr/local/bin/hysteria",
            "snell": "/usr/local/bin/sing-box-snell", "awg-go": "/usr/local/bin/amneziawg-go",
            "awg": "/usr/bin/awg", "awg-quick": "/usr/bin/awg-quick",
            "curl": "/usr/bin/curl", "ip": "/usr/sbin/ip", "systemctl": "/usr/bin/systemctl"}


class ProbeError(ValueError):
    """Fixed categorical reason, never subprocess diagnostics."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProbeError("invalid-request")
        result[key] = value
    return result


def validate_request(value):
    if (not isinstance(value, dict) or set(value) != {"schema_version", "mode", "profiles", "control", "timeout_seconds"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["mode"] not in {"accept", "deny"}
            or type(value["timeout_seconds"]) is not int or not 1 <= value["timeout_seconds"] <= 30
            or not isinstance(value["profiles"], list) or not 1 <= len(value["profiles"]) <= 64):
        raise ProbeError("invalid-request")
    control = value["control"]
    if (not isinstance(control, dict) or set(control) != {"url", "status", "body_sha256"}
            or type(control["status"]) is not int or not 200 <= control["status"] <= 299
            or not isinstance(control["body_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", control["body_sha256"])):
        raise ProbeError("invalid-control")
    try:
        parsed = urlsplit(control["url"])
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.fragment or any(ord(c) < 33 for c in control["url"])):
            raise ValueError
        _ = parsed.port
    except (ValueError, TypeError):
        raise ProbeError("invalid-control") from None
    identifiers = set()
    for profile in value["profiles"]:
        if (not isinstance(profile, dict) or set(profile) != {"id", "engine", "config", "witness"}
                or profile["engine"] not in ENGINES or not isinstance(profile["id"], str)
                or not re.fullmatch(r"[a-z]+-[1-9][0-9]{0,2}", profile["id"]) or profile["id"] in identifiers
                or not isinstance(profile["config"], dict) or not isinstance(profile["witness"], dict)
                or set(profile["witness"]) != {"kind", "credential", "instance", "config_path", "unit"}
                or not isinstance(profile["witness"]["credential"], str) or not profile["witness"]["credential"]
                or len(profile["witness"]["credential"]) > 1024):
            raise ProbeError("invalid-profile")
        expected = {"xray": "uuid", "hysteria": "username", "snell": "userkey", "awg": "peer", "naive": "basic"}
        if profile["witness"]["kind"] != expected[profile["engine"]]:
            raise ProbeError("invalid-profile")
        instance = profile["witness"]["instance"]
        path, unit = profile["witness"]["config_path"], profile["witness"]["unit"]
        if (not isinstance(path, str) or len(path) > 512 or not re.fullmatch(r"/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+", path)
                or any(part in {".", ".."} for part in path.split("/"))
                or not isinstance(unit, str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}\.service", unit)):
            raise ProbeError("invalid-runtime-witness")
        if profile["engine"] == "awg":
            if not isinstance(instance, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,14}", instance):
                raise ProbeError("invalid-profile")
        elif instance is not None:
            raise ProbeError("invalid-profile")
        identifiers.add(profile["id"])
    return value


def _private(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
    return str(path)


def _stop(process):
    if process is None:
        return True
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        # The owned process group already exited before the signal.
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            # The owned process group already exited before the signal.
            pass
        process.wait(timeout=2)
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return True
    return False


class Runtime:
    """Canonical runtime adapter. Test overrides stay outside the stdin API."""
    def __init__(self, *, binaries=None, ca_file=None, namespace_root=Path("/etc/netns")):
        self.binaries = dict(BINARIES if binaries is None else binaries)
        self.ca_file = ca_file
        self.namespace_root = namespace_root
        self.deadline = None
        self.environment = {key: value for key, value in os.environ.items()
                            if key in {"PATH", "LANG", "LC_ALL", "TZ"}}
        self.environment.update(LC_ALL="C", LOG_LEVEL="silent")
        self.environment["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        if ca_file:
            self.environment["SSL_CERT_FILE"] = str(ca_file)

    def binary(self, name):
        path = Path(self.binaries[name])
        if path.lstat().st_uid != os.geteuid():
            raise ProbeError("unsafe-runtime-tool")
        for parent in (*path.parents, path.resolve(), *path.resolve().parents):
            info = parent.stat()
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise ProbeError("unsafe-runtime-tool")
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ProbeError("missing-runtime-tool")
        return str(path)

    def command(self, args, *, data=None, timeout=5):
        # Bounded output is kept in private files, never in the result or argv.
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                raise ProbeError("probe-budget-exhausted")
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=output, stderr=errors,
                                       env=self.environment, start_new_session=True)
            try:
                process.communicate(data, timeout=timeout)
                output.seek(0)
                value = output.read(MAX_REQUEST + 1)
                if len(value) > MAX_REQUEST:
                    raise ProbeError("runtime-output-limit")
                return process.returncode, value
            except subprocess.TimeoutExpired:
                raise ProbeError("runtime-command-timeout") from None
            finally:
                if not _stop(process):
                    raise ProbeError("cleanup-failed")

    @contextmanager
    def budget(self):
        previous = self.deadline
        self.deadline = min(previous if previous is not None else float("inf"), time.monotonic() + MAX_RUNTIME_SECONDS)
        try:
            yield
        finally:
            self.deadline = previous

    def cleanup_command(self, args):
        # Exhausted traffic time never removes the independent cleanup budget.
        previous, self.deadline = self.deadline, None
        try:
            return self.command(args, timeout=5)
        finally:
            self.deadline = previous

    def witness(self, profile):
        engine, identity = profile["engine"], profile["witness"]["credential"]
        unit = profile["witness"]["unit"]
        code, service = self.command([self.binary("systemctl"), "show", unit,
                                      "--property=ActiveState,SubState,MainPID,LoadState"])
        properties = dict(line.split("=", 1) for line in service.decode("ascii").splitlines() if "=" in line)
        active = (code == 0 and properties.get("ActiveState") == "active"
                  and properties.get("SubState") == "running" and properties.get("MainPID", "0").isdigit()
                  and int(properties["MainPID"]) > 0)
        if engine == "awg":
            active = code == 0 and properties.get("ActiveState") == "active" and properties.get("SubState") in {"running", "exited"}
        inactive = (properties.get("ActiveState") == "inactive" and properties.get("MainPID", "0") == "0"
                    and properties.get("LoadState") in {"loaded", "not-found"})
        if engine == "awg":
            instance = profile["witness"]["instance"]
            code, output = self.command([self.binary("awg"), "show", instance, "peers"])
            if code:
                absent, _ = self.command([self.binary("ip"), "link", "show", instance])
                authority = Path(profile["witness"]["config_path"])
                if not inactive or absent != 1 or authority.exists() or authority.is_symlink():
                    raise ProbeError("runtime-authority-unavailable")
                output = b""
            else:
                link_code, link = self.command([self.binary("ip"), "-j", "link", "show", instance])
                links = json.loads(link)
                active = active and link_code == 0 and len(links) == 1 and "UP" in links[0]["flags"]
                port_code, port = self.command([self.binary("awg"), "show", instance, "listen-port"])
                key_code, server_key = self.command([self.binary("awg"), "show", instance, "public-key"])
                fields = dict(line.partition("=")[::2] for line in profile["config"]["text"].splitlines() if "=" in line)
                fields = {name.strip(): value.strip() for name, value in fields.items()}
                active = (active and port_code == key_code == 0
                          and port.strip().decode("ascii") == fields["Endpoint"].rsplit(":", 1)[1]
                          and server_key.strip().decode("ascii") == fields["PublicKey"])
            peers = output.decode("ascii").splitlines()
            if any(not re.fullmatch(r"[A-Za-z0-9+/]{43}=", peer) for peer in peers):
                raise ProbeError("runtime-authority-invalid")
            present = identity in peers
            token = hashlib.sha256(output).hexdigest()
        else:
            filename = profile["witness"]["config_path"]
            path = Path(filename)
            if not path.exists() and not path.is_symlink() and inactive:
                return {"peer_absent": True, "runtime_healthy": True, "inactive_confirmed": True,
                        "token": "absent", "unit_token": hashlib.sha256(service).hexdigest()}
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022 or info.st_size > MAX_REQUEST:
                raise ProbeError("unsafe-runtime-authority")
            content = path.read_bytes()
            if len(content) > MAX_REQUEST:
                raise ProbeError("runtime-authority-limit")
            token = hashlib.sha256(content).hexdigest()
            if engine == "hysteria":
                # The canonical template emits JSON-quoted scalar entries under
                # this exact YAML mapping. Reject unknown syntax, never infer an
                # empty map from a parser error or a missing auth block.
                lines = content.decode().splitlines()
                start = lines.index("auth:")
                if lines[start + 1:start + 3] != ["  type: userpass", "  userpass:"]:
                    raise ProbeError("runtime-authority-invalid")
                names = []
                for line in lines[start + 3:]:
                    if not line or line.startswith("#"):
                        continue
                    if not line.startswith("    "):
                        break
                    key, end = json.JSONDecoder().raw_decode(line[4:])
                    tail = line[4 + end:]
                    if not isinstance(key, str) or not tail.startswith(": "):
                        raise ProbeError("runtime-authority-invalid")
                    json.loads(tail[2:])
                    names.append(key)
                present = identity in names
            else:
                document = json.loads(content, object_pairs_hook=_unique)
                if engine == "xray":
                    inbounds = document["inbounds"]
                    present = any(user.get("id") == identity for inbound in inbounds
                                  for user in inbound.get("settings", {}).get("clients", []))
                elif engine == "snell":
                    present = any(user.get("userkey") == identity for inbound in document["inbounds"]
                                  for user in inbound.get("users", []))
                else:
                    encoded = base64.b64encode(base64.b64encode(identity.encode())).decode()
                    def credentials(value):
                        if isinstance(value, dict):
                            if value.get("handler") == "forward_proxy":
                                yield from value.get("auth_credentials", [])
                            for child in value.values():
                                yield from credentials(child)
                        elif isinstance(value, list):
                            for child in value:
                                yield from credentials(child)
                    # Require the actual server tree even when the last user's
                    # forward_proxy handler has been removed by the role.
                    if not isinstance(document["apps"]["http"]["servers"], dict):
                        raise ProbeError("runtime-authority-invalid")
                    present = encoded in credentials(document)
        return {"peer_absent": not present, "runtime_healthy": active or (inactive and engine == "awg"),
                "inactive_confirmed": inactive, "token": token,
                "unit_token": hashlib.sha256(service).hexdigest()}

    def http(self, control, timeout, directory, *, proxy=None, namespace=None, naive=None):
        output = directory / (uuid4().hex + ".body")
        args = [self.binary("curl"), "--disable", "--silent", "--show-error", "--http1.1", "--proto", "=https",
                "--max-time", str(timeout), "--connect-timeout", str(timeout), "--max-filesize", str(MAX_BODY),
                "--output", str(output), "--write-out", "%{http_code}", "--noproxy", "" if proxy or naive else "*"]
        if self.ca_file:
            args += ["--cacert", str(self.ca_file), "--proxy-cacert", str(self.ca_file)]
        data = None
        if proxy:
            args += ["--proxy", "socks5h://127.0.0.1:" + str(proxy)]
        if naive:
            # curl config quoting prevents newline/option injection and keeps
            # Basic credentials out of the child argv and process listings.
            auth = naive["username"] + ":" + naive["password"]
            if any(ord(char) < 32 for char in auth):
                raise ProbeError("invalid-profile")
            escaped = auth.replace("\\", "\\\\").replace('"', '\\"')
            data = ('proxy-user = "' + escaped + '"\n').encode()
            args += ["--config", "-", "--proxy-basic", "--proxytunnel", "--proxy", f"https://{naive['server_name']}:{naive['port']}",
                     "--resolve", f"{naive['server_name']}:{naive['port']}:{naive['address']}"]
        args += [control["url"]]
        if namespace:
            args = [self.binary("ip"), "netns", "exec", namespace, *args]
        started = time.monotonic()
        try:
            code, status = self.command(args, data=data, timeout=timeout + 2)
            body = output.read_bytes() if output.exists() else b""
            if len(body) > MAX_BODY:
                raise ProbeError("response-limit")
            matched = code == 0 and status == str(control["status"]).encode() and hashlib.sha256(body).hexdigest() == control["body_sha256"]
            return {"accepted": matched, "exit": code, "elapsed": time.monotonic() - started}
        finally:
            output.unlink(missing_ok=True)

    def stream(self, profile, control, timeout, directory):
        if profile["engine"] == "naive":
            return {**self.http(control, timeout, directory, naive=profile["config"]), "setup_ok": True, "cleanup_ok": True}
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        config = copy.deepcopy(profile["config"])
        engine = profile["engine"]
        if engine == "xray":
            config["inbounds"] = [{"listen": "127.0.0.1", "port": port, "protocol": "socks", "settings": {"auth": "noauth", "udp": False}}]
        elif engine == "snell":
            config["inbounds"] = [{"listen": "127.0.0.1", "listen_port": port, "type": "socks"}]
        else:
            config["socks5"] = {"listen": "127.0.0.1:" + str(port)}
            config["lazy"] = True
        filename = _private(directory / (uuid4().hex + ".json"), json.dumps(config).encode())
        command = [self.binary(engine), "client" if engine == "hysteria" else "run",
                   "-config" if engine == "xray" else "-c", filename]
        process, result = None, None
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, env=self.environment, start_new_session=True)
            deadline = time.monotonic() + min(timeout, 5)
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise ProbeError("client-start-failed")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.02)
            else:
                raise ProbeError("client-start-timeout")
            result = self.http(control, timeout, directory, proxy=port)
            if process.poll() is not None:
                raise ProbeError("client-exited")
        finally:
            cleaned = _stop(process)
            Path(filename).unlink()
        if not cleaned:
            raise ProbeError("cleanup-failed")
        return {**result, "setup_ok": True, "cleanup_ok": True}

    def awg(self, profile, control, timeout, directory):
        """Create the UDP owner in the host, move only its TUN into an owned netns."""
        ip, awg, quick, go = (self.binary(name) for name in ("ip", "awg", "awg-quick", "awg-go"))
        config = profile["config"]
        if (set(config) != {"text", "addresses", "dns", "mtu"} or not isinstance(config["text"], str)
                or type(config["mtu"]) is not int or not 576 <= config["mtu"] <= 9000
                or not isinstance(config["addresses"], list) or not 1 <= len(config["addresses"]) <= 2
                or not isinstance(config["dns"], list) or not 1 <= len(config["dns"]) <= 3):
            raise ProbeError("invalid-awg-profile")
        addresses = [ipaddress.ip_interface(address) for address in config["addresses"]]
        dns = [str(ipaddress.ip_address(address)) for address in config["dns"]]
        if len({address.version for address in addresses}) != len(addresses):
            raise ProbeError("invalid-awg-profile")
        namespace, interface = "devprobe-" + uuid4().hex, "dp" + uuid4().hex[:11]
        resolver = self.namespace_root / namespace
        marker = Path("/run/netns") / namespace
        process, attempted, location, resolver_created = None, False, None, False
        filename = _private(directory / (interface + ".conf"), config["text"].encode())

        def checked(args, reason, *, data=None):
            code, output = self.command(args, data=data)
            if code:
                raise ProbeError(reason)
            return output

        try:
            code, _ = self.command([ip, "link", "show", interface])
            if code != 1 or marker.exists() or marker.is_symlink():
                raise ProbeError("awg-resource-collision")
            attempted = True
            checked([ip, "netns", "add", namespace], "awg-namespace-create-failed")
            self.namespace_root.mkdir(mode=0o700, exist_ok=True)
            info = self.namespace_root.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise ProbeError("unsafe-resolver-root")
            resolver.mkdir(mode=0o700)
            resolver_created = True
            _private(resolver / "resolv.conf", "".join("nameserver " + value + "\n" for value in dns).encode())
            stripped = checked([quick, "strip", filename], "awg-config-strip-failed")
            process = subprocess.Popen([go, "-f", interface], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       env=self.environment, start_new_session=True)
            location = "host"
            deadline = time.monotonic() + min(timeout, 5)
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise ProbeError("awg-client-exited")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                code, _ = self.command([ip, "link", "show", interface], timeout=min(2, remaining))
                if code == 0:
                    # The TUN appears before the userspace control socket.
                    # Read the fresh daemon before the single configuration write.
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    ready, port = self.command([awg, "show", interface, "listen-port"],
                                               timeout=min(2, remaining))
                    if process.poll() is not None:
                        raise ProbeError("awg-client-exited")
                    if ready == 0:
                        if not re.fullmatch(rb"(?:0|[1-9][0-9]{0,4})\n", port) or int(port) > 65535:
                            raise ProbeError("awg-client-state-invalid")
                        break
                elif code != 1:
                    raise ProbeError("awg-interface-unavailable")
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(0.05, remaining))
            else:
                raise ProbeError("awg-client-start-timeout")
            if time.monotonic() >= deadline:
                raise ProbeError("awg-client-start-timeout")
            checked([awg, "setconf", interface, "/dev/stdin"], "awg-configure-failed", data=stripped)
            # Record intent before the move; cleanup reconciles both namespaces.
            location = "uncertain"
            checked([ip, "link", "set", interface, "netns", namespace], "awg-namespace-move-failed")
            location = "namespace"
            checked([ip, "-n", namespace, "link", "set", "lo", "up"], "awg-loopback-failed")
            for address in addresses:
                checked([ip, "-n", namespace, "address", "add", str(address), "dev", interface], "awg-address-failed")
            checked([ip, "-n", namespace, "link", "set", interface, "mtu", str(config["mtu"]), "up"], "awg-interface-up-failed")
            for version in {address.version for address in addresses}:
                checked([ip, "-n", namespace, "-" + str(version), "route", "add", "default", "dev", interface], "awg-route-failed")
            started = int(time.time())
            result = self.http(control, timeout, directory, namespace=namespace)
            handshakes = checked([ip, "netns", "exec", namespace, awg, "show", interface, "latest-handshakes"], "awg-handshake-read-failed")
            rows = [line.split() for line in handshakes.decode("ascii").splitlines()]
            if len(rows) != 1 or len(rows[0]) != 2 or not rows[0][1].isdigit():
                raise ProbeError("awg-handshake-unavailable")
            stamp = int(rows[0][1])
            fresh = started - 5 <= stamp <= int(time.time())
            if stamp != 0 and not fresh:
                raise ProbeError("awg-stale-handshake")
            if process.poll() is not None:
                raise ProbeError("awg-client-exited")
            result.update(fresh_handshake=fresh, setup_ok=True)
            if result["accepted"] and not fresh:
                raise ProbeError("awg-no-fresh-handshake")
        finally:
            cleanup = _stop(process)
            if location:
                prefixes = [[ip], [ip, "-n", namespace]] if location == "uncertain" else [[ip, "-n", namespace] if location == "namespace" else [ip]]
                for prefix in prefixes:
                    try:
                        code, _ = self.cleanup_command([*prefix, "link", "show", interface])
                        if code == 0:
                            code, _ = self.cleanup_command([*prefix, "link", "delete", interface])
                            cleanup &= code == 0
                        else:
                            cleanup &= code == 1
                    except (OSError, ValueError, subprocess.SubprocessError):
                        cleanup = False
            if attempted and (marker.exists() or marker.is_symlink()):
                try:
                    code, _ = self.cleanup_command([ip, "netns", "delete", namespace])
                    cleanup &= code == 0 and not marker.exists() and not marker.is_symlink()
                except (OSError, ValueError, subprocess.SubprocessError):
                    cleanup = False
            if resolver_created:
                try:
                    (resolver / "resolv.conf").unlink()
                    resolver.rmdir()
                except OSError:
                    cleanup = False
            Path(filename).unlink()
            if not cleanup:
                raise ProbeError("cleanup-failed")
        return {**result, "cleanup_ok": True}


def run_request(request, *, runtime=None):
    request = validate_request(request)
    runtime = runtime or Runtime()
    results = []
    with runtime.budget(), tempfile.TemporaryDirectory(prefix="device-probe-") as temporary:
        directory = Path(temporary)
        control = request["control"]
        timeout = request["timeout_seconds"]
        try:
            initial_control = runtime.http(control, timeout, directory)["accepted"]
        except (OSError, ValueError, subprocess.SubprocessError):
            initial_control = False
        for profile in request["profiles"]:
            witnesses = {"control_ok": False, "setup_ok": False, "cleanup_ok": False,
                         "peer_absent": False, "runtime_healthy": False, "fresh_handshake": False,
                         "inactive_confirmed": False}
            state, reason = "unknown", "control-unavailable"
            try:
                if not initial_control:
                    raise ProbeError(reason)
                before = runtime.witness(profile)
                measured = (runtime.awg(profile, control, timeout, directory) if profile["engine"] == "awg"
                            else runtime.stream(profile, control, timeout, directory))
                after = runtime.witness(profile)
                witnesses.update(setup_ok=measured["setup_ok"], cleanup_ok=measured["cleanup_ok"],
                                 peer_absent=before["peer_absent"] and after["peer_absent"],
                                 runtime_healthy=before["runtime_healthy"] and after["runtime_healthy"],
                                 inactive_confirmed=before["inactive_confirmed"] and after["inactive_confirmed"],
                                 fresh_handshake=measured.get("fresh_handshake", False),
                                 control_ok=runtime.http(control, timeout, directory)["accepted"])
                if before != after or not all(witnesses[key] for key in ("control_ok", "setup_ok", "cleanup_ok", "runtime_healthy")):
                    raise ProbeError("unstable-or-unhealthy-runtime")
                if measured["accepted"]:
                    state, reason = "accepted", "authenticated-payload"
                elif profile["engine"] == "awg" and witnesses["peer_absent"] and not witnesses["fresh_handshake"] and measured["exit"] == 28 and measured["elapsed"] >= timeout - 0.25:
                    state, reason = "denied", "absent-peer-no-handshake"
                elif witnesses["peer_absent"] and measured["exit"] in {35, 52, 56, 97}:
                    state, reason = "denied", "absent-identity-access-failed"
                elif witnesses["peer_absent"] and witnesses["inactive_confirmed"] and (
                    measured["exit"] == 7
                    or (profile["engine"] == "hysteria" and measured["exit"] == 28
                        and measured["elapsed"] >= timeout)
                ):
                    state, reason = "denied", "retired-runtime-access-failed"
                else:
                    reason = "access-ambiguous"
            except (OSError, ValueError, KeyError, UnicodeError, subprocess.SubprocessError) as error:
                reason = str(error) if isinstance(error, ProbeError) else "probe-unavailable"
            results.append({"id": profile["id"], "state": state, "reason": reason, **witnesses})
    return {"schema_version": 1, "control": "passed" if initial_control else "failed", "profiles": results,
            "cleanup": "confirmed" if all(row["cleanup_ok"] for row in results) else "unconfirmed"}


def main():
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt
    for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(number, interrupted)
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ProbeError("request-limit")
        if sys.platform != "linux" or os.geteuid() != 0:
            raise ProbeError("linux-root-required")
        request = json.loads(raw, object_pairs_hook=_unique)
        print(json.dumps(run_request(request), separators=(",", ":")))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, KeyboardInterrupt):
        print('{"schema_version":1,"error":"probe-refused"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
