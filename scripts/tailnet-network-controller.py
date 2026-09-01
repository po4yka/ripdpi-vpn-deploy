#!/usr/bin/env python3
"""Operator composition root for one Tailnet promotion and its rollback daemon."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PROMOTION_PATH = ROOT / "scripts" / "tailnet-network-promotion.py"
EXECUTOR = ROOT / "scripts" / "tailnet-network-executor.py"
GUEST_HELPER = "/usr/local/lib/vpn-tailnet-network/tailnet-network-guest.py"
MAX = 65536
# The canonical JSON request (including base64 and timeout) must fit the
# guest's 64-KiB bounded stdin frame at this exact raw candidate ceiling.
MAX_CANDIDATE = 49125


def process_incarnation(pid: int):
    """Return the kernel-reported process start time used to detect PID reuse."""
    try:
        result = subprocess.run(
            ["/bin/ps", "-o", "lstart=", "-p", str(pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        raise ControllerError("process-incarnation-refused") from None
    value = result.stdout.strip()
    if result.returncode != 0 or not value or len(value) > 64 or "\n" in value:
        raise ControllerError("process-incarnation-refused")
    return value


def executor_identity(
    target_digest: str, terraform_digest: str, snapshot_digest: str, token: str
):
    """Return the non-secret authority a controller must match before reuse."""
    if (
        p.HEX.fullmatch(target_digest) is None
        or p.HEX.fullmatch(terraform_digest) is None
        or p.HEX.fullmatch(snapshot_digest) is None
        or not isinstance(token, str)
        or not token
    ):
        raise ControllerError("executor-identity-refused")
    return {
        "provider_target_sha256": target_digest,
        "terraform_sha256": terraform_digest,
        "terraform_snapshot_sha256": snapshot_digest,
        # This is an in-memory/0600 daemon capability binding, never a
        # promotion receipt.  It prevents a later credential from arming an
        # executor that inherited a prior controller's provider authority.
        "provider_capability_sha256": hashlib.sha256(
            b"tailnet-network-executor-capability-v2\0" + token.encode("utf-8")
        ).hexdigest(),
    }


def module():
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_promotion", PROMOTION_PATH
    )
    value = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(value)
    return value


p = module()
PREPARE_TIMEOUT = p.TRANSACTION_LEASE_SECONDS


class ControllerError(RuntimeError):
    pass


def private(path: Path, *, executable=False):
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_nlink != 1
        or before.st_mode & (0o022 if executable else 0o077)
    ):
        raise ControllerError("private-input-refused")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    after = os.fstat(fd)
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        os.close(fd)
        raise ControllerError("private-input-refused")
    return fd


def private_directory(path: Path):
    if not path.is_absolute():
        raise ControllerError("executor-directory-refused")
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            os.close(parent)
            parent = child
            info = os.fstat(parent)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in {0, os.geteuid()}
                or info.st_mode & 0o022
            ):
                raise ControllerError("executor-directory-refused")
        try:
            os.mkdir(path.name, 0o700, dir_fd=parent)
        except FileExistsError:
            # The final component is validated through its no-follow descriptor.
            pass
        fd = os.open(
            path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
    finally:
        os.close(parent)
    if fd is None:
        raise ControllerError("executor-directory-refused")
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise ControllerError("executor-directory-refused")
    finally:
        os.close(fd)


def snapshot_recovery_required(root: Path):
    """Keep an old immutable snapshot only while a durable lease needs it."""
    path = root / "receipt.json"
    if not path.exists():
        return False
    fd = private(path)
    try:
        raw = os.read(fd, MAX + 1)
    finally:
        os.close(fd)
    try:
        envelope = json.loads(raw)
        payload = envelope["payload"]
        canonical_payload = (
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        canonical_envelope = (
            json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        if (
            len(raw) > MAX
            or raw != canonical_envelope
            or set(envelope) != {"payload", "sha256"}
            or envelope["sha256"] != hashlib.sha256(canonical_payload).hexdigest()
            or not isinstance(payload, dict)
            or payload.get("state")
            not in {
                "armed",
                "forward-started",
                "provider-applied",
                "committed-cleanup-debt",
                "executed",
                "released",
            }
        ):
            raise ValueError
        return payload["state"] in {
            "armed",
            "forward-started",
            "provider-applied",
            "committed-cleanup-debt",
        }
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise ControllerError("executor-recovery-refused") from None


def load_config(path: Path):
    fd = private(path)
    try:
        raw = os.read(fd, MAX + 1)
    finally:
        os.close(fd)
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ControllerError("config-refused") from None
    required = {
        "inventory_path",
        "inventory_name",
        "contexts",
        "mode",
        "promotion_config_path",
        "provider_target_path",
        "provider_state_path",
        "terraform_path",
        "terraform_sha256",
        "known_hosts_path",
        "executor_dir",
        "candidate_fragment_path",
    }
    if (
        set(value) != required
        or value["mode"] not in {"dry-run", "apply"}
        or not all(isinstance(value[k], str) for k in required - {"contexts", "mode"})
    ):
        raise ControllerError("config-refused")
    return value


def guard(socket_path: Path):
    def invoke(action, value):
        payload = json.dumps(
            {"action": action, "value": value}, sort_keys=True, separators=(",", ":")
        ).encode()
        if len(payload) > MAX:
            raise p.PromotionError("rollback-uncertain")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(
                    p.ROLLBACK_GUARD_RPC_TIMEOUT_SECONDS
                    if action in {"rollback-provider", "execute"}
                    else p.GUARD_RPC_TIMEOUT_SECONDS
                )
                client.connect(str(socket_path))
                client.sendall(payload)
                client.shutdown(socket.SHUT_WR)
                chunks = bytearray()
                while len(chunks) <= MAX:
                    chunk = client.recv(min(4096, MAX + 1 - len(chunks)))
                    if not chunk:
                        break
                    chunks.extend(chunk)
                if len(chunks) > MAX:
                    raise ValueError
                raw = bytes(chunks)
            result = json.loads(raw)
            if not isinstance(result, dict) or set(result) != {"ok"}:
                raise ValueError
            return result["ok"]
        except (OSError, ValueError, UnicodeError):
            raise p.PromotionError("rollback-uncertain") from None

    return invoke


def provider_transaction_lock(root: Path):
    path = root / "provider.lock"
    fd = os.open(
        path,
        os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
    ):
        os.close(fd)
        raise ControllerError("provider-lock-refused")
    os.fchmod(fd, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _live_executor(
    socket_path: Path, identity: dict, *, allow_unarmed=False, allow_terminal=False
):
    try:
        value = guard(socket_path)("ping", {})
        return (
            isinstance(value, dict)
            and set(value) == {"identity", "receipt_state"}
            and value["identity"] == identity
            and value["receipt_state"]
            in (
                {
                    "armed",
                    "forward-started",
                    "provider-applied",
                    "committed-cleanup-debt",
                }
                | ({None} if allow_unarmed else set())
                | ({"executed", "released"} if allow_terminal else set())
            )
        )
    except p.PromotionError:
        return False


def _wait_for_spawned_executor(process, socket_path: Path, identity: dict):
    """Accept only the just-spawned daemon's exact unarmed handshake."""
    for _ in range(50):
        if socket_path.exists():
            if _live_executor(
                socket_path,
                identity,
                allow_unarmed=True,
                allow_terminal=True,
            ):
                return
            # The socket can belong to another controller or a stale daemon;
            # never continue into arm based on path existence alone.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            raise ControllerError("executor-identity-refused")
        if process.poll() is not None:
            raise ControllerError("executor-unavailable")
        time.sleep(0.1)
    raise ControllerError("executor-unavailable")


def _reap_spawned_process(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _wait_or_reap_spawned_executor(process, socket_path: Path, identity: dict):
    """Never leave the credential-bearing child behind after handshake failure."""
    try:
        _wait_for_spawned_executor(process, socket_path, identity)
    except (Exception, KeyboardInterrupt, SystemExit):
        _reap_spawned_process(process)
        raise


def _terminate_unarmed_executor(process, socket_path: Path, identity: dict):
    """Reap the child we spawned only while its receipt remains unarmed."""
    if process is None or process.poll() is not None:
        return
    if _live_executor(socket_path, identity, allow_unarmed=True) and not _live_executor(
        socket_path, identity
    ):
        _reap_spawned_process(process)


def _wait_for_terminal_cleanup(process, root: Path, socket_path: Path, snapshot: Path):
    """Do not report reconciliation while durable daemon artifacts remain live."""
    for _ in range(50):
        artifacts_removed = not any(
            path.exists() or path.is_symlink()
            for path in (socket_path, root / "daemon.json", snapshot)
        )
        process_exited = process is None or process.poll() is not None
        if artifacts_removed and process_exited:
            return
        time.sleep(0.1)
    raise ControllerError("executor-cleanup-refused")


def _reconcile_previous(adapter, rollback_guard, guest, host, promotion_config):
    """Finish an earlier provider and guest rollback before a new promotion."""
    current = rollback_guard("reconcile", {})
    state = current.get("state") if isinstance(current, dict) else None
    if state == "idle":
        return False
    if state in {"executed", "released"}:
        if rollback_guard("acknowledge", {"state": state}) != {"state": "idle"}:
            raise p.PromotionError("rollback-uncertain")
        return True
    if state == "committed-cleanup-debt":
        p.reconcile_release(adapter, tuple(sorted(current.items())))
        return True
    if state not in {"armed", "forward-started", "provider-applied"}:
        raise p.PromotionError("rollback-uncertain")
    try:
        identity = {
            "generation": current["guest_generation"],
            "nonce": current["guest_nonce"],
            "snapshot_digest": current["guest_snapshot_digest"],
            "deadline": current["guest_deadline"],
        }
    except KeyError:
        raise p.PromotionError("rollback-uncertain") from None
    if current.get("guest_phase") == "unchanged":
        rollback_guard("rollback-provider", current)
        terminal = rollback_guard("execute", current)
        if terminal != {"state": "executed"}:
            raise p.PromotionError("rollback-uncertain")
        return True
    if current.get("guest_phase") != "transactional":
        raise p.PromotionError("rollback-uncertain")
    status = guest(host, "status", {}, False)
    status_name = status.get("status") if isinstance(status, dict) else None
    if status_name == "rolled_back":
        p._same_receipt(status, identity, "rolled_back")
    elif state in {"armed", "forward-started"}:
        p._same_receipt(status, identity, "prepared")
    elif status_name in {"prepared", "applied"}:
        p._same_receipt(status, identity, status_name)
    elif status_name == "committed":
        p._same_receipt(status, identity, "committed")
        expected_identity = {
            key: adapter.target.value[key]
            for key in (
                "inventory_alias",
                "public_service_address_sha256",
                "deployable_digest",
            )
        }
        proof = p.promotion_proof(
            Path(promotion_config),
            p._env(adapter.environment),
            expected_identity,
            current["provider_applied_at"],
        )
        if proof is None:
            raise p.PromotionError("promotion-proof-failed")
        armed = dict(current)
        armed.pop("forward_lease")
        armed.pop("provider_applied_at")
        armed["state"] = "armed"
        p.reconcile_commit_release(adapter, tuple(sorted(armed.items())), status, proof)
        return True
    else:
        raise p.PromotionError("rollback-uncertain")
    rollback_guard("rollback-provider", current)
    if status_name != "rolled_back":
        p._same_receipt(
            guest(host, "rollback", identity, True), identity, "rolled_back"
        )
    terminal = rollback_guard("execute", current)
    if terminal != {"state": "executed"}:
        raise p.PromotionError("rollback-uncertain")
    return True


def _remove_verified_stale_executor(
    root: Path, socket_path: Path, identity: dict, *, socket_required=True
):
    """Only unlink a dead daemon with the exact trusted invocation identity."""
    pid_path = root / "daemon.json"
    fd = private(pid_path)
    try:
        value = json.loads(os.read(fd, MAX + 1))
    finally:
        os.close(fd)
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "pid", "process_started_at", *identity}
        or value.get("schema_version") != 3
        or type(value.get("pid")) is not int
        or not isinstance(value.get("process_started_at"), str)
        or not value["process_started_at"]
        or any(value.get(key) != item for key, item in identity.items())
    ):
        raise ControllerError("executor-stale-refused")
    try:
        os.kill(value["pid"], 0)
    except ProcessLookupError:
        pass
    except PermissionError:
        raise ControllerError("executor-stale-refused") from None
    else:
        if process_incarnation(value["pid"]) == value["process_started_at"]:
            raise ControllerError("executor-unreachable")
    if socket_required:
        info = socket_path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            raise ControllerError("executor-stale-refused")
        socket_path.unlink()
    pid_path.unlink()


def strict_guest(host, known_hosts, candidate: bytes):
    """Fixed helper command, private fragment on stdin, strict pinned SSH only."""
    if len(candidate) > MAX_CANDIDATE:
        raise p.PromotionError("guest-uncertain")

    def call(_host, action, identity, cleanup):
        if action == "prepare":
            request = {
                "candidate_b64": base64.b64encode(candidate).decode("ascii"),
                "timeout": PREPARE_TIMEOUT,
            }
        elif action == "preview":
            request = {"candidate_b64": base64.b64encode(candidate).decode("ascii")}
        elif action in {"apply", "rollback", "confirm"}:
            request = identity
        elif action == "status":
            request = {}
        else:
            raise p.PromotionError("guest-uncertain")
        command = p.fleet_inspection.ssh_command(host, known_hosts)
        # fleet_inspection owns all strict transport and pinned-host options;
        # replace only its fixed remote command, never append a second one.
        command[-1] = "sudo -n /usr/bin/python3 -I -B " + GUEST_HELPER + " " + action
        raw = p._bounded(
            command,
            p._env("prod"),
            input_data=json.dumps(
                request, sort_keys=True, separators=(",", ":")
            ).encode(),
            timeout=p.COMMAND_TIMEOUT_SECONDS,
        )
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise p.PromotionError("guest-uncertain") from None

    return call


def validate_provider_return_path(state_value, host):
    """Validate the effective stateless provider rules for the frozen SSH host."""
    try:
        if not isinstance(state_value, dict) or type(host["port"]) is not int:
            raise ValueError

        def resource(kind, name):
            matches = [
                item
                for item in state_value["resources"]
                if item.get("type") == kind and item.get("name") == name
            ]
            if len(matches) != 1 or len(matches[0]["instances"]) != 1:
                raise ValueError
            return matches[0]["instances"][0]["attributes"]

        server = resource("upcloud_server", "vpn")
        rules = resource("upcloud_firewall_rules", "vpn")["firewall_rule"]
        ssh_data = resource("terraform_data", "ssh_port")["input"]
        outputs = state_value["outputs"]
        ssh_output = outputs["ssh_port"]["value"]
        listeners = outputs["public_listeners"]["value"]
        if (
            type(server["firewall"]) is not bool
            or type(ssh_data) is not int
            or ssh_data != host["port"]
            or ssh_output != host["port"]
            or not isinstance(rules, list)
            or not rules
            or not isinstance(listeners, list)
            or not listeners
        ):
            raise ValueError

        def drop_index(family):
            indices = [
                index
                for index, rule in enumerate(rules)
                if rule.get("action") == "drop"
                and rule.get("direction") == "in"
                and rule.get("family") == family
            ]
            if len(indices) != 1:
                raise ValueError
            return indices[0]

        drops = {family: drop_index(family) for family in ("IPv4", "IPv6")}
        ssh_rules = [
            (index, rule)
            for index, rule in enumerate(rules)
            if isinstance(rule.get("comment"), str)
            and rule["comment"].startswith("SSH allow ")
        ]
        if not ssh_rules:
            raise ValueError
        for index, rule in ssh_rules:
            start = ipaddress.ip_address(rule["source_address_start"])
            end = ipaddress.ip_address(rule["source_address_end"])
            family = "IPv6" if start.version == 6 else "IPv4"
            if (
                end.version != start.version
                or int(start) > int(end)
                or rule.get("action") != "accept"
                or rule.get("direction") != "in"
                or rule.get("family") != family
                or rule.get("protocol") != "tcp"
                or rule.get("destination_port_start") != str(host["port"])
                or rule.get("destination_port_end") != str(host["port"])
                or index >= drops[family]
            ):
                raise ValueError

        for listener in listeners:
            if (
                not isinstance(listener, dict)
                or not isinstance(listener.get("name"), str)
                or listener.get("protocol") not in {"tcp", "udp"}
            ):
                raise ValueError
            if type(listener.get("port")) is int:
                start = end = listener["port"]
            else:
                match = re.fullmatch(
                    r"([0-9]{1,5})-([0-9]{1,5})", listener.get("port_range", "")
                )
                if match is None:
                    raise ValueError
                start, end = map(int, match.groups())
            if not 1 <= start <= end <= 65535:
                raise ValueError
            for family in ("IPv4", "IPv6"):
                matching = [
                    index
                    for index, rule in enumerate(rules)
                    if rule.get("action") == "accept"
                    and rule.get("direction") == "in"
                    and rule.get("family") == family
                    and rule.get("protocol") == listener["protocol"]
                    and rule.get("destination_port_start") == str(start)
                    and rule.get("destination_port_end") == str(end)
                ]
                if not matching or min(matching) >= drops[family]:
                    raise ValueError

        return_ranges = set()
        for family in ("IPv4", "IPv6"):
            for protocol in ("tcp", "udp"):
                comment = f"{protocol.upper()} return {family}"
                matches = [
                    (index, rule)
                    for index, rule in enumerate(rules)
                    if rule.get("comment") == comment
                    and rule.get("action") == "accept"
                    and rule.get("direction") == "in"
                    and rule.get("family") == family
                    and rule.get("protocol") == protocol
                ]
                if len(matches) != 1 or matches[0][0] >= drops[family]:
                    raise ValueError
                start = int(matches[0][1]["destination_port_start"])
                end = int(matches[0][1]["destination_port_end"])
                if not 1024 <= start <= end <= 65535:
                    raise ValueError
                return_ranges.add((start, end))
        if len(return_ranges) != 1 or not any(
            rule.get("action") == "accept" and rule.get("direction") == "out"
            for rule in rules
        ):
            raise ValueError
        return server["firewall"]
    except (
        IndexError,
        KeyError,
        StopIteration,
        TypeError,
        ValueError,
        ipaddress.AddressValueError,
    ):
        raise p.PromotionError("provider-return-path-invalid") from None


def run(config):
    # Exact one alias is checked before either a daemon or SSH can start.
    aliases = p.fleet_inspection.select_hosts(
        Path(config["inventory_path"]), [config["inventory_name"]]
    )
    if len(aliases) != 1:
        raise ControllerError("selection-refused")
    target, state, terraform = (
        Path(config[k])
        for k in ("provider_target_path", "provider_state_path", "terraform_path")
    )
    target_fd = state_fd = terraform_fd = -1
    validated_target = validated_tf = None
    try:
        target_fd = private(target)
        state_fd = private(state)
        terraform_fd = private(terraform, executable=True)
        # Validate the three opened inodes in this composition root before daemon spawn.
        validated_target = p.ProviderTarget(target_fd, state_fd)
        target_fd = state_fd = -1
        validated_tf = p.TrustedTerraform(terraform_fd, config["terraform_sha256"])
        terraform_fd = -1
        target_digest = validated_target.digest
        target_environment = validated_target.value["environment"]
        terraform_digest = validated_tf.digest
    finally:
        if validated_target is not None:
            validated_target.close()
        if validated_tf is not None:
            validated_tf.close()
        if target_fd >= 0:
            os.close(target_fd)
        if state_fd >= 0:
            os.close(state_fd)
        if terraform_fd >= 0:
            os.close(terraform_fd)
    candidate_fd = private(Path(config["candidate_fragment_path"]))
    try:
        candidate = os.read(candidate_fd, MAX + 1)
    finally:
        os.close(candidate_fd)
    if len(candidate) > MAX_CANDIDATE:
        raise ControllerError("candidate-refused")
    root = Path(config["executor_dir"])
    private_directory(root)
    sock = root / "executor.sock"
    snapshot_path = root / "terraform-snapshot"
    if (
        (snapshot_path.exists() or snapshot_path.is_symlink())
        and not (sock.exists() or sock.is_symlink() or (root / "daemon.json").exists())
        and not snapshot_recovery_required(root)
    ):
        p.TerraformConfigSnapshot(snapshot_path).remove()
    terraform_snapshot = p.TerraformConfigSnapshot.create(
        ROOT, snapshot_path, target_environment
    )
    token = os.environ.get("UPCLOUD_TOKEN")
    process = None
    if config["mode"] == "apply":
        if not token:
            raise ControllerError("provider-credentials-unavailable")
        identity = executor_identity(
            target_digest, terraform_digest, terraform_snapshot.digest, token
        )
        if sock.exists() or sock.is_symlink():
            if not _live_executor(sock, identity):
                _remove_verified_stale_executor(root, sock, identity)
        elif (root / "daemon.json").exists():
            # A process can die after durable PID identity write but before
            # socket bind.  Reuse the same verified stale-artifact cleanup.
            _remove_verified_stale_executor(root, sock, identity, socket_required=False)
        if not sock.exists():
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(EXECUTOR),
                    "serve",
                    "--target",
                    str(target),
                    "--state",
                    str(state),
                    "--terraform",
                    str(terraform),
                    "--terraform-sha256",
                    config["terraform_sha256"],
                    "--terraform-snapshot",
                    str(terraform_snapshot.root),
                    "--terraform-snapshot-sha256",
                    terraform_snapshot.digest,
                    "--receipt-dir",
                    str(root),
                    "--socket",
                    str(sock),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env={
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "TZ": "UTC",
                    "UPCLOUD_TOKEN": token,
                },
            )
            _wait_or_reap_spawned_executor(process, sock, identity)
    target_fd = state_fd = terraform_fd = -1
    provider_target = trusted_terraform = adapter = None
    try:
        target_fd = private(target)
        state_fd = private(state)
        terraform_fd = private(terraform, executable=True)
        provider_target = p.ProviderTarget(target_fd, state_fd)
        target_fd = state_fd = -1
        trusted_terraform = p.TrustedTerraform(terraform_fd, config["terraform_sha256"])
        terraform_fd = -1
        adapter = p.TerraformAdapter(
            provider_target,
            trusted_terraform=trusted_terraform,
            terraform_snapshot=terraform_snapshot,
            external_rollback_guard=guard(sock),
            provider_transaction_lock=lambda: provider_transaction_lock(root),
            allow_apply=config["mode"] == "apply",
        )
    except (Exception, KeyboardInterrupt, SystemExit):
        if trusted_terraform is not None:
            trusted_terraform.close()
        if provider_target is not None:
            provider_target.close()
        if config["mode"] == "apply":
            _terminate_unarmed_executor(process, sock, identity)
        raise
    finally:
        if target_fd >= 0:
            os.close(target_fd)
        if state_fd >= 0:
            os.close(state_fd)
        if terraform_fd >= 0:
            os.close(terraform_fd)
    try:
        if token:
            adapter.environment_map = {
                **adapter.environment_map,
                "UPCLOUD_TOKEN": token,
            }

        def return_path(action, identity):
            if action not in {"forward", "readback"}:
                raise p.PromotionError("provider-return-path-invalid")
            try:
                state_value = json.loads(adapter.current_state())
                firewall = validate_provider_return_path(state_value, aliases[0])
            except (
                KeyError,
                IndexError,
                StopIteration,
                TypeError,
                ValueError,
                p.PromotionError,
            ):
                if action == "readback":
                    raise p.PromotionError("provider-readback-invalid") from None
                raise p.PromotionError("provider-return-path-invalid") from None
            if action == "forward":
                return firewall is False
            return {**identity, "firewall": firewall}

        adapter.return_path_guard = return_path
        request = {
            "inventory_path": config["inventory_path"],
            "inventory_name": config["inventory_name"],
            "contexts": config["contexts"],
            "mode": config["mode"],
            "promotion_config_path": config["promotion_config_path"],
            "target_identity": {
                k: adapter.target.value[k]
                for k in (
                    "inventory_alias",
                    "public_service_address_sha256",
                    "deployable_digest",
                )
            },
            "provider_target_sha256": adapter.target.digest,
        }
        try:
            if config["mode"] == "apply":
                if _reconcile_previous(
                    adapter,
                    guard(sock),
                    strict_guest(
                        aliases[0], Path(config["known_hosts_path"]), candidate
                    ),
                    aliases[0],
                    Path(config["promotion_config_path"]),
                ):
                    _wait_for_terminal_cleanup(process, root, sock, snapshot_path)
                    return {"status": "reconciled"}
            return p.execute(
                request,
                adapter,
                guest=strict_guest(
                    aliases[0], Path(config["known_hosts_path"]), candidate
                ),
                known_hosts=Path(config["known_hosts_path"]),
                selected_host=aliases[0],
            )
        except (Exception, KeyboardInterrupt, SystemExit):
            if config["mode"] == "apply":
                _terminate_unarmed_executor(process, sock, identity)
            raise
    finally:
        adapter.close()
        if config["mode"] == "dry-run":
            terraform_snapshot.remove()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        result = run(load_config(Path(args.config)))
        print(json.dumps(result, sort_keys=True))
        if result.get("status") in {
            "committed-cleanup-debt",
            "committed-rollback-armed",
        }:
            return 1
    except (ControllerError, p.PromotionError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
