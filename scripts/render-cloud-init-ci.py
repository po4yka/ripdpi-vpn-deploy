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
    "admin_ssh_public_keys": ["ssh-ed25519 AAAATESTKEY ci@fixture"],
    "ssh_port": "22",
    "build_env": "ci",
    "bootstrap_ssh_ownership_b64": base64.b64encode(BOOTSTRAP_OWNER.read_bytes()).decode("ascii"),
}


def render(values: dict[str, object] = VALUES) -> str:
    # Fixed CI bindings, not a Terraform expression interpreter. Unknown
    # expressions fail so template changes cannot silently escape schema checks.
    if not all(isinstance(values[name], str) for name in (
        "admin_user", "build_env",
    )):
        raise TypeError("cloud-init scalar inputs must be strings")
    if not (isinstance(values["admin_ssh_public_keys"], list) and all(
        isinstance(key, str) for key in values["admin_ssh_public_keys"]
    )):
        raise TypeError("admin_ssh_public_keys must be a list of strings")
    bindings = dict(values)
    bindings['jsonencode(format("%s", admin_user))'] = json.dumps(values["admin_user"])
    bindings['jsonencode([for key in admin_ssh_public_keys : format("%s", key)])'] = json.dumps(
        values["admin_ssh_public_keys"]
    )
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
