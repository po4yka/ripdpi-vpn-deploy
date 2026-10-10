"""Resolved paths for one invocation; no fleet configuration is loaded."""

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import tempfile
from . import protected_file


def config_home():
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library/Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")


def resolve_runtime_dir():
    return (
        Path(os.environ["XDG_RUNTIME_DIR"])
        if os.environ.get("XDG_RUNTIME_DIR")
        else Path(tempfile.gettempdir()) / f"vpn-provision-{os.getuid()}"
    )


def is_repo_root(path):
    return (
        (path / "Makefile").is_file()
        and (path / "ansible").is_dir()
        and (path / "terraform").is_dir()
    )


def find_repo_root():
    cwd = Path.cwd()
    for path in (cwd, *cwd.parents):
        if is_repo_root(path):
            return path
    raise ValueError("could not locate vpn-deploy repo root (set VPN_DEPLOY_ROOT or cd into it)")


@dataclass
class Context:
    root: Path
    ansible_dir: Path
    tf_root: Path
    env: str
    provider: str
    sops_file: Path
    secrets_file: Path
    config_dir: Path
    explain: bool
    yes: bool

    @classmethod
    def discover(cls, cli):
        try:
            root = Path(cli.root).resolve(strict=True) if cli.root else find_repo_root()
        except OSError as error:
            raise ValueError("--root not found") from error
        ansible = root / "ansible"
        tfroot = root / "terraform/providers" / cli.provider
        if not ansible.is_dir():
            raise ValueError(f"missing {ansible} — not a vpn-deploy repo root")
        if not tfroot.is_dir():
            raise ValueError(
                f"missing {tfroot} — unknown provider '{cli.provider}' (expected upcloud | hetzner | vultr | scaleway)"
            )
        config = config_home() / "vpn-provision"
        return cls(
            root,
            ansible,
            tfroot,
            cli.env,
            cli.provider,
            config / f"{cli.env}.secrets.sops.yaml",
            resolve_runtime_dir() / f"vpn-{cli.env}.secrets.yaml",
            config,
            cli.explain,
            cli.yes,
        )

    def ansible_cfg(self):
        return self.ansible_dir / "ansible.cfg"

    def secure_secrets_file(self):
        if not self.explain:
            try:
                protected_file.harden(self.secrets_file)
            except (OSError, ValueError) as error:
                raise ValueError(
                    "failed to set 0600 on decrypted secrets file: " + str(error)
                ) from error
