"""Provision the existing exact-pair lab on an isolated Linux CI host."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main():
    if (
        os.uname().sysname != "Linux"
        or os.environ.get("TRANSPORT_NATIVE_ISOLATED") != "1"
    ):
        raise RuntimeError("isolated-Linux-source-build-required")
    pins = json.loads(
        (ROOT / "tests/integration/awg_source_candidate/sources.json").read_text()
    )
    env = {
        **os.environ,
        "GOMAXPROCS": "2",
        "CGO_ENABLED": "0",
        "GOTOOLCHAIN": "local",
        "GOWORK": "off",
        "GOPROXY": pins["go_module_proxy"],
        "GOFLAGS": "-mod=readonly -p=2",
    }
    toolchain = subprocess.check_output(
        ["go", "env", "GOVERSION"], env=env, text=True
    ).strip()
    if toolchain != "go" + pins["go_toolchain"]:
        raise RuntimeError("pinned-Go-toolchain-required")
    for pair in ("baseline", "candidate"):
        for component in ("go", "tools"):
            pin = pins[pair][component]
            directory = ROOT / ".cache/four-transport-sources" / pair / component
            directory.parent.mkdir(parents=True, exist_ok=True)
            if not directory.exists():
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--branch",
                        pin["tag"],
                        "--single-branch",
                        "https://github.com/amnezia-vpn/amneziawg-" + component,
                        str(directory),
                    ],
                    check=True,
                    timeout=180,
                )
            head = subprocess.check_output(
                ["git", "-C", str(directory), "rev-parse", "HEAD"], text=True
            ).strip()
            if head != pin["commit"]:
                raise RuntimeError("AWG-source-commit-mismatch")
            for args in (["diff", "--exit-code"], ["diff", "--cached", "--exit-code"]):
                subprocess.run(
                    ["git", "-C", str(directory), *args], check=True, timeout=30
                )
            subprocess.run(
                ["make", "-j2"],
                cwd=directory if component == "go" else directory / "src",
                env=env,
                check=True,
                timeout=600,
            )
            for args in (["diff", "--exit-code"], ["diff", "--cached", "--exit-code"]):
                subprocess.run(
                    ["git", "-C", str(directory), *args], check=True, timeout=30
                )


if __name__ == "__main__":
    main()
