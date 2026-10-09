#!/usr/bin/env python3
"""Render the shared cloud-init template with non-secret CI fixture values."""

from __future__ import annotations

import base64
import json
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


def render(values: dict[str, str] = VALUES) -> str:
    # Fixed CI bindings, not a Terraform expression interpreter. Unknown
    # expressions fail so template changes cannot silently escape schema checks.
    if not all(isinstance(values[name], str) for name in (
        "admin_user", "admin_ssh_public_key", "build_env",
    )):
        raise TypeError("cloud-init scalar inputs must be strings")
    bindings = dict(values)
    for name in ("admin_user", "admin_ssh_public_key"):
        bindings[f'jsonencode(format("%s", {name}))'] = json.dumps(values[name])
    bindings[
        'jsonencode(format("provisioned_by=cloud-init\\nnext_stage=ansible\\nbuild_env=%s\\n", build_env))'
    ] = json.dumps(
        f"provisioned_by=cloud-init\nnext_stage=ansible\nbuild_env={values['build_env']}\n"
    )
    template = TEMPLATE.read_text(encoding="utf-8")
    return re.sub(r"\$\{([^{}]+)\}", lambda match: bindings[match.group(1)], template)


def main() -> None:
    print(render(), end="")


if __name__ == "__main__":
    main()
