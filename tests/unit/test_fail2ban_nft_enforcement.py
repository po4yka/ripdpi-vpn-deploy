"""Typed idempotent nft races are distinct from actual enforcement failures."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "ansible/roles/intrusion_prevention/files/vpn-fail2ban-nft.py"
)
spec = importlib.util.spec_from_file_location("fail2ban_enforcement", SOURCE)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def result(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], rc, stdout, stderr)


def observation(address, *, present=True, version=4, **changes):
    current = {
        "family": "inet",
        "table": "filter",
        "name": f"f2b_sshd{version}",
        "type": f"ipv{version}_addr",
        "flags": ["timeout"],
        "elem": (
            [{"elem": {"val": address, "timeout": 3600000, "expires": 10000}}]
            if present
            else []
        ),
    }
    current.update(changes)
    return json.dumps({"nftables": [{"metainfo": {}}, {"set": current}]})


@pytest.mark.parametrize(
    "operation,address,seconds",
    [
        ("ban", "198.51.100.22", 600),
        ("ban", "2001:db8::22", 600),
        ("unban", "198.51.100.22", None),
        ("unban", "2001:db8::22", None),
    ],
)
def test_success_uses_exact_family_and_bounded_timeout(
    monkeypatch, operation, address, seconds
):
    calls = []

    def run(argv):
        calls.append(argv)
        return result()

    monkeypatch.setattr(helper, "run", run)
    helper.enforce(operation, address, seconds)
    assert len(calls) == 1
    assert calls[0][0] == ("add" if operation == "ban" else "delete")
    assert calls[0][4] == ("f2b_sshd6" if ":" in address else "f2b_sshd4")
    if operation == "ban":
        assert calls[0][-3:] == ["timeout", "600s", "}"]


@pytest.mark.parametrize(
    "operation,error,present",
    [("ban", "File exists", True), ("unban", "No such file or directory", False)],
)
def test_only_expected_race_with_confirmed_desired_membership_succeeds(
    monkeypatch, operation, error, present
):
    values = iter(
        [
            result(1, stderr=f"Error: Could not process rule: {error}\n"),
            result(stdout=observation("198.51.100.22", present=present)),
        ]
    )
    monkeypatch.setattr(helper, "run", lambda _argv: next(values))
    helper.enforce(operation, "198.51.100.22", 600)


@pytest.mark.parametrize(
    "failure",
    [
        "permission",
        "missing-set",
        "wrong-type",
        "wrong-family",
        "nested-address",
        "wrong-membership",
    ],
)
def test_unexpected_errors_never_report_success(monkeypatch, failure):
    stderr = "Error: Could not process rule: File exists\n"
    current = observation("198.51.100.22")
    rc = 0
    if failure == "permission":
        stderr = "Error: Could not process rule: Operation not permitted\n"
    elif failure == "missing-set":
        rc = 1
    elif failure == "wrong-type":
        current = observation("198.51.100.22", type="integer")
    elif failure == "wrong-family":
        current = observation("198.51.100.22", family="ip")
    elif failure == "nested-address":
        current = observation(["198.51.100.22"])
    else:
        current = observation("198.51.100.22", present=False)
    values = iter([result(1, stderr=stderr), result(rc, stdout=current)])
    monkeypatch.setattr(helper, "run", lambda _argv: next(values))
    with pytest.raises((helper.EnforcementError, ValueError, TypeError)):
        helper.enforce("ban", "198.51.100.22", 600)
