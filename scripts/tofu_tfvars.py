"""Select the operator input file for one OpenTofu provider and environment."""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys


def tfvars_path(provider_root: Path, environment: str) -> Path:
    if provider_root.name not in {"upcloud", "hetzner", "vultr", "scaleway"}:
        raise ValueError("unsupported tfvars provider")
    if environment == "default" or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", environment):
        raise ValueError("invalid tfvars environment")
    external = os.environ.get("TFVARS_ROOT")
    if external and not Path(external).is_absolute():
        raise ValueError("TFVARS_ROOT must be an absolute path")
    directory = Path(external) / provider_root.name if external else provider_root / "environments"
    return directory / f"{environment}.tfvars"


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: tofu_tfvars.py <provider> <environment>")
    provider, environment = sys.argv[1:]
    if "/" in provider:
        sys.exit("invalid tfvars provider")
    try:
        print(tfvars_path(Path(__file__).resolve().parents[1] / "terraform/providers" / provider, environment))
    except ValueError as error:
        sys.exit(str(error))
