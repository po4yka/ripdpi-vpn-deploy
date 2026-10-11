"""Reset native UDP generations before admission and recover only owned frontends."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import signal
import socket
import stat
import subprocess
import sys
import time

NORMALIZER = "ripdpi-transport-normalizer.service"
GATEWAYS = {"direct": "ripdpi-transport-direct.service", "warp": "ripdpi-transport-warp.service"}
FRONTENDS = {"xray.service", "hysteria-server.service"}
LOADER = "/usr/local/libexec/ripdpi-transport-egress/policy-loader.py"
POLICY = "/etc/ripdpi/transport-egress/policy.json"
READY = Path('/var/lib/ripdpi/transport-egress/ready.json')
stopping = False


class Refusal(Exception):
    pass


def private_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        record = os.fstat(fd)
        if not stat.S_ISREG(record.st_mode) or record.st_nlink != 1 or record.st_uid != 0 or record.st_mode & 0o077 or record.st_size > 1048576:
            raise Refusal("private-authority-invalid")
        raw = os.read(fd, 1048577)
        return json.loads(raw)
    finally:
        os.close(fd)


def validate(config, normalizer):
    if not isinstance(config, dict) or set(config) != {"schema_version", "gateway_units", "frontend_units", "normalizer_uid", "control_timeout_seconds", "recovery_seconds"}:
        raise Refusal("generation-config-invalid")
    if config["schema_version"] != 1 or type(config["normalizer_uid"]) is not int or config["normalizer_uid"] <= 0:
        raise Refusal("generation-config-invalid")
    expected = [GATEWAYS[name] for name in normalizer["backends"]]
    if config["gateway_units"] != expected or not expected or expected[0] != GATEWAYS["direct"]:
        raise Refusal("generation-gateways-invalid")
    fronts = config["frontend_units"]
    if not isinstance(fronts, list) or len(fronts) != len(set(fronts)) or any(unit not in FRONTENDS for unit in fronts):
        raise Refusal("generation-frontends-invalid")
    if normalizer["runtime_uid"] != config["normalizer_uid"]:
        raise Refusal("generation-identity-invalid")
    for name, maximum in [("control_timeout_seconds", 60), ("recovery_seconds", 30)]:
        if type(config[name]) is not int or not 1 <= config[name] <= maximum:
            raise Refusal("generation-deadline-invalid")
    return config


def command(argv, timeout):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    if result.returncode:
        operation = 'unknown'
        if argv[0] == 'systemctl' and argv[1] in {'show', 'stop', 'start', 'reset-failed'}:
            operation = 'systemctl-' + argv[1]
            labels = {NORMALIZER: 'normalizer', GATEWAYS['direct']: 'direct',
                      GATEWAYS['warp']: 'warp', 'xray.service': 'xray',
                      'hysteria-server.service': 'hysteria'}
            if len(argv) > 2 and argv[2] in labels:
                operation += '-' + labels[argv[2]]
        elif argv[0] == LOADER and argv[1] in {'apply', 'verify'}:
            operation = 'policy-' + argv[1]
        elif argv == ['/usr/bin/python3', '-Es', '/usr/local/libexec/ripdpi-warp/namespace.py', 'refresh']:
            operation = 'warp-refresh'
        elif argv[0] == 'journalctl':
            operation = 'readiness-journal'
        raise Refusal("generation-command-failed-" + operation)
    return result.stdout.decode("utf-8", "strict")


class Controller:
    def __init__(self, config, normalizer):
        self.config, self.normalizer = validate(config, normalizer), normalizer
        self.timeout = config["control_timeout_seconds"]

    def state(self, unit, *, check_identity=True):
        if unit not in {NORMALIZER, *GATEWAYS.values(), *FRONTENDS}:
            raise Refusal("generation-unit-invalid")
        text = command(["systemctl", "show", unit, "--property=LoadState,ActiveState,MainPID,ControlGroup,FragmentPath"], self.timeout)
        fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
        expected = Path("/etc/systemd/system") / unit
        if fields.get("LoadState") != "loaded" or fields.get("FragmentPath") != str(expected):
            raise Refusal("generation-unit-unowned")
        info = expected.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o022:
            raise Refusal("generation-unit-unowned")
        pid = int(fields.get('MainPID', '0'))
        if check_identity and pid > 0:
            policy = private_json(POLICY)
            if unit == NORMALIZER:
                expected_uid = policy['normalizer_uid']
            elif unit in GATEWAYS.values():
                expected_uid = policy['gateway_uid' if unit == GATEWAYS['direct'] else 'warp_gateway_uid']
            else:
                name = 'direct_xray' if unit == 'xray.service' else 'direct_hysteria'
                listeners = [value for value in policy['listeners'] if value['name'] == name]
                if len(listeners) != 1:
                    raise Refusal('generation-process-identity')
                expected_uid = listeners[0]['frontend_uid']
            if type(expected_uid) is not int or expected_uid <= 0:
                raise Refusal('generation-process-identity')
            fd = os.open('/proc/'+str(pid)+'/status', os.O_RDONLY | os.O_NOFOLLOW)
            try:
                raw = os.read(fd, 65537)
            finally:
                os.close(fd)
            if len(raw) > 65536:
                raise Refusal('generation-process-identity')
            status = dict(line.split(':', 1) for line in raw.decode('ascii').splitlines() if ':' in line)
            if status.get('Pid', '').strip() != str(pid) or status.get('Uid', '').split() != [str(expected_uid)] * 4:
                raise Refusal('generation-process-identity')
        return fields

    def stop(self, unit):
        # Invalid runtime identity must never prevent stopping the owned unit.
        before = self.state(unit, check_identity=False)
        command(["systemctl", "stop", unit], self.timeout)
        state = self.state(unit, check_identity=False)
        if state.get("ActiveState") not in {"inactive", "failed"} or int(state.get("MainPID", "-1")) != 0:
            raise Refusal("generation-stop-unconfirmed")
        cgroup = before.get("ControlGroup", "")
        if cgroup:
            path = Path("/sys/fs/cgroup") / cgroup.lstrip("/") / "cgroup.procs"
            if path.exists() and path.read_text().strip():
                raise Refusal("generation-stop-unconfirmed")

    def start(self, unit):
        # Startup metadata may describe systemd's privileged executor before
        # the configured UID and executable are installed. Admission follows
        # the synchronous Type=exec start, not this reset-state inspection.
        state = self.state(unit, check_identity=False)
        # An inactive, unreferenced unit may be garbage-collected after show;
        # reset-failed does not load it. Only clear actual failed state.
        if state.get('ActiveState') == 'failed':
            command(["systemctl", "reset-failed", unit], self.timeout)
        command(["systemctl", "start", unit], self.timeout)
        state = self.state(unit)
        if state.get("ActiveState") != "active" or int(state.get("MainPID", "0")) <= 0:
            raise Refusal("generation-start-unconfirmed")
        return int(state["MainPID"])

    def stop_frontends(self):
        for unit in self.config["frontend_units"]:
            self.stop(unit)

    def stop_gateways(self):
        for unit in self.config["gateway_units"]:
            self.stop(unit)

    def prepare(self):
        # Do not stop NORMALIZER: this path runs inside its ExecStartPre.
        self.stop_frontends()
        self.stop_gateways()
        if 'warp' in self.normalizer['backends']:
            command(['/usr/bin/python3', '-Es', '/usr/local/libexec/ripdpi-warp/namespace.py', 'refresh'], self.timeout)
        # Reboot loses owned nft state. Restore only after definitive consumer stop;
        # apply retains the loader's foreign-hook and kernel-authority admission.
        command([LOADER, "apply", "--config", POLICY], self.timeout)
        command([LOADER, "verify", "--config", POLICY], self.timeout)
        for unit in self.config["gateway_units"]:
            self.start(unit)

    def snapshot(self):
        result = {}
        for unit in [NORMALIZER, *self.config["gateway_units"], *self.config["frontend_units"]]:
            state = self.state(unit)
            if state.get("ActiveState") != "active" or int(state.get("MainPID", "0")) <= 0:
                raise Refusal("generation-not-active")
            result[unit] = int(state["MainPID"])
        return result

    def ready(self):
        # Probe only authentication and UDP control, not a recipient or public target.
        # Child UID admission is the same kernel path used by the actual frontend.
        probes = [(listener["frontend_uid"], {**listener, "probe_kind": "auth"}) for listener in self.normalizer["listeners"]]
        probes.extend((self.normalizer["runtime_uid"], {**backend, "name": name, "probe_kind": "udp-control"})
                      for name, backend in self.normalizer["backends"].items())
        deadline = time.monotonic() + self.timeout
        while True:
            stage = 'generation-readiness-process-state'
            try:
                pid = self.state(NORMALIZER).get('MainPID')
                process_verified = int(pid or '0') > 0
                stage = 'generation-readiness-journal-query'
                journal = command(['journalctl', '--unit='+NORMALIZER, '--boot', '--output=json',
                                   '--lines=200', '--no-pager'], max(0.1, deadline-time.monotonic()))
                messages = [json.loads(line) for line in journal.splitlines()]
                matching = [value for value in messages if value.get('_PID') == pid
                            and value.get('MESSAGE') == 'normalizer-ready']
                message_seen = bool(matching)
                uid_seen = any(value.get('_UID') == str(self.normalizer['runtime_uid']) for value in matching)
                stage = ('generation-readiness-journal-message-' + str(int(message_seen))
                         + '-uid-' + str(int(uid_seen)) + '-process-' + str(int(process_verified)))
                if not uid_seen:
                    raise Refusal('generation-normalizer-not-ready')
                for uid, listener in probes:
                    labels = {'direct_xray': 'auth-direct-xray', 'direct_hysteria': 'auth-direct-hysteria',
                              'warp_xray': 'auth-warp-xray', 'direct': 'udp-control-direct',
                              'warp': 'udp-control-warp'}
                    stage = 'generation-readiness-' + labels.get(listener['name'], 'unknown-probe')
                    entry = pwd.getpwuid(uid)
                    payload = json.dumps(listener).encode()
                    def demote():
                        os.setgroups([])
                        os.setgid(entry.pw_gid)
                        os.setuid(entry.pw_uid)
                    result = subprocess.run([sys.executable, '-Es', __file__, 'probe'], input=payload,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            timeout=max(0.1, deadline-time.monotonic()), preexec_fn=demote, check=False)
                    if result.returncode:
                        raise Refusal('generation-readiness-failed')
                return
            except (Refusal, subprocess.SubprocessError) as error:
                if time.monotonic() >= deadline:
                    suffix = ('-timeout' if isinstance(error, subprocess.TimeoutExpired) else
                              '-child-failed' if isinstance(error, subprocess.SubprocessError) else '')
                    raise Refusal(stage + suffix) from None
                time.sleep(0.1)

    def frontend_credentials(self):
        # The frontend roles have already performed genuine syntax/topology validation.
        # Check their actual published private authority against this generation as well.
        by_name = {value['name']: value for value in self.normalizer['listeners']}
        for unit in self.config['frontend_units']:
            path = Path('/etc/xray/config.json' if unit == 'xray.service' else '/etc/hysteria/config.yaml')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o027 or info.st_size > 1048576:
                    raise Refusal('generation-frontend-authority-invalid')
                raw = os.read(fd, 1048577).decode('utf-8', 'strict')
            finally:
                os.close(fd)
            if unit == 'xray.service':
                outbounds = json.loads(raw)['outbounds']
                for name, tag in [('direct_xray', 'direct'), ('warp_xray', 'warp-out')]:
                    if name not in by_name:
                        continue
                    matching = [value for value in outbounds if value.get('tag') == tag]
                    if len(matching) != 1:
                        raise Refusal('generation-frontend-authority-invalid')
                    expected = by_name[name]
                    server = matching[0]['settings']['servers'][0]
                    if server['address'] != expected['address'] or server['port'] != expected['port'] or server['users'] != [{'user': expected['username'], 'pass': expected['password']}]:
                        raise Refusal('generation-frontend-credential-mismatch')
            else:
                blocks = raw.split('outbounds:\n')
                if len(blocks) != 2:
                    raise Refusal('generation-frontend-authority-invalid')
                expected = by_name['direct_hysteria']
                for field, value in [('addr', expected['address']+':'+str(expected['port'])),
                                     ('username', expected['username']), ('password', expected['password'])]:
                    found = re.findall(r'^      '+field+r': (".*")$', blocks[1], re.MULTILINE)
                    if len(found) != 1 or json.loads(found[0]) != value:
                        raise Refusal('generation-frontend-credential-mismatch')

    def run(self):
        global stopping
        while not stopping:
            try:
                self.stop_frontends()
                self.stop(NORMALIZER)
                self.start(NORMALIZER)  # ExecStartPre resets both old gateways first.
                self.ready()
                tunnel_index = private_json(POLICY).get("warp", {}).get("tunnel_ifindex")
                next_tunnel_check = time.monotonic()
                self.frontend_credentials()
                for unit in self.config["frontend_units"]:
                    self.start(unit)
                generation = self.snapshot()
                self.publish_ready(generation)
                print("transport-generation-ready", flush=True)
                while not stopping:
                    if "warp" in self.normalizer["backends"] and time.monotonic() >= next_tunnel_check:
                        command(["systemctl", "start", "ripdpi-warp-refresh.service"], self.timeout)
                        if private_json(POLICY).get("warp", {}).get("tunnel_ifindex") != tunnel_index:
                            raise Refusal("generation-tunnel-changed")
                        next_tunnel_check = time.monotonic() + self.config["recovery_seconds"]
                    if self.snapshot() != generation:
                        raise Refusal("generation-process-changed")
                    time.sleep(1)
            except (Refusal, OSError, ValueError, subprocess.SubprocessError) as error:
                reason = str(error) if isinstance(error, Refusal) else type(error).__name__
                print("transport-generation-recovering:" + reason, flush=True)
                try:
                    self.stop_frontends()
                    self.stop(NORMALIZER)
                    self.stop_gateways()
                except (Refusal, OSError, ValueError, subprocess.SubprocessError):
                    raise Refusal("generation-cleanup-unconfirmed") from None
                until = time.monotonic() + self.config["recovery_seconds"]
                while not stopping and time.monotonic() < until:
                    time.sleep(0.1)
        self.stop_frontends()
        self.stop(NORMALIZER)
        self.stop_gateways()

    def publish_ready(self, generation):
        from snapshot import accept
        accept()
        value = {'schema': 1, 'controller_pid': os.getpid(), 'generation': generation,
                 'config_digest': hashlib.sha256(json.dumps(self.normalizer, sort_keys=True).encode()).hexdigest()}
        temporary = READY.with_name('.ready-' + str(os.getpid()))
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'w') as target:
                json.dump(value, target)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, READY)
        finally:
            temporary.unlink(missing_ok=True)

    def status(self):
        value = private_json(READY)
        expected = hashlib.sha256(json.dumps(self.normalizer, sort_keys=True).encode()).hexdigest()
        state = command(['systemctl', 'show', 'ripdpi-transport-generation.service', '--property=MainPID,ActiveState'], self.timeout)
        fields = dict(line.split('=', 1) for line in state.splitlines() if '=' in line)
        if value.get('schema') != 1 or value.get('config_digest') != expected or value.get('generation') != self.snapshot() or fields.get('ActiveState') != 'active' or int(fields.get('MainPID', '0')) != value.get('controller_pid'):
            raise Refusal('generation-readiness-stale')
        self.frontend_credentials()
        for unit in self.config['frontend_units']:
            if self.state(unit).get('ActiveState') != 'active':
                raise Refusal('generation-frontend-not-ready')


def probe(listener):
    def exact(conn, size):
        value = b""
        while len(value) < size:
            part = conn.recv(size - len(value))
            if not part:
                raise Refusal("readiness-closed")
            value += part
        return value
    with socket.create_connection((listener["address"], listener["port"]), timeout=3) as conn:
        conn.sendall(b"\x05\x01\x02")
        if exact(conn, 2) != b"\x05\x02":
            raise Refusal("readiness-auth-method")
        user, password = listener["username"].encode(), listener["password"].encode()
        conn.sendall(bytes([1, len(user)]) + user + bytes([len(password)]) + password)
        if exact(conn, 2) != b"\x01\x00":
            raise Refusal("readiness-auth-refused")
        if listener.get("probe_kind") == "auth":
            return
        # Hysteria's control convention encodes a destination, rather than a source.
        # Use an admissible numeric public resolver; no datagram is sent by this probe.
        target = socket.inet_aton("1.1.1.1") if listener["name"] == "direct_hysteria" else bytes(4)
        port = 53 if listener["name"] == "direct_hysteria" else 0
        conn.sendall(b"\x05\x03\x00\x01" + target + port.to_bytes(2, "big"))
        if exact(conn, 4)[1] != 0:
            raise Refusal("readiness-association-refused")


def terminate(*_):
    global stopping
    stopping = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run", "prepare", "validate", "status", "probe"])
    parser.add_argument("--config")
    parser.add_argument("--normalizer-config")
    args = parser.parse_args()
    if args.action == "probe":
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise Refusal("readiness-input-oversize")
        probe(json.loads(raw))
        return
    controller = Controller(private_json(args.config), private_json(args.normalizer_config))
    if args.action == "validate":
        return
    if os.geteuid() != 0:
        raise Refusal("generation-requires-root")
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    getattr(controller, args.action)()


if __name__ == "__main__":
    try:
        main()
    except (Refusal, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        reason = str(error) if isinstance(error, Refusal) else type(error).__name__
        print("transport-generation-refused:" + reason, file=sys.stderr)
        raise SystemExit(1)
