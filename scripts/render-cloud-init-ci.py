#!/usr/bin/env python3
"""Render the shared cloud-init template with non-secret CI fixture values."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "terraform" / "shared" / "cloud-init.yaml.tftpl"
VALUES = {
    "admin_user_yaml": json.dumps("deploy"),
    "admin_ssh_public_key_yaml": json.dumps("ssh-ed25519 AAAA_REPLACE_WITH_PUBLIC_KEY operator: ci # fixture"),
    "build_id_content_yaml": json.dumps("provisioned_by=cloud-init\nnext_stage=ansible\nbuild_env=ci\n"),
}


def main() -> None:
    rendered = TEMPLATE.read_text(encoding="utf-8")
    for placeholder, encoded_value in VALUES.items():
        token = "${" + placeholder + "}"
        if token not in rendered:
            raise ValueError(f"cloud-init template is missing expected placeholder {token}")
        rendered = rendered.replace(token, encoded_value)
    if "${" in rendered:
        raise ValueError("cloud-init template contains an unknown or unexpanded placeholder")
    print(rendered, end="")


if __name__ == "__main__":
    main()
