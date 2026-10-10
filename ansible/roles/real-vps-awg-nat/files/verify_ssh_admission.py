#!/usr/bin/env python3
"""Read-only admission proof; server-local provisioning never edits SSH authority."""

from __future__ import annotations
import ipaddress
import json
import re
import subprocess
import sys


def policy(context=None):
    argv = ["/usr/sbin/sshd", "-T"]
    if context is not None:
        argv += ["-C", context]
    result = subprocess.run(
        argv, capture_output=True, text=True, timeout=10, check=False
    )
    if result.returncode:
        raise ValueError("sshd unavailable")
    return dict(
        line.split(" ", 1) for line in result.stdout.splitlines() if " " in line
    )


def verify(value):
    user = value["user"]
    addresses = value["sources"]
    local = str(ipaddress.ip_address(value["local"]))
    if (
        not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user)
        or not addresses
        or len(addresses) > 2
    ):
        raise ValueError("invalid input")
    port = policy()["port"]
    for source in addresses:
        source = str(ipaddress.ip_address(source))
        actual = policy(
            f"user={user},host=sentinel.example.test,addr={source},laddr={local},lport={port}"
        )
        if user not in actual.get("allowusers", "").split():
            raise ValueError("not admitted")
        # Future account/group membership does not exist yet. The supported
        # canonical admission contract cannot infer group or denial matches.
        if any(
            actual.get(key, "").strip()
            for key in ("denyusers", "allowgroups", "denygroups")
        ):
            raise ValueError("unsupported admission restriction")
        if actual.get("authenticationmethods") not in ("any", "publickey"):
            raise ValueError("unsupported authentication factors")
        if actual.get("forcecommand") != "none":
            raise ValueError("server command supersedes forced key")
        for key in (
            "allowtcpforwarding",
            "allowagentforwarding",
            "x11forwarding",
            "permittunnel",
            "permittty",
            "permituserrc",
        ):
            if actual.get(key) != "no":
                raise ValueError("not restricted")
        if any(
            actual.get(key) != "no"
            for key in (
                "passwordauthentication",
                "kbdinteractiveauthentication",
                "permitrootlogin",
            )
        ):
            raise ValueError("unsafe authentication")
        if actual.get("pubkeyauthentication") != "yes":
            raise ValueError("key authentication unavailable")


def main():
    try:
        verify(json.loads(sys.stdin.read(4097)))
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        print("restricted evidence SSH admission unavailable", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
