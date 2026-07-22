#!/usr/bin/env python3
"""Sentinel-side transactional AWG evidence peer rotation hook."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

KEY = re.compile(rb"[A-Za-z0-9+/]{43}=")
SHA256 = re.compile(r"[0-9a-f]{64}")


def one(config: bytes, name: bytes) -> bytes:
    values = re.findall(rb"(?mi)^\s*" + name + rb"\s*=\s*(.*?)\s*$", config)
    if len(values) != 1 or KEY.fullmatch(values[0]) is None:
        raise ValueError(f"client config must contain one valid {name.decode()}")
    return values[0]


def address(config: bytes) -> str:
    values = re.findall(rb"(?mi)^\s*Address\s*=\s*([^,\s]+)", config)
    if len(values) != 1:
        raise ValueError("client config must contain one Address")
    value = values[0].decode()
    if re.fullmatch(r"10\.66\.77\.[2-9][0-9]?/32", value) is None:
        raise ValueError("client Address is outside the evidence subnet")
    return value


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def atomic(path: Path, raw: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_parent(path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def sync_parent(path: Path) -> None:
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def state_paths(current: Path) -> tuple[Path, Path, Path]:
    return (
        current.parent / ".rotation-state.json",
        current.parent / ".rotation-current.backup",
        current.parent / ".rotation-next.backup",
    )


def successor_path(current: Path) -> Path:
    return current.parent / ".rotation-successor.conf"


def save_state(
    current: Path, phase: str, current_raw: bytes, rotated_raw: bytes
) -> None:
    state, current_backup, rotated_backup = state_paths(current)
    atomic(current_backup, current_raw)
    atomic(rotated_backup, rotated_raw)
    atomic(state, (json.dumps({"phase": phase}, sort_keys=True) + "\n").encode())


def clear_state(current: Path) -> None:
    for path in (*state_paths(current), successor_path(current)):
        path.unlink(missing_ok=True)
    sync_parent(current)


def load_state(current: Path) -> dict[str, str]:
    state, _, _ = state_paths(current)
    value = json.loads(state.read_text())
    if not isinstance(value, dict) or not isinstance(value.get("phase"), str):
        raise ValueError("invalid local rotation state")
    if value["phase"] == "prepared" and set(value) == {"phase"}:
        return dict(value)
    fields = {
        "phase",
        "expectedPromotedClientConfigSha256",
        "successorClientConfigSha256",
    }
    if (
        value["phase"] != "committing"
        or set(value) != fields
        or any(not isinstance(value[field], str) for field in fields)
        or SHA256.fullmatch(value["expectedPromotedClientConfigSha256"]) is None
        or SHA256.fullmatch(value["successorClientConfigSha256"]) is None
    ):
        raise ValueError("invalid local rotation state")
    return dict(value)


def commit_receipt(value: dict, expected: str) -> dict:
    for field in (
        "action",
        "configGenerationSha256",
        "peerConfigSha256",
        "currentClientConfigSha256",
    ):
        if field in value and not isinstance(value[field], str):
            raise ValueError("remote commit receipt has non-string fields")
    if value.get("action", "commit") != "commit":
        raise ValueError("remote commit receipt has invalid action")
    for field in ("configGenerationSha256", "peerConfigSha256"):
        if field in value and SHA256.fullmatch(value[field]) is None:
            raise ValueError("remote commit receipt has invalid digest")
    actual = value.get("currentClientConfigSha256")
    if not isinstance(actual, str) or SHA256.fullmatch(actual) is None:
        raise ValueError("remote commit receipt has invalid promoted digest")
    if actual != expected:
        raise ValueError("remote commit receipt does not match promoted client")
    return value


def rollback_receipt(value: dict) -> dict:
    fields = {
        "action",
        "configGenerationSha256",
        "peerConfigSha256",
        "currentClientConfigSha256",
    }
    if (
        set(value) - {"state"} != fields
        or any(not isinstance(value[field], str) for field in fields)
        or value["action"] != "rollback"
        or any(
            SHA256.fullmatch(value[field]) is None
            for field in (
                "configGenerationSha256",
                "peerConfigSha256",
                "currentClientConfigSha256",
            )
        )
    ):
        raise ValueError("remote rollback receipt is invalid")
    return value


def reconcile_state(value: dict) -> str:
    state = value.get("state")
    if not isinstance(state, str) or state not in {
        "committed",
        "rolled_back",
        "prepared",
        "idle",
    }:
        raise ValueError("remote rotation returned invalid reconciliation state")
    return state


def restore_local(
    current: Path, rotated: Path, current_backup: Path, rotated_backup: Path
) -> None:
    atomic(current, current_backup.read_bytes())
    atomic(rotated, rotated_backup.read_bytes())


def promote_local(
    current: Path,
    rotated: Path,
    promoted_backup: Path,
    successor: Path,
    expected_promoted: str,
    expected_successor: str,
) -> None:
    promoted = promoted_backup.read_bytes()
    successor_raw = successor.read_bytes()
    if sha(promoted) != expected_promoted or sha(successor_raw) != expected_successor:
        raise ValueError("local rotation recovery material has changed")
    atomic(current, promoted)
    atomic(rotated, successor_raw)


def run_ssh(ssh: list[str], command: str, payload: bytes = b"") -> dict:
    completed = subprocess.run(
        [*ssh, command],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=120,
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("remote rotation returned a non-object")
    return value


def recover_interrupted(current: Path, rotated: Path, ssh: list[str]) -> None:
    state, current_backup, rotated_backup = state_paths(current)
    if not state.exists():
        return
    local = load_state(current)
    if not current_backup.is_file() or not rotated_backup.is_file():
        raise ValueError("local rotation recovery material is missing")
    remote = run_ssh(ssh, "rotation reconcile")
    remote_state = reconcile_state(remote)
    if remote_state == "rolled_back":
        rollback_receipt(remote)
        restore_local(current, rotated, current_backup, rotated_backup)
        clear_state(current)
        return
    if local["phase"] == "committing":
        expected = local["expectedPromotedClientConfigSha256"]
        next_path = successor_path(current)
        if not next_path.is_file():
            raise ValueError("local rotation successor is missing")
        if remote_state == "committed":
            commit_receipt(remote, expected)
            promote_local(
                current,
                rotated,
                rotated_backup,
                next_path,
                expected,
                local["successorClientConfigSha256"],
            )
            clear_state(current)
            return
        if (
            remote_state == "prepared"
            and remote.get("currentClientConfigSha256") == expected
        ):
            receipt = commit_receipt(run_ssh(ssh, "rotation commit"), expected)
            promote_local(
                current,
                rotated,
                rotated_backup,
                next_path,
                expected,
                local["successorClientConfigSha256"],
            )
            try:
                acknowledged = commit_receipt(
                    run_ssh(ssh, "rotation acknowledge"), expected
                )
                if acknowledged != receipt:
                    raise ValueError("remote acknowledge receipt changed")
            except Exception as acknowledge_error:
                try:
                    reconciled = run_ssh(ssh, "rotation reconcile")
                    reconciled_state = reconcile_state(reconciled)
                except Exception:
                    raise acknowledge_error
                if reconciled_state != "committed":
                    raise acknowledge_error
                commit_receipt(reconciled, expected)
            clear_state(current)
            return
    run_ssh(ssh, "rotation rollback")
    restore_local(current, rotated, current_backup, rotated_backup)
    clear_state(current)


def generate_successor(template: bytes) -> bytes:
    private = subprocess.run(
        ["awg", "genkey"], check=True, stdout=subprocess.PIPE, timeout=30
    ).stdout.strip()
    psk = subprocess.run(
        ["awg", "genpsk"], check=True, stdout=subprocess.PIPE, timeout=30
    ).stdout.strip()
    if KEY.fullmatch(private) is None or KEY.fullmatch(psk) is None:
        raise ValueError("awg generated malformed credentials")
    updated, private_count = re.subn(
        rb"(?mi)^(\s*PrivateKey\s*=\s*).*?$", rb"\g<1>" + private, template
    )
    updated, psk_count = re.subn(
        rb"(?mi)^(\s*PresharedKey\s*=\s*).*?$", rb"\g<1>" + psk, updated
    )
    if private_count != 1 or psk_count != 1:
        raise ValueError("cannot update successor client config")
    return updated


def prepare(current: Path, rotated: Path, ssh: list[str]) -> dict:
    recover_interrupted(current, rotated, ssh)
    current_raw = current.read_bytes()
    raw = rotated.read_bytes()
    private = one(raw, b"PrivateKey")
    public = subprocess.run(
        ["awg", "pubkey"],
        input=private + b"\n",
        check=True,
        stdout=subprocess.PIPE,
        timeout=30,
    ).stdout.strip()
    if KEY.fullmatch(public) is None:
        raise ValueError("awg returned malformed public key")
    payload = {
        "clientPublicKey": public.decode(),
        "presharedKey": one(raw, b"PresharedKey").decode(),
        "allowedIps": address(raw),
        "rotatedClientConfigSha256": sha(raw),
    }
    save_state(current, "prepared", current_raw, raw)
    try:
        return run_ssh(
            ssh,
            "rotation prepare",
            (
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode(),
        )
    except Exception as prepare_error:
        try:
            run_ssh(ssh, "rotation rollback")
        except Exception:
            # The prepare may have reached the server; keep backups so the
            # next invocation can reconcile instead of guessing.
            raise prepare_error
        clear_state(current)
        raise prepare_error


def finalize(action: str, current: Path, rotated: Path, ssh: list[str]) -> dict:
    state, current_backup, rotated_backup = state_paths(current)
    if action == "rollback":
        receipt = rollback_receipt(run_ssh(ssh, "rotation rollback"))
        if current_backup.is_file() and rotated_backup.is_file():
            atomic(current, current_backup.read_bytes())
            atomic(rotated, rotated_backup.read_bytes())
        clear_state(current)
        receipt["currentClientConfigSha256"] = sha(current.read_bytes())
        return receipt
    if (
        not state.is_file()
        or not current_backup.is_file()
        or not rotated_backup.is_file()
    ):
        raise ValueError("local rotation transaction is missing")
    promoted = rotated.read_bytes()
    successor = generate_successor(promoted)
    expected = sha(promoted)
    expected_successor = sha(successor)
    atomic(successor_path(current), successor)
    atomic(
        state,
        (
            json.dumps(
                {
                    "phase": "committing",
                    "expectedPromotedClientConfigSha256": expected,
                    "successorClientConfigSha256": expected_successor,
                },
                sort_keys=True,
            )
            + "\n"
        ).encode(),
    )
    try:
        receipt = commit_receipt(run_ssh(ssh, "rotation commit"), expected)
        promote_local(
            current,
            rotated,
            rotated_backup,
            successor_path(current),
            expected,
            expected_successor,
        )
        try:
            acknowledged = run_ssh(ssh, "rotation acknowledge")
            commit_receipt(acknowledged, expected)
            if acknowledged != receipt:
                raise ValueError("remote acknowledge receipt changed")
        except Exception as acknowledge_error:
            try:
                reconciled = run_ssh(ssh, "rotation reconcile")
                reconciled_state = reconcile_state(reconciled)
            except Exception:
                raise acknowledge_error
            if reconciled_state != "committed":
                raise acknowledge_error
            commit_receipt(reconciled, expected)
        clear_state(current)
        return receipt
    except Exception:
        try:
            rollback = run_ssh(ssh, "rotation rollback")
        except Exception:
            # Preserve all recovery material when remote state is uncertain.
            raise
        else:
            if rollback.get("action") == "commit":
                commit_receipt(rollback, expected)
                clear_state(current)
                return receipt
            restore_local(current, rotated, current_backup, rotated_backup)
            clear_state(current)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "commit", "rollback"))
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--rotated", type=Path, required=True)
    parser.add_argument("--ssh", nargs="+", required=True)
    args = parser.parse_args()
    try:
        value = (
            prepare(args.current, args.rotated, args.ssh)
            if args.action == "prepare"
            else finalize(args.action, args.current, args.rotated, args.ssh)
        )
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"real-vps-awg-nat-rotation: remote command failed", file=os.sys.stderr)
        return 75 if exc.returncode == 75 else 70
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"real-vps-awg-nat-rotation: {exc}", file=os.sys.stderr)
        return 75
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"real-vps-awg-nat-rotation: {exc}", file=os.sys.stderr)
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
