#!/usr/bin/env python3
"""Render the shared cloud-init template with non-secret CI fixture values."""

from __future__ import annotations

import base64
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "terraform" / "shared" / "cloud-init.yaml.tftpl"
BOOTSTRAP_OWNER = ROOT / "terraform" / "shared" / "bootstrap-sshd-ownership.py"
VALUES = {
    "admin_user": "deploy",
    "admin_ssh_public_key": "ssh-ed25519 AAAATESTKEY ci@fixture",
    "ssh_port": "22",
    "build_env": "ci",
    "bootstrap_ssh_ownership_b64": base64.b64encode(BOOTSTRAP_OWNER.read_bytes()).decode("ascii"),
}


def main() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    rendered = re.sub(r"\$\{(\w+)\}", lambda match: VALUES[match.group(1)], template)
    print(rendered, end="")


if __name__ == "__main__":
    main()
