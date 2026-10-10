#!/usr/bin/env python3
"""Read bounded named systemd service, timer and target ownership state."""

from __future__ import annotations

import json
import re
import subprocess
import sys

UNIT = re.compile(r"[A-Za-z0-9_.@:-]{1,160}[.](?:service|timer|target)\Z")


def inspect(names: list[str]) -> dict:
    if (
        not isinstance(names, list)
        or len(names) > 64
        or any(
            not isinstance(name, str) or UNIT.fullmatch(name) is None for name in names
        )
        or len(set(names)) != len(names)
    ):
        raise ValueError("unit request")
    states = {}
    for name in names:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                name,
                "--property=LoadState,ActiveState,UnitFileState",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if len(result.stdout) > 4096:
            raise ValueError("unit response")
        values = {}
        for line in result.stdout.splitlines():
            key, separator, value = line.partition("=")
            if (
                not separator
                or key not in {"LoadState", "ActiveState", "UnitFileState"}
                or key in values
            ):
                raise ValueError("unit response")
            values[key] = value
        load = values.get("LoadState")
        active = values.get("ActiveState")
        enabled = values.get("UnitFileState") or (
            "not-found" if load == "not-found" else ""
        )
        if (
            result.returncode
            and load != "not-found"
            or load not in {"loaded", "not-found", "masked"}
            or active not in {"active", "inactive", "failed"}
            or enabled
            not in {
                "enabled",
                "enabled-runtime",
                "disabled",
                "static",
                "indirect",
                "not-found",
                "masked",
                "masked-runtime",
            }
        ):
            raise ValueError("unit state")
        states[name] = {
            "exists": load != "not-found",
            "active": active == "active",
            "enabled": enabled in {"enabled", "enabled-runtime"},
            "unit_file_state": enabled,
        }
    return states


def restore(states: dict) -> None:
    if not isinstance(states, dict):
        raise ValueError("unit restore")
    names = list(states)
    inspect(names)  # Validate all names before any lifecycle command.
    allowed = {
        "enabled",
        "enabled-runtime",
        "disabled",
        "static",
        "indirect",
        "not-found",
        "masked",
        "masked-runtime",
    }
    for row in states.values():
        if (
            not isinstance(row, dict)
            or set(row) != {"exists", "active", "enabled", "unit_file_state"}
            or any(
                type(row[field]) is not bool
                for field in ("exists", "active", "enabled")
            )
            or not isinstance(row["unit_file_state"], str)
            or row["unit_file_state"] not in allowed
            or row["enabled"]
            != (row["unit_file_state"] in {"enabled", "enabled-runtime"})
        ):
            raise ValueError("unit restore")

    def command(*arguments):
        result = subprocess.run(
            ["systemctl", *arguments], capture_output=True, timeout=10
        )
        if result.returncode:
            raise ValueError("unit restore")

    command("daemon-reload")
    current = inspect(names)
    for name, prior in states.items():
        if not prior["exists"]:
            if current[name]["exists"]:
                raise ValueError("unit remains")
            continue
        if current[name]["unit_file_state"] != prior["unit_file_state"]:
            if prior["unit_file_state"] in {"enabled", "enabled-runtime"}:
                command("disable", name)
                command("disable", "--runtime", name)
                arguments = ["enable"]
                if prior["unit_file_state"] == "enabled-runtime":
                    arguments.append("--runtime")
                command(*arguments, name)
            elif prior["unit_file_state"] in {"disabled", "static", "indirect"}:
                command("disable", name)
                command("disable", "--runtime", name)
            else:
                raise ValueError("masked or absent unit changed")
        if current[name]["active"] != prior["active"]:
            command("start" if prior["active"] else "stop", name)
    if inspect(names) != states:
        raise ValueError("unit restore mismatch")


def retire(names: list[str]) -> dict:
    previous = inspect(names)
    for name, row in previous.items():
        if row["exists"]:
            for arguments in (
                ("stop", name),
                ("disable", name),
                ("disable", "--runtime", name),
            ):
                result = subprocess.run(
                    ["systemctl", *arguments], capture_output=True, timeout=10
                )
                if result.returncode:
                    raise ValueError("unit retirement")
    current = inspect(names)
    if any(row["active"] or row["enabled"] for row in current.values()):
        raise ValueError("unit remains active or enabled")
    return {
        "status": "retired",
        "changed": any(row["active"] or row["enabled"] for row in previous.values()),
    }


def main() -> int:
    try:
        request = json.loads(sys.stdin.read(16385))
        if sys.argv[1:] == ["retire"]:
            print(json.dumps(retire(request), sort_keys=True))
        elif sys.argv[1:] == ["restore"]:
            restore(request)
            print("owned unit states restored")
        elif not sys.argv[1:]:
            print(json.dumps(inspect(request), sort_keys=True))
        else:
            raise ValueError("unit operation")
    except (ValueError, OSError, subprocess.TimeoutExpired):
        print("owned unit state unavailable", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
