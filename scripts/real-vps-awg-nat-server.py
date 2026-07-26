#!/usr/bin/env python3
"""Fixed-command server half of the real-VPS AWG/NAT evidence lane."""

from __future__ import annotations

import hashlib
import ipaddress
import io
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SHA1 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
WG_KEY = re.compile(r"[A-Za-z0-9+/]{43}=")
STATE = Path("/var/lib/ripdpi-real-vps-awg-nat-server")
CONFIG = Path("/etc/amneziawg/awg-evidence0.conf")
SERVICE = "awg-quick@awg-evidence0.service"
NAT_COMMENT = "awg-nat-awg-evidence0"
SOURCE_ROOT = Path("/opt/ripdpi-real-vps-awg-nat-server")
RECORD = STATE / "deployment.json"
PRIVATE_VARS = Path("/etc/ripdpi/real-vps-awg-nat-server.yml")
SOURCE_POLICY = Path("/etc/ripdpi/real-vps-awg-nat-source-policy.json")
SERVER_PATH = Path(__file__).resolve()


class ProductFailure(RuntimeError):
    """The applied server product state did not satisfy the lane contract."""


class InfrastructureUnavailable(RuntimeError):
    """A prerequisite or remote-control transport is unavailable."""


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def peer_digest(psk: bytes) -> str:
    return digest(b"ripdpi:awg-evidence-peer:v1:" + psk)


def parse_forced_command(command: str) -> tuple[str, list[str]]:
    try:
        parts = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError("malformed forced command") from exc
    if parts in (["status"], ["restart"], ["reload"]):
        return parts[0], []
    if (
        len(parts) == 2
        and parts[0] == "rotation"
        and parts[1]
        in {
            "prepare",
            "commit",
            "rollback",
            "acknowledge",
            "reconcile",
        }
    ):
        return "rotation", [parts[1]]
    if (
        len(parts) == 3
        and parts[0] == "deploy"
        and SHA1.fullmatch(parts[1])
        and SHA256.fullmatch(parts[2])
    ):
        return "deploy", parts[1:]
    raise ValueError("unsupported forced command")


def validate_archive_members(members: Iterable[Any]) -> None:
    required = False
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("source archive contains an unsafe member")
        is_link = bool(getattr(member, "issym", lambda: False)())
        if is_link:
            link = PurePosixPath(member.linkname)
            resolved = posixpath.normpath((path.parent / link).as_posix())
            if link.is_absolute() or resolved == ".." or resolved.startswith("../"):
                raise ValueError("source archive contains an unsafe link")
        elif not (member.isreg() or member.isdir()):
            raise ValueError("source archive contains an unsafe member")
        if path == PurePosixPath("scripts/real-vps-awg-nat-server.py"):
            required = member.isreg()
    if not required:
        raise ValueError("source archive lacks the server hook")


def validate_rotation_payload(value: Any, expected_allowed_ips: str) -> dict[str, str]:
    fields = {
        "clientPublicKey",
        "presharedKey",
        "allowedIps",
        "rotatedClientConfigSha256",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or any(not isinstance(value[field], str) for field in fields)
    ):
        raise ValueError("invalid rotation payload fields")
    if not WG_KEY.fullmatch(value["clientPublicKey"]):
        raise ValueError("invalid client public key")
    if not WG_KEY.fullmatch(value["presharedKey"]):
        raise ValueError("invalid preshared key")
    if value["allowedIps"] != expected_allowed_ips:
        raise ValueError("invalid evidence peer address")
    if not SHA256.fullmatch(value["rotatedClientConfigSha256"]):
        raise ValueError("invalid rotated config digest")
    return dict(value)


def validate_rotation_receipt(value: Any) -> dict[str, str]:
    fields = {
        "previousConfigGenerationSha256",
        "nextConfigGenerationSha256",
        "previousPeerConfigSha256",
        "nextPeerConfigSha256",
        "rotatedClientConfigSha256",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or any(not isinstance(value[field], str) for field in fields)
        or any(SHA256.fullmatch(value[field]) is None for field in fields)
    ):
        raise ValueError("invalid rotation receipt")
    return dict(value)


def rotation_receipt(
    *,
    previous_config: bytes,
    next_config: bytes,
    previous_psk: bytes,
    next_psk: bytes,
    rotated_client_sha: str,
) -> dict[str, str]:
    return {
        "previousConfigGenerationSha256": digest(previous_config),
        "nextConfigGenerationSha256": digest(next_config),
        "previousPeerConfigSha256": peer_digest(previous_psk),
        "nextPeerConfigSha256": peer_digest(next_psk),
        "rotatedClientConfigSha256": rotated_client_sha,
    }


def committed_rotation(receipt: dict[str, str]) -> dict[str, str]:
    return {
        "action": "commit",
        "configGenerationSha256": receipt["nextConfigGenerationSha256"],
        "peerConfigSha256": receipt["nextPeerConfigSha256"],
        "currentClientConfigSha256": receipt["rotatedClientConfigSha256"],
    }


def rolled_back_rotation(receipt: dict[str, str]) -> dict[str, str]:
    return {
        "action": "rollback",
        "configGenerationSha256": receipt["previousConfigGenerationSha256"],
        "peerConfigSha256": receipt["previousPeerConfigSha256"],
        "currentClientConfigSha256": "0" * 64,
    }


def rotation_outcome(state: str, receipt: dict[str, str]) -> dict[str, Any]:
    if state not in {"committed", "rolled_back"}:
        raise ValueError("invalid rotation outcome state")
    return {"state": state, "receipt": receipt}


def validate_rotation_outcome(value: Any) -> tuple[str, dict[str, str]]:
    if (
        not isinstance(value, dict)
        or set(value) != {"state", "receipt"}
        or not isinstance(value["state"], str)
        or value["state"] not in {"committed", "rolled_back"}
    ):
        raise ValueError("invalid rotation outcome")
    return value["state"], validate_rotation_receipt(value["receipt"])


def atomic_write(path: Path, raw: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_parent(path)
    finally:
        Path(name).unlink(missing_ok=True)


def sync_parent(path: Path) -> None:
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def remove_rotation_files(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
    if paths:
        sync_parent(paths[0])


def recover_orphaned_prepare(
    pending: Path,
    previous: Path,
    transaction: Path,
    rollback_intent: Path,
) -> bool:
    """Discard staging files that cannot belong to a durable transaction."""
    if transaction.exists() or rollback_intent.exists():
        return False
    if not pending.exists() and not previous.exists():
        return False
    remove_rotation_files(pending, previous)
    return True


def finish_server_rollback(
    *,
    receipt: dict[str, str],
    pending: Path,
    previous: Path,
    transaction: Path,
    intent: Path,
    outcome: Path,
) -> dict[str, str]:
    if not previous.is_file():
        raise ProductFailure("rotation rollback material is missing")
    previous_raw = previous.read_bytes()
    if digest(previous_raw) != receipt["previousConfigGenerationSha256"]:
        raise ProductFailure("rotation rollback material has changed")
    current_digest = digest(CONFIG.read_bytes())
    if current_digest not in {
        receipt["previousConfigGenerationSha256"],
        receipt["nextConfigGenerationSha256"],
    }:
        raise ProductFailure("server config is outside the rotation transaction")
    atomic_write(CONFIG, previous_raw)
    try:
        run("systemctl", "reload", SERVICE)
    except subprocess.SubprocessError as exc:
        raise ProductFailure("server rollback reload failed") from exc
    result = rolled_back_rotation(receipt)
    atomic_write(outcome, canonical(rotation_outcome("rolled_back", receipt)))
    remove_rotation_files(pending, previous, intent, transaction)
    return result


def tree_digest(root: Path) -> str:
    state = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            state.update(b"L\0" + relative + b"\0" + os.readlink(path).encode() + b"\0")
        elif path.is_dir():
            state.update(b"D\0" + relative + b"\0")
        elif path.is_file():
            state.update(b"F\0" + relative + b"\0" + path.read_bytes())
        else:
            raise ProductFailure("extracted source contains a special file")
    return state.hexdigest()


def validate_snapshot_permissions(root: Path) -> None:
    owner = os.geteuid()
    resolved_root = root.resolve()
    for path in [root, *root.rglob("*")]:
        info = path.lstat()
        if path.is_symlink():
            try:
                path.resolve(strict=True).relative_to(resolved_root)
            except (FileNotFoundError, ValueError) as exc:
                raise ProductFailure("source snapshot symlink is unsafe") from exc
            if info.st_uid != owner:
                raise ProductFailure("source snapshot ownership or mode is unsafe")
            continue
        if info.st_uid != owner or info.st_mode & 0o022:
            raise ProductFailure("source snapshot ownership or mode is unsafe")


def validate_private_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise InfrastructureUnavailable("private exact-source vars are missing")
    info = path.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise InfrastructureUnavailable(
            "private exact-source vars ownership or mode is unsafe"
        )


def source_policy() -> dict[str, str]:
    validate_private_file(SOURCE_POLICY)
    value = json.loads(SOURCE_POLICY.read_text())
    fields = {
        "clientAllowedIps",
        "sourceSha",
        "sourceArchiveSha256",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or any(not isinstance(value[field], str) for field in fields)
    ):
        raise ValueError("source allowlist policy is malformed")
    if not SHA1.fullmatch(value["sourceSha"]) or not SHA256.fullmatch(
        value["sourceArchiveSha256"]
    ):
        raise ValueError("source allowlist policy is malformed")
    try:
        client = ipaddress.ip_interface(value["clientAllowedIps"])
    except ValueError as exc:
        raise ValueError("source allowlist policy is malformed") from exc
    if client.network.prefixlen != client.max_prefixlen:
        raise ValueError("source allowlist policy is malformed")
    value["clientAllowedIps"] = str(client)
    return dict(value)


def run(
    *command: str,
    input_bytes: bytes | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=timeout,
        cwd=cwd,
        env=env,
    )


def extract_psk(config: bytes) -> bytes:
    values = re.findall(rb"(?mi)^\s*PresharedKey\s*=\s*(.*?)\s*$", config)
    if len(values) != 1 or WG_KEY.fullmatch(values[0].decode()) is None:
        raise ValueError("server config must contain one evidence preshared key")
    return values[0]


def render_rotated_config(current: bytes, payload: dict[str, str]) -> bytes:
    text = current.decode()
    start = text.find("# BEGIN RIPDPI AWG EVIDENCE PEER\n")
    end_marker = "# END RIPDPI AWG EVIDENCE PEER\n"
    end = text.find(end_marker)
    if start < 0 or end < start:
        raise ValueError("server config lacks the managed evidence peer block")
    end += len(end_marker)
    block = (
        "# BEGIN RIPDPI AWG EVIDENCE PEER\n"
        "[Peer]\n"
        f"PublicKey = {payload['clientPublicKey']}\n"
        f"PresharedKey = {payload['presharedKey']}\n"
        f"AllowedIPs = {payload['allowedIps']}\n"
        "# END RIPDPI AWG EVIDENCE PEER\n"
    )
    return (text[:start] + block + text[end:]).encode()


def deploy(source_sha: str, expected_digest: str, archive: bytes) -> dict[str, str]:
    allowed = source_policy()
    if (
        source_sha != allowed["sourceSha"]
        or expected_digest != allowed["sourceArchiveSha256"]
    ):
        raise ProductFailure("source archive is not operator-approved")
    if digest(archive) != expected_digest:
        raise ValueError("source archive digest mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as source:
        members = source.getmembers()
        validate_archive_members(members)
        staging = Path(tempfile.mkdtemp(prefix=".deploy-", dir=SOURCE_ROOT))
        try:
            source.extractall(staging, members=members, filter="data")
            target = SOURCE_ROOT / "sources" / f"{source_sha}-{expected_digest}"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise ProductFailure("existing source target is unsafe")
            if target.exists():
                if tree_digest(target) != tree_digest(staging):
                    raise ProductFailure("existing source snapshot was modified")
            else:
                os.replace(staging, target)
                for root, directories, files in os.walk(target):
                    os.chmod(root, os.stat(root).st_mode & ~0o022)
                    for name in [*directories, *files]:
                        path = Path(root) / name
                        if not path.is_symlink():
                            os.chmod(path, os.stat(path).st_mode & ~0o022)
            validate_snapshot_permissions(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    target = SOURCE_ROOT / "sources" / f"{source_sha}-{expected_digest}"
    playbook = target / "ansible/playbooks/provision-real-vps-awg-nat-server-local.yml"
    if playbook.is_symlink() or not playbook.is_file():
        raise InfrastructureUnavailable("exact-source apply prerequisites are missing")
    validate_private_file(PRIVATE_VARS)
    try:
        run(
            "ansible-playbook",
            "-i",
            "localhost,",
            "-c",
            "local",
            "playbooks/provision-real-vps-awg-nat-server-local.yml",
            "--extra-vars",
            f"@{PRIVATE_VARS}",
            cwd=target / "ansible",
            env={**os.environ, "ANSIBLE_CONFIG": str(target / "ansible/ansible.cfg")},
            timeout=840,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProductFailure("exact-source Ansible apply failed") from exc
    current_tmp = SOURCE_ROOT / ".current.tmp"
    current = SOURCE_ROOT / "current"
    if current_tmp.exists() or current_tmp.is_symlink():
        current_tmp.unlink()
    current_tmp.symlink_to(Path("sources") / f"{source_sha}-{expected_digest}")
    os.replace(current_tmp, current)
    receipt = {
        "deployedSourceSha": source_sha,
        "deployedArchiveSha256": expected_digest,
    }
    atomic_write(RECORD, canonical(receipt))
    return receipt


def deployment() -> dict[str, str]:
    value = json.loads(RECORD.read_text())
    fields = {"deployedSourceSha", "deployedArchiveSha256"}
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or any(not isinstance(value[field], str) for field in fields)
        or SHA1.fullmatch(value["deployedSourceSha"]) is None
        or SHA256.fullmatch(value["deployedArchiveSha256"]) is None
    ):
        raise ValueError("invalid deployment record")
    return dict(value)


def nft_counter() -> tuple[int, int]:
    value = json.loads(run("nft", "-j", "list", "ruleset").stdout)
    matches: list[tuple[int, int]] = []
    for item in value.get("nftables", []):
        rule = item.get("rule", {})
        if rule.get("comment") != NAT_COMMENT:
            continue
        packets = bytes_ = None
        for expression in rule.get("expr", []):
            if "counter" in expression:
                packets = expression["counter"].get("packets")
                bytes_ = expression["counter"].get("bytes")
        if isinstance(packets, int) and isinstance(bytes_, int):
            matches.append((packets, bytes_))
    if len(matches) != 1:
        return 0, 0
    return matches[0]


def status() -> dict[str, Any]:
    for dependency in ("systemctl", "awg", "nft"):
        if shutil.which(dependency) is None:
            raise InfrastructureUnavailable(
                f"missing server prerequisite: {dependency}"
            )
    record = deployment()
    config = CONFIG.read_bytes()
    psk = extract_psk(config)
    service_fields = {}
    for line in (
        run("systemctl", "show", SERVICE, "--property=ActiveState,InvocationID")
        .stdout.decode()
        .splitlines()
    ):
        key, separator, value = line.partition("=")
        if separator:
            service_fields[key] = value
    if set(service_fields) != {"ActiveState", "InvocationID"}:
        raise ValueError("invalid systemd status")
    awg_process = subprocess.run(
        ["awg", "show", "awg-evidence0", "dump"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=30,
    )
    awg = (
        awg_process.stdout.decode().splitlines() if awg_process.returncode == 0 else []
    )
    peer = next((line for line in awg[1:] if len(line.split("\t")) >= 8), None)
    fields = (
        peer.split("\t") if peer is not None else ["", "", "", "", "0", "0", "0", ""]
    )
    packets, bytes_ = nft_counter()
    return {
        "serviceActive": service_fields["ActiveState"] == "active",
        "interfaceUp": bool(awg),
        **record,
        "serviceInvocationSha256": digest(service_fields["InvocationID"].encode()),
        "configGenerationSha256": digest(config),
        "peerConfigSha256": peer_digest(psk),
        "latestHandshakeEpoch": int(fields[4]),
        "peerRxBytes": int(fields[5]),
        "peerTxBytes": int(fields[6]),
        "natPackets": packets,
        "natBytes": bytes_,
    }


def rotation(action: str, stdin: bytes) -> dict[str, str]:
    pending = STATE / "pending.conf"
    previous = STATE / "previous.conf"
    transaction = STATE / "transaction.json"
    rollback_intent = STATE / "rollback-intent.json"
    outcome = STATE / "rotation-outcome.json"
    recover_orphaned_prepare(pending, previous, transaction, rollback_intent)
    if action == "prepare":
        if pending.exists() or transaction.exists() or rollback_intent.exists():
            raise ValueError("rotation transaction already exists")
        payload = validate_rotation_payload(
            json.loads(stdin), source_policy()["clientAllowedIps"]
        )
        current = CONFIG.read_bytes()
        next_config = render_rotated_config(current, payload)
        receipt = rotation_receipt(
            previous_config=current,
            next_config=next_config,
            previous_psk=extract_psk(current),
            next_psk=payload["presharedKey"].encode(),
            rotated_client_sha=payload["rotatedClientConfigSha256"],
        )
        atomic_write(previous, current)
        atomic_write(pending, next_config)
        atomic_write(transaction, canonical(receipt))
        return receipt
    if action == "reconcile":
        pending_receipt = (
            validate_rotation_receipt(json.loads(transaction.read_text()))
            if transaction.exists()
            else None
        )
        final_outcome = (
            validate_rotation_outcome(json.loads(outcome.read_text()))
            if outcome.exists()
            else None
        )
        if final_outcome is not None and (
            pending_receipt is None or final_outcome[1] == pending_receipt
        ):
            state, receipt = final_outcome
            result = (
                committed_rotation(receipt)
                if state == "committed"
                else rolled_back_rotation(receipt)
            )
            if pending_receipt is not None:
                remove_rotation_files(pending, previous, rollback_intent, transaction)
            return {"state": state, **result}
        if pending_receipt is not None and rollback_intent.exists():
            intent_receipt = validate_rotation_receipt(
                json.loads(rollback_intent.read_text())
            )
            if intent_receipt != pending_receipt:
                raise ProductFailure(
                    "rotation rollback intent does not match transaction"
                )
            result = finish_server_rollback(
                receipt=pending_receipt,
                pending=pending,
                previous=previous,
                transaction=transaction,
                intent=rollback_intent,
                outcome=outcome,
            )
            return {"state": "rolled_back", **result}
        if pending_receipt is not None:
            return {
                "state": "prepared",
                "currentClientConfigSha256": pending_receipt[
                    "rotatedClientConfigSha256"
                ],
            }
        if rollback_intent.exists():
            raise ProductFailure("orphaned rotation rollback intent")
        return {"state": "idle"}
    if not transaction.exists():
        if action != "rollback":
            raise ProductFailure("rotation transaction does not exist")
        if outcome.exists():
            state, receipt = validate_rotation_outcome(json.loads(outcome.read_text()))
            remove_rotation_files(pending, previous, rollback_intent)
            return (
                committed_rotation(receipt)
                if state == "committed"
                else rolled_back_rotation(receipt)
            )
        if rollback_intent.exists():
            raise ProductFailure("orphaned rotation rollback intent")
        current = CONFIG.read_bytes()
        remove_rotation_files(pending, previous)
        return {
            "action": "rollback",
            "configGenerationSha256": digest(current),
            "peerConfigSha256": peer_digest(extract_psk(current)),
            "currentClientConfigSha256": "0" * 64,
        }
    receipt = validate_rotation_receipt(json.loads(transaction.read_text()))
    if action == "commit":
        if digest(CONFIG.read_bytes()) != receipt["nextConfigGenerationSha256"]:
            raise ValueError("cannot commit an unapplied rotation")
        return committed_rotation(receipt)
    if action == "acknowledge":
        if digest(CONFIG.read_bytes()) != receipt["nextConfigGenerationSha256"]:
            raise ProductFailure("cannot acknowledge an unapplied rotation")
        # This tombstone is the durable commit point.  Reconciliation must be
        # able to prove the commit even if the SSH response or cleanup is lost.
        atomic_write(outcome, canonical(rotation_outcome("committed", receipt)))
        remove_rotation_files(pending, previous, transaction)
        return committed_rotation(receipt)
    if action == "rollback":
        if outcome.exists():
            state, final_receipt = validate_rotation_outcome(
                json.loads(outcome.read_text())
            )
            if state == "rolled_back" and final_receipt == receipt:
                remove_rotation_files(pending, previous, rollback_intent, transaction)
                return rolled_back_rotation(receipt)
        # Intent distinguishes rollback recovery from an ordinary prepared
        # transaction whose live config is also still the previous generation.
        atomic_write(rollback_intent, canonical(receipt))
        return finish_server_rollback(
            receipt=receipt,
            pending=pending,
            previous=previous,
            transaction=transaction,
            intent=rollback_intent,
            outcome=outcome,
        )
    raise ValueError("invalid rotation action")


def dispatch(command: str, args: list[str], stdin: bytes) -> dict[str, Any] | None:
    if command == "deploy":
        return deploy(args[0], args[1], stdin)
    if command == "status":
        return status()
    if command == "restart":
        try:
            run("systemctl", "restart", SERVICE)
        except subprocess.SubprocessError as exc:
            raise ProductFailure("server restart failed") from exc
        return None
    if command == "reload":
        pending = STATE / "pending.conf"
        if not pending.is_file():
            raise ValueError("no prepared rotation")
        atomic_write(CONFIG, pending.read_bytes())
        try:
            run("systemctl", "reload", SERVICE)
        except subprocess.SubprocessError as exc:
            raise ProductFailure("server reload failed") from exc
        return None
    if command == "rotation":
        return rotation(args[0], stdin)
    raise ValueError("unsupported command")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "--forced":
        print("fixed forced-command entrypoint only", file=sys.stderr)
        return 64
    try:
        command, args = parse_forced_command(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
        stdin = sys.stdin.buffer.read(64 * 1024 * 1024 + 1)
        if len(stdin) > 64 * 1024 * 1024:
            raise ValueError("input exceeds fixed maximum")
        result = dispatch(command, args, stdin)
        if result is not None:
            sys.stdout.buffer.write(canonical(result))
        return 0
    except ProductFailure as exc:
        print(f"real-vps-awg-nat-server: {exc}", file=sys.stderr)
        return 70
    except InfrastructureUnavailable as exc:
        print(f"real-vps-awg-nat-server: {exc}", file=sys.stderr)
        return 75
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"real-vps-awg-nat-server: {exc}", file=sys.stderr)
        return 70
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"real-vps-awg-nat-server: {exc}", file=sys.stderr)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
