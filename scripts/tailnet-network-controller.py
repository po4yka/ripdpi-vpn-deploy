#!/usr/bin/env python3
"""Operator composition root for one Tailnet promotion and its rollback daemon."""

from __future__ import annotations

import argparse
import base64
import fcntl
import importlib.util
import json
import os
from pathlib import Path
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


def module():
    spec = importlib.util.spec_from_file_location(
        "tailnet_network_promotion", PROMOTION_PATH
    )
    value = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(value)
    return value


p = module()


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
    fd = -1
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
            pass
        fd = os.open(
            path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
    finally:
        os.close(parent)
    if fd < 0:
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
                client.settimeout(5)
                client.connect(str(socket_path))
                client.sendall(payload)
                client.shutdown(socket.SHUT_WR)
                raw = client.recv(MAX + 1)
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


def _live_executor(socket_path: Path, target_digest: str):
    try:
        value = guard(socket_path)("ping", {})
        return value == {"provider_target_sha256": target_digest}
    except p.PromotionError:
        return False


def _remove_verified_stale_executor(
    root: Path, socket_path: Path, target_digest: str, *, socket_required=True
):
    """Only unlink a dead, same-target daemon socket with its private pid record."""
    pid_path = root / "daemon.json"
    fd = private(pid_path)
    try:
        value = json.loads(os.read(fd, MAX + 1))
    finally:
        os.close(fd)
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "pid", "provider_target_sha256"}
        or value.get("schema_version") != 1
        or type(value.get("pid")) is not int
        or value.get("provider_target_sha256") != target_digest
    ):
        raise ControllerError("executor-stale-refused")
    try:
        os.kill(value["pid"], 0)
    except ProcessLookupError:
        pass
    except PermissionError:
        raise ControllerError("executor-stale-refused") from None
    else:
        raise ControllerError("executor-unreachable")
    if socket_required:
        info = socket_path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            raise ControllerError("executor-stale-refused")
        socket_path.unlink()
    pid_path.unlink()


def strict_guest(host, known_hosts, candidate: bytes):
    """Fixed helper command, private fragment on stdin, strict pinned SSH only."""
    if len(candidate) > MAX:
        raise p.PromotionError("guest-uncertain")

    def call(_host, action, identity, cleanup):
        if action == "prepare":
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
            timeout=90,
        )
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise p.PromotionError("guest-uncertain") from None

    return call


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
    fds = [private(target), private(state), private(terraform, executable=True)]
    try:
        # Validate the three opened inodes in this composition root before daemon spawn.
        validated_target = p.ProviderTarget(fds[0], fds[1])
        validated_tf = p.TrustedTerraform(fds[2], config["terraform_sha256"])
        target_digest = validated_target.digest
        validated_target.close()
        validated_tf.close()
        fds = []
    finally:
        for fd in fds:
            try:
                os.close(fd)
            except OSError:
                pass
    candidate_fd = private(Path(config["candidate_fragment_path"]))
    try:
        candidate = os.read(candidate_fd, MAX + 1)
    finally:
        os.close(candidate_fd)
    if len(candidate) > MAX:
        raise ControllerError("candidate-refused")
    root = Path(config["executor_dir"])
    private_directory(root)
    sock = root / "executor.sock"
    if config["mode"] == "apply":
        if sock.exists() or sock.is_symlink():
            if not _live_executor(sock, target_digest):
                _remove_verified_stale_executor(root, sock, target_digest)
        elif (root / "daemon.json").exists():
            # A process can die after durable PID identity write but before
            # socket bind.  Reuse the same verified stale-artifact cleanup.
            _remove_verified_stale_executor(
                root, sock, target_digest, socket_required=False
            )
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
                    "--receipt-dir",
                    str(root),
                    "--socket",
                    str(sock),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            for _ in range(50):
                if sock.exists():
                    break
                if process.poll() is not None:
                    raise ControllerError("executor-unavailable")
                time.sleep(0.1)
            else:
                raise ControllerError("executor-unavailable")
    adapter = p.TerraformAdapter(
        p.ProviderTarget(private(target), private(state)),
        trusted_terraform=p.TrustedTerraform(
            private(terraform, executable=True), config["terraform_sha256"]
        ),
        external_rollback_guard=guard(sock),
        provider_transaction_lock=lambda: provider_transaction_lock(root),
        allow_apply=config["mode"] == "apply",
    )
    if config["mode"] == "apply":
        token = os.environ.get("UPCLOUD_TOKEN")
        if not token:
            raise ControllerError("provider-credentials-unavailable")
        adapter.environment_map = {**adapter.environment_map, "UPCLOUD_TOKEN": token}

    def return_path(action, identity):
        if action not in {"forward", "readback"}:
            raise p.PromotionError("provider-return-path-invalid")
        if action == "forward":
            return True
        try:
            state_value = json.loads(adapter._command(["state", "pull"]))
            resource = next(
                item
                for item in state_value["resources"]
                if item.get("type") == "upcloud_server" and item.get("name") == "vpn"
            )
            firewall = resource["instances"][0]["attributes"]["firewall"]
        except (
            KeyError,
            IndexError,
            StopIteration,
            TypeError,
            ValueError,
            p.PromotionError,
        ):
            raise p.PromotionError("provider-readback-invalid") from None
        if type(firewall) is not bool:
            raise p.PromotionError("provider-readback-invalid")
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
    return p.execute(
        request,
        adapter,
        guest=strict_guest(aliases[0], Path(config["known_hosts_path"]), candidate),
        known_hosts=Path(config["known_hosts_path"]),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(load_config(Path(args.config))), sort_keys=True))
    except (ControllerError, p.PromotionError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
