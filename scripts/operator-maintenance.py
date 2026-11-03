#!/usr/bin/env python3
"""Explicit local operator checks; public output contains categories and counts."""
import base64
import json
import os
import re
import signal
import sys

import operator_kit
import operator_release
from operator_private import capture, checked, document, environment, fields, read_owned, require
from private_client_artifact import new_output


def diagnostics(plan):
    fields(plan, ("schema_version", "argv", "recipient", "output", "timeout", "max_bytes"),
           ("environment_names", "input_file"))
    argv = plan["argv"]
    require(isinstance(argv, list) and 1 <= len(argv) <= 128 and
            all(isinstance(arg, str) and 0 < len(arg) <= 4096 and "\0" not in arg for arg in argv), "invalid-command")
    require(type(plan["timeout"]) is int and 0 < plan["timeout"] <= 3600 and
            type(plan["max_bytes"]) is int and 0 < plan["max_bytes"] <= 16 * 1024 * 1024, "capture-limit")
    names = plan.get("environment_names", [])
    require(isinstance(names, list) and len(names) <= 64 and
            all(isinstance(name, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", name) and
                not name.startswith(("LD_", "DYLD_", "PYTHON", "GIT_")) and
                name not in ("PATH", "ENV", "BASH_ENV", "MAKEFILES", "MAKEFLAGS", "SHELLOPTS") for name in names),
            "invalid-environment-selection")
    env = environment(names)
    data = read_owned(plan["input_file"], limit=4 * 1024 * 1024) if "input_file" in plan else b""
    with new_output(plan["output"]) as (write, validate):
        checked(["age", "-a", "-r", plan["recipient"]], data=b"recipient admission", limit=65536)
        result = capture(argv, timeout=plan["timeout"], limit=plan["max_bytes"], data=data, env=env)
        envelope = {"schema_version": 1, "capture": result["capture"], "exit_code": result["exit_code"],
                    "stdout_base64": base64.b64encode(result["stdout"]).decode(),
                    "stderr_base64": base64.b64encode(result["stderr"]).decode()}
        ciphertext = checked(["age", "-a", "-r", plan["recipient"]],
                             data=json.dumps(envelope).encode(), limit=64 * 1024 * 1024)
        validate()
        write(ciphertext.decode("ascii"))
    code = result["exit_code"] if result["exit_code"] >= 0 else 128 - result["exit_code"]
    if result["capture"] != "complete":
        code = {"timeout": 124, "cancelled": 130}.get(result["capture"], 125)
    return {"result": "diagnostics-encrypted", "capture": result["capture"],
            "command_exit_code": result["exit_code"],
            "captured_bytes": len(result["stdout"]) + len(result["stderr"])}, code


def main():
    def cancel(_number, _frame):
        raise KeyboardInterrupt
    for number in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, cancel)
    try:
        require(len(sys.argv) == 2, "one-action-required")
        action = sys.argv[1]
        require(action in ("operator-release-check", "operator-diagnostics", "operator-kit-check",
                           "operator-kit-seal", "operator-kit-verify-backup"), "invalid-action")
        if action == "operator-diagnostics":
            require(os.environ.get("OPERATOR_CONFIRM_COMMAND") == "1", "command-authority-required")
        if action == "operator-kit-verify-backup":
            require(os.environ.get("OPERATOR_CONFIRM_OFFSITE_READ") == "1", "offsite-read-authority-required")
        path = os.environ.get("OPERATOR_MAINTENANCE_PLAN", "")
        require(bool(path), "plan-required")
        frozen = read_owned(path, limit=4 * 1024 * 1024)
        plan = document(frozen)
        require(read_owned(path, limit=4 * 1024 * 1024) == frozen, "plan-changed")
        code = 0
        if action == "operator-diagnostics":
            answer, code = diagnostics(plan)
        elif action == "operator-release-check":
            answer = operator_release.check(plan)
        elif action == "operator-kit-check":
            answer = operator_kit.check(plan)
        elif action == "operator-kit-seal":
            answer = operator_kit.seal(plan)
        else:
            answer = operator_kit.verify_backup(plan)
        require(read_owned(path, limit=4 * 1024 * 1024) == frozen, "plan-changed")
        print(json.dumps(answer, sort_keys=True))
        return code
    except KeyboardInterrupt:
        print(json.dumps({"result": "cancelled"}), file=sys.stderr)
        return 130
    except Exception as error:
        # Dependency exceptions can include private paths and captured output.
        from operator_private import Refusal
        category = str(error) if isinstance(error, Refusal) else "operation-refused"
        print(json.dumps({"result": "refused", "category": category}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
